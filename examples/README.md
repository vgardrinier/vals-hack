# example tasks

Two tasks exactly as they run on Valkyrie (dataset `yaya/precedent`), so you can open one without building anything:

- `morningL2-k3-nohandbook`: the main benchmark. 8 unwritten rules, 3 examples each, no old policy doc.
- `morningL2-k3-told`: the same task with the 8 rules stated in the instruction (the fairness control).

Each has `instruction.md`, the company files in `environment/`, the grader in `tests/` and a reference answer in `solution/`. The rest are built with `gen/build_morning.py` (see the main README). The background emails, Slack threads and tickets come from EnterpriseRAG-Bench (MIT).
