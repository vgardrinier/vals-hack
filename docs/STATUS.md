# Status: where PrecedentBench is (Sat Nov 14, evening)

Read this first. The README has the commands; this has the story and the numbers.

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

- Never more than 5 Valkyrie runs in progress across the team. Start runs only with
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
