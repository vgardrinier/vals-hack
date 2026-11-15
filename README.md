# vals-hack

our eval for vals hacks (track 1, build your own eval on valkyrie).
submissions close sun nov 15, 2pm pt.

## setup (once each)

    uv tool install valkyrie-cli
    valkyrie login          # pick the hackathon-yaya-vivi org

## a task

each folder in `tasks/` is one task:

    tasks/<task-id>/
      task.toml           settings (timeouts, docker image)
      instruction.md      what the model is asked to do
      environment/        Dockerfile + files the model gets
      tests/test.sh       grades it, writes 1 or 0 to /logs/verifier/reward.txt
      solution/solve.sh   our reference answer (proves the task is solvable)

`examples/hello` is the smallest working task.

## build the tasks

tasks are generated, not committed (the company docs are big):

    gen/fetch_redwood.sh ../ext/redwood
    python3 gen/build_invoice_task.py ../ext/redwood tasks    # v1: REVIEW in the tracker (too easy, opus 3/3)
    python3 gen/build_approval_task.py ../ext/redwood tasks   # v2: approval habit only in email history (opus 3/3)
    python3 gen/build_approval_v3.py ../ext/redwood tasks     # v3: threshold change + vendor exception
    python3 gen/test_approval_v3_grader.py tasks/invoice-approval-v3   # grader vs answer shapes
    python3 gen/build_ladder.py ../ext/redwood tasks          # ladder tasks 1-4 and 6 (task 5 is v3)
    python3 gen/test_ladder_grader.py tasks/ladder-*            # grader vs answer shapes, every ladder task

## results

    python3 results/collect_ladder.py /tmp/ladder_runs.txt     # -> results/ladder_attempts.json
    python3 results/render.py                                   # -> results/leaderboard.html

`bridge/` is a command-line bridge to Zapier's simulated company apps (AutomationBench), parked for later.

## push + run

    valkyrie dataset push yaya/precedent ./tasks
    valkyrie run start --agent claude_code-v1.0.0 --dataset yaya/precedent \
      --model anthropic/claude-sonnet-4-6 --provider modal \
      -s ANTHROPIC_API_KEY anthropic-api-key --concurrency 4

## drift benchmark (main result)

    python3 gen/build_drift.py ../ext/redwood tasks                  # 4 kinds of change x 1/3/7 examples
    python3 gen/test_drift_grader.py tasks/drift-*-k[137]            # grader vs wrong answers
    python3 gen/replicate.py tasks tasks 5 <task names>              # -r1..-r5 copies, one run per model
    # runs: agent plain-agent (agents/plain-agent), same loop for every model, via scripts/queue_runs.sh
    python3 results/collect_drift.py runs.txt [reruns.txt]           # -> results/drift_attempts.json
    python3 results/classify_drift.py && python3 results/tag_hesitation.py   # how each miss happened
    python3 results/render.py                                        # -> results/leaderboard.html
