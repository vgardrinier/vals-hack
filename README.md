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
    python3 gen/build_approval_task.py ../ext/redwood tasks   # v2: approval habit only in email history

`bridge/` is a command-line bridge to Zapier's simulated company apps (AutomationBench), parked for later.

## push + run

    valkyrie dataset push yaya/precedent ./tasks
    valkyrie run start --agent claude_code-v1.0.0 --dataset yaya/precedent \
      --model anthropic/claude-sonnet-4-6 --provider modal \
      -s ANTHROPIC_API_KEY anthropic-api-key --concurrency 4
