# vals-hack: the invoice benchmark behind Implicit Action Bench

**Live page: https://implicit-action-bench.vercel.app/** (built with Yacine, repo yacine-baghli/implicit-action-bench).
This repo holds the finance invoices benchmark (Track 2 on the page, "unwritten team habits"): the task
generator, the grader and its tests, the shared agent, every run's results, and the demo deck (`demo/deck.html`).

Can AI agents pick up the rules nobody wrote down? The agent joins a fake finance team (Redwood
Inference), gets 15 new supplier invoices and three quarters of history, and has to log them the way
the team works now. Level 1 has 4 unwritten rules, level 2 has 8 at once, level 3 adds an old policy doc
from January. Each rule is shown by 3 or 5 recent examples. A told control states the rules in the instruction.

Story and numbers: `docs/findings.md` and `docs/STATUS.md`. Numbers on the live page come from
`results/morning_v3.json`, exported by `scripts/export_precedentbench.py` in Yacine's repo.

## what's where

    gen/          task generator (build_morning.py, imports the rule engine in build_approval_v3.py),
                  grader tests (test_*_grader.py), Redwood download, replicate.py for numbered copies
    agents/       plain-agent: the one agent every model runs in (same prompt, one shell tool, 80 steps)
                  codex-gpt6: Codex with GPT-6 models, only used for the own-agent check
    scripts/      queue_runs.sh: starts Valkyrie runs, never more than 10 in flight team-wide
    results/      collect_*.py turn Valkyrie runs into per-attempt JSON; baselines.py scores the
                  no-AI strategies with the same checker; *.json are the raw results
    docs/         findings.md (what we found, how we checked it's fair), leak_check.md, STATUS.md (lab notebook)
    demo/         deck.html, the demo
    archive/      every earlier round and parked experiment, kept so nothing is cherry-picked

Python standard library only. The only install is `valkyrie-cli`.

## setup (once each)

    uv tool install valkyrie-cli
    valkyrie login                       # pick the hackathon-yaya-vivi org
    gen/fetch_redwood.sh ../ext/redwood  # Redwood corpus slices (EnterpriseRAG-Bench, MIT)

## build the tasks (generated, not committed: the company docs are big)

    python3 gen/build_morning.py ../ext/redwood tasks --v3 --doses 3,5 --prefix morning3    # level 1 (+ side versions)
    python3 gen/build_morning.py ../ext/redwood tasks --l2 --doses 3,5 --prefix morningL2   # levels 2, 3 and told
    python3 gen/test_morning_grader.py tasks/morning3-k* tasks/morningL2-k*                 # grader vs wrong answers

Every build runs self-checks (evidence counts per habit, no rule stated in any doc, name collisions with
the corpus). Before any model run, also check the right answer scores 1 and an empty tracker 0 inside
each Docker box (see docs/leak_check.md for the box listing).

## run a model (one plain agent for every model)

`agents/plain-agent/agent.py`: same instructions, one shell tool, effort high, 80 steps, no fallback model.

    IDS=$(python3 gen/replicate.py tasks /tmp/stage 5 morningL2-k3-nohandbook morningL2-k5-nohandbook ...)
    valkyrie dataset push yaya/precedent /tmp/stage --tag my-run
    DATASET=yaya/precedent@<version> TASKS=$IDS CONCURRENCY=25 scripts/queue_runs.sh /tmp/runs.txt \
      "plain-agent|anthropic/claude-fable-5-2|ANTHROPIC_API_KEY anthropic-api-key" \
      "plain-agent|openai/gpt-6.1-sol|OPENAI_API_KEY openai-api-key-victor"

Never more than 10 runs in flight team-wide (the Vals limit); `scripts/queue_runs.sh` enforces it.

## collect and render

    python3 results/collect_morning.py <round> /tmp/runs.txt   # -> results/morning_<round>.json
    python3 results/baselines.py --v3                          # brainless scripts, same checker

`results/morning_v3.json` holds the final run (levels 1-3, told, side versions). `morning_round2.json` and
`morning_vendor.json` are the earlier round used for the own-agent check (Claude Code and Codex).

## archive

Earlier experiments (single-habit tasks, the ladder, drift, earlier morning rounds, the Zapier bridge, the
old standalone page) live in `archive/`, with their data, so nothing is lost.
