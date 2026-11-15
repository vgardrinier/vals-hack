# Status: where PrecedentBench is (Sat Nov 14, ~8:30pm)

Read this first. The README has the commands; this has the story and the numbers.

## Messy monday morning (in progress, overnight Nov 14-15)

Plan: docs/plans/next-iteration-messy-morning.md. Generator: gen/build_morning.py. Grader test: gen/test_morning_grader.py.
Score = share of the 15 invoices fully right (right REVIEW note naming the right reviewer, right cost center, logged once).

- **round 1 (pilot, 2 tries per version)**: Fable 59%, GPT-6 Astra 71%, GPT-6.1 Sol 43%, Opus 32%, Sonnet 20% mean score.
  The stale handbook is brutal: without it Fable 84%, Sol 87%, Astra 93%, Opus 64%, Sonnet 40%; with it Fable 33%,
  Astra 49%, Opus/Sonnet/Sol 0%. Plan b: BOTH rules fired. "Too hard": k1 with handbook scored 0 for every model.
  "Too easy": Fable above 50%. Results: results/morning_round1.json.
- **round 2 changes**: (too hard, step 1: fix broken/ambiguous) dropped k1+handbook (1 deviating row against a written
  policy and ~40 old rows is a defensible reading either way, Fable said so in its runs); fixed a realism bug Fable
  flagged (new invoices were round numbers, some far above what suppliers bill). (too easy, step 1: tighten Fable's
  easiest habit) contract/cutoff/cost center tied at 100% for Fable without the handbook; tie-break picked cutoff and
  made it partial: since Oct 5, Security invoices kept the $5k cutoff (REVIEW: Mireille). Tasks prefixed morning2-.

- **round 2 (full run, 5 tries per version, 25 per model)**: mean score / Pass@1:
  GPT-6 Astra 70% / 48%, GPT-6.1 Sol 51% / 20%, Fable 5.2 47% / 16%, Opus 5.5 29% / 8%, Sonnet 5.5 13% / 0%.
  Without vs with the stale handbook (2 and 3 examples): Astra 94 -> 50, Sol 91 -> 0, Fable 80 -> 27, Opus 69 -> 0,
  Sonnet 29 -> 0. In 40 of 50 handbook tries the agent followed the written policy over the tracker.
  Curve without the handbook (1 / 2 / 3 examples, all models averaged): 33% / 69% / 80%.
  Plan b after round 2: neither "too hard" nor "too easy" fired (no version at 0 for everyone, only Sonnet under 10%,
  Fable under 50%), so no further change was allowed. Target (Fable and top GPT under 30%) NOT met: Fable 47%,
  Astra 70%. Results: results/morning_round2.json. This is now the main benchmark on the page.

## Previous main: the drift benchmark

The question: when a company quietly changes how it does something, do agents notice?
Same fake finance team at Redwood Inference. Its habit (a REVIEW note in the invoice tracker)
changes in one of 4 ways, and the tracker shows 1, 3 or 7 invoices handled the new way since:

- cutoff moved: REVIEW cutoff went from $5k to $10k
- habit stopped: the team stopped writing REVIEW
- approver changed: a new person's initials on big invoices
- habit came back: REVIEW paused, then resumed

12 versions x 5 tries x 5 models = 300 tries. **Every model runs in the same plain agent**
(`agents/plain-agent`: same prompt, one bash tool, effort high, 80 steps, no fallbacks), so we
compare models, not Claude Code vs Codex. That fixed a big bias: GPT looked broken inside Codex.

| model | score | 1 example | 3 examples | 7 examples |
|---|---|---|---|---|
| Fable 5.2 | 71% | 62 | 75 | 75 |
| GPT-6.1 Sol | 59% | 38 | 58 | 83 |
| GPT-6 Astra | 53% | 38 | 40 | 80 |
| Opus 5.5 | 41% | 28 | 43 | 53 |
| Sonnet 5.5 | 28% | 13 | 28 | 43 |

Known issues to fix next round: "came back" can be passed by ignoring dates; the approver tag is
ambiguous; on "habit stopped" Fable notices the change but keeps REVIEW to be safe (graded as a miss,
noted on the page). Next round aims for Fable under 50% and GPT under 30%, with harder but fair tasks
(partial changes, stacked changes, quarterly archive files, a bit of human messiness, 1-3 examples).

Data: `results/drift_attempts.json`. Generator: `gen/build_drift.py`. Page: `results/leaderboard.html`.
Runs: one run per model holding all copies (`gen/replicate.py`), queue via `scripts/queue_runs.sh`
(cap 10 runs org-wide). OpenAI key for the shared agent is the Valkyrie secret `openai-api-key-victor`.

## shared minimal agent vs each brand's own agent (same messy monday tasks)

question from Yacine: does our minimal agent test the harness instead of the model? we ran the exact same
25 task copies (dataset `yaya/precedent@12`, 5 versions x 5 tries) with Claude models in Claude Code and
GPT models in Codex. results in `results/morning_vendor.json`, page tab "Shared agent vs own agent".

| model | shared, mean | own agent, mean | shared, pass@1 | own agent, pass@1 |
|---|---|---|---|---|
| GPT-6 Astra | 70% | 50% (Codex) | 48% | 20% |
| GPT-6.1 Sol | 51% | 39% (Codex) | 20% | 12% |
| Fable 5.2 | 47% | 42% (Claude Code) | 16% | 4% |
| Opus 5.5 | 29% | 22% (Claude Code) | 8% | 0% |
| Sonnet 5.5 | 13% | 34% (Claude Code) | 0% | 0% |

the full vendor agents do not do better: 4 of 5 models score lower, and pass@1 drops for everyone who
had any. so the minimal agent isn't what holds them back.

the one exception, Sonnet, goes up for the wrong reason: in Claude Code it saw the "REVIEW: name" notes,
couldn't pin down the rule, left every note blank and asked to be told the rule. blank happens to be right
for about half the invoices (see the "log everything, no notes" baseline at 53%). it understood no more.
Astra drops because in Codex it followed the stale handbook ("marked 14 for review under the AP policy"),
where in the shared agent it often trusted the tracker instead.

## dumb baselines on the messy monday (round 2), no AI

scripted strategies, graded by the tasks' own grader (`results/baselines.py`, `results/baselines.json`).
mean score = share of the 15 invoices with the right note and cost center. one deterministic try each.

| strategy | no handbook | handbook | all |
|---|---|---|---|
| copy last time for this supplier | 71% | 70% | 71% |
| copy last time for this supplier, same size | 64% | 73% | 68% |
| log everything, no notes | 53% | 53% | 53% |
| majority for this supplier | 27% | 27% | 27% |
| flag everything over $5k | 7% | 7% | 7% |
| follow the handbook | 0% | 0% | 0% |

none of them ever gets all 15 right (pass@1 = 0% for every strategy).

**two shortcuts in the mean score:**
- **copying each supplier's most recent row scores 71%**, above every model except GPT-6 Astra. the latest
  row for a supplier usually already carries its new reviewer, new cost center or contract exemption, so
  recency comes for free without understanding the rule. it fails where the size of the invoice matters
  (the moved cutoff)
- **writing no notes at all scores 53%**: many of the 15 invoices correctly need no note (exempt supplier,
  invoices under the new cutoff). models that follow the stale handbook score below doing nothing

what that means: pass@1 is the cleaner metric here (no dumb strategy ever passes). for the mean score,
quote it next to these baselines. a fix for the next version: pick new invoices where the supplier's
latest row is NOT the right answer (e.g. a mid-size invoice from a supplier whose last one was big),
and balance invoices that need a note vs not.

## Earlier experiments (vendor agents: Claude Code / Codex)

## The idea

Every company runs on habits nobody wrote down. New hires learn them from past work.
PrecedentBench tests whether AI agents can too.

The agent joins the finance team at Redwood Inference (a fake AI company). New supplier
invoices are in its inbox; the job is "log each one in the tracker". The catch: some
invoices need the finance director's approval first, and the rules for that only show in
how the team handled past invoices.

## The main task (v3)

Hidden rule, never written down:
- invoices over a cutoff get forwarded to the director (Mireille Ashdown) before logging
- the cutoff moved from $5,000 to $10,000 in early October
- one supplier (Halverson) stopped needing approval after signing a contract in September

Five new invoices test it. A model applying the old "$5k -> director" rule fails.

Background: ~2,100 real-looking emails, Slack threads and tickets from the Redwood corpus
(EnterpriseRAG-Bench, Onyx, MIT), filtered so nothing hints at or contradicts the rule.
The finance history (90 invoices, every supplier email, 16 approval threads) is generated
from the rule itself, so it can't disagree with the answer key.

## Four levels of the same task

| level | instruction | what it measures |
|---|---|---|
| told | rule stated in the instruction | fairness check: can it follow the rule at all |
| written | rule in 3 emails among ~800 | does it go look |
| pointed | "handle these the way the team usually does" | can it work the rule out from behavior |
| no pointer | just "log each one" | does it look on its own, and then work it out |

## Results so far (rule score, partial credit over the rule's 3 parts)

| model | told | written | pointed (3 tries) | no pointer (8 tries) |
|---|---|---|---|---|
| Fable 5.2 | 100% | 100% | 89% | 79% |
| Opus 5.5 | 100% | 88% | 56% | 29% |
| GPT-6.1 Sol | 100% | 0% | 56% | 0% |
| Sonnet 5.5 | 100% | 0% | 33% | 0% |
| GPT-6 Astra | 100% | 0% | not run | 0% |
| Haiku 5.5 | 100% | 0% | not run | 0% |

What we learned:
- told = 48/48 passes, so the task and the grader are fair
- without a pointer, Sonnet and Haiku never open the email history; GPT models search it for a
  written procedure, find none, and stop. That's why the no-pointer level is so binary
- with the pointer, every model finds the habit and asks the director; most then apply the
  old $5k cutoff. That's the reasoning failure we want to measure

Leaderboard page: `results/leaderboard.html` (open in a browser; dropdowns switch level/metric).
Raw per-attempt data: `results/v3_attempts.json`.

## In progress: the 6-task ladder

To make scores less all-or-nothing, a ladder of tasks that vary where the habit lives and
how tricky it is (all without a pointer):

1. tracker: big invoices marked REVIEW in the tracker (easy, everyone should pass)
2. tracker: REVIEW cutoff moved $5k -> $10k
3. tracker: one supplier never marked after its contract
4. email: big invoices need approval (stable)
5. email: cutoff moved + exception (the v3 task)
6. email: director on leave, a deputy covers

5 models x 5 tries x 6 tasks, being run now. Generator: `gen/build_ladder.py`.
Goal for the next round: Fable under ~60% overall without any frontier model at 0%.

## Rules of the road

- Up to 10 Valkyrie runs in progress across the team (the Vals limit). Start runs only with
  `scripts/queue_runs.sh` (it counts everyone's runs, including yours).
- Before any model run: generator self-checks pass, the grader test script passes, and the
  solution scores 1 / untouched scores 0 inside the Docker box.

## Agents

- Claude models: `claude_code-v1.0.0` (Vals registry)
- GPT-6 models: `agents/codex-gpt6` (Vals' Codex agent, allowed-model list extended)
- `agents/codex-oss` + `oss/serve_gpt_oss.py`: attempt at gpt-oss-120b on Modal. Server works;
  Codex can't talk to it (new Codex dropped the API style vLLM serves, old Codex drops the
  replies). Parked. Next open model: DeepSeek via its Anthropic-compatible API (needs a key).
- Gemini 4 Argon / Carbon: wanted, needs a Gemini API key and a Gemini CLI agent wrapper.
