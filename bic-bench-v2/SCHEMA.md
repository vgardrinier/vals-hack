# V2 review-stage case schema

Each file in `cases/` is JSON with these fields:

- `id`, `title`, `industry`, `company`, `category`;
- `difficulty`: tier, evidence depth, distractor count, temporal conflicts, and whether multiple constraints apply;
- `action_type`: the primary final tool action being tested;
- `context_files`: ordered relative paths under the task's context directory;
- `task`: a business objective, analysis steps, and the final explicit instruction;
- `implicit_constraints`: normalized ground truth hidden from the evaluated agent;
- `expected_behavior`: required evidence, required actions, allowed adaptations, and why refusal alone is insufficient;
- `failure_criteria`: observable unsafe or incomplete behaviors;
- `scoring_blueprint`: deterministic `forbidden` and `required` action predicates, acceptable action sequences, and judge anchors.

The review-stage files are intentionally richer than the eventual public task payload. Hidden constraints, expected behavior, and scoring blueprints must be placed only in verifier-side files when Harbor tasks are generated.
