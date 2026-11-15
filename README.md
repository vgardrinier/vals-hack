# PrecedentBench (vals-hack)

Our eval for Vals Hacks (track 1, build your own eval on Valkyrie). Submissions close Sun Nov 15, 2pm PT.

Can AI agents follow the habits nobody wrote down? The agent joins a fake finance team (Redwood
Inference), gets 15 new supplier invoices and three quarters of history, and has to log them the way
the team works now. Level 1 has 4 habits, level 2 has 8 at once, level 3 adds last year's policy doc.
Each habit is shown by 3 or 5 recent examples. A told control states the habits in the instruction.

Results page: `results/leaderboard.html`. Story and numbers: `docs/STATUS.md`.

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
    python3 results/render.py && open results/leaderboard.html

`results/morning_v3.json` holds the final run (levels 1-3, told, side versions). `morning_round2.json` and
`morning_vendor.json` are the earlier round the page cites for the own-agent check.

## archive

Earlier experiments (single-habit tasks, the ladder, drift, earlier morning rounds, the Zapier bridge, the
old page) live in `archive/`, with their data, so nothing is lost.
