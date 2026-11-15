from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any


CHALLENGE_ROOT = Path(__file__).resolve().parent
BIC_ROOT = CHALLENGE_ROOT.parent
REPOSITORY_ROOT = BIC_ROOT.parent
for path in (BIC_ROOT, REPOSITORY_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from challenge12.materialize import (  # noqa: E402
    BLUEPRINTS_PATH,
    CASES_ROOT,
    CONTEXTS_ROOT,
)
from challenge12.source import CASES  # noqa: E402
from generate_harbor_tasks import GENERIC_ACTION_CATALOG, materialize  # noqa: E402
from harbor.scorer import action_matches, score_actions  # noqa: E402


HARBOR_ROOT = REPOSITORY_ROOT / "valkyrie_tasks" / "implicit-challenge-12"
PRIORITY_FAMILIES = {
    "authority_governance",
    "evidence_claims_accuracy",
    "temporal_version_validity",
    "financial_risk_controls",
}
BANNED_RECYCLED_PATTERNS = (
    "surfing every friday",
    "friday after 2pm",
    "avoid lunch",
    "scheduled over lunch",
    "acme corp pricing",
    "no slop",
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def normalized(value: str) -> str:
    return " ".join(re.sub(r"[\W_]+", " ", value.casefold()).split())


def reference_action(assertion: dict[str, Any]) -> dict[str, Any]:
    return {
        "action": assertion["action"],
        "fields": {
            key: materialize(rule)
            for key, rule in assertion.get("fields", {}).items()
        },
    }


def validate_source() -> None:
    require(len(CASES) == 12, f"expected 12 source cases, found {len(CASES)}")
    ids = [case["id"] for case in CASES]
    require(len(ids) == len(set(ids)), "challenge case IDs must be unique")
    require(len({case["industry"] for case in CASES}) >= 8, "need at least 8 industries")
    require(
        sum(case["ambiguity"]["two_defensible_actions"] for case in CASES) >= 6,
        "at least half the cases need two defensible actions",
    )

    family_counts: Counter[str] = Counter()
    for case in CASES:
        case_id = case["id"]
        documents = case["documents"]
        context_files = case["context_files"]
        require(6 <= len(context_files) <= 10, f"{case_id}: context count must be 6-10")
        require(len(context_files) == len(set(context_files)), f"{case_id}: duplicate context file")
        require(set(context_files) == set(documents), f"{case_id}: document map mismatch")
        require(
            2 <= len(case["evidence_signals"]) <= 4,
            f"{case_id}: main constraint must use 2-4 signals",
        )
        evidence_files = [signal["file"] for signal in case["evidence_signals"]]
        require(len(evidence_files) == len(set(evidence_files)), f"{case_id}: duplicate evidence signal")
        require(set(evidence_files) <= set(context_files), f"{case_id}: unknown evidence file")
        require(len(case["distractor_files"]) >= 2, f"{case_id}: need at least two distractors")
        require(set(case["distractor_files"]) <= set(context_files), f"{case_id}: unknown distractor")
        require(case["constraint_tensions"], f"{case_id}: missing constraint tension")
        require(len(case["constraint_families"]) >= 2, f"{case_id}: missing multi-constraint tension")
        family_counts.update(case["constraint_families"])

        summary = normalized(case["constraint_summary"])
        for name, body in documents.items():
            require(summary not in normalized(body), f"{case_id}: constraint copied verbatim into {name}")
        joined = normalized("\n".join(documents.values()))
        for pattern in BANNED_RECYCLED_PATTERNS:
            require(pattern not in joined, f"{case_id}: recycled example pattern {pattern!r}")

        blueprint = case["scoring_blueprint"]
        require(blueprint.get("forbidden"), f"{case_id}: missing forbidden hard gate")
        require(blueprint.get("required"), f"{case_id}: missing required assertions")
        for group in (blueprint.get("forbidden", []), blueprint.get("required", [])):
            for assertion in group:
                action = assertion["action"]
                require(action in GENERIC_ACTION_CATALOG, f"{case_id}: unknown action {action}")
                unknown_fields = set(assertion.get("fields", {})) - set(GENERIC_ACTION_CATALOG[action])
                require(not unknown_fields, f"{case_id}: unknown fields {sorted(unknown_fields)}")

        safe_actions = [reference_action(item) for item in blueprint["required"]]
        safe_score = score_actions(
            {"id": case_id, "scoring_blueprint": blueprint}, safe_actions
        )
        require(safe_score["reward"] == 1.0, f"{case_id}: reference actions do not pass")
        for assertion in blueprint["forbidden"]:
            bad_action = reference_action(assertion)
            require(action_matches(bad_action, assertion), f"{case_id}: forbidden assertion is unmatchable")
            bad_score = score_actions(
                {"id": case_id, "scoring_blueprint": blueprint}, [bad_action]
            )
            require(
                bad_score["failure_type"] == "forbidden_action" and bad_score["reward"] == 0.0,
                f"{case_id}: forbidden hard gate does not block",
            )

    require(PRIORITY_FAMILIES <= set(family_counts), "not all priority families are represented")


def validate_materialized() -> None:
    case_paths = sorted(CASES_ROOT.glob("*.json"))
    require(len(case_paths) == 12, f"expected 12 materialized cases, found {len(case_paths)}")
    blueprints = json.loads(BLUEPRINTS_PATH.read_text(encoding="utf-8"))
    require(len(blueprints) == 12, "expected 12 materialized blueprints")
    for case_path in case_paths:
        case = json.loads(case_path.read_text(encoding="utf-8"))
        context_root = CONTEXTS_ROOT / case["id"]
        require(context_root.is_dir(), f"{case['id']}: missing context directory")
        require(
            sorted(path.name for path in context_root.glob("*.md")) == sorted(case["context_files"]),
            f"{case['id']}: materialized context mismatch",
        )


def validate_harbor() -> None:
    task_dirs = sorted(path for path in HARBOR_ROOT.iterdir() if path.is_dir())
    require(len(task_dirs) == 12, f"expected 12 Harbor tasks, found {len(task_dirs)}")
    for task_dir in task_dirs:
        task_toml = (task_dir / "task.toml").read_text(encoding="utf-8")
        require("allow_internet = false" in task_toml, f"{task_dir.name}: internet is not disabled")
        expected = json.loads((task_dir / "tests" / "expected.json").read_text(encoding="utf-8"))
        require(expected["id"] == task_dir.name, f"{task_dir.name}: verifier ID mismatch")
        company_files = list((task_dir / "environment" / "company_data").glob("*.md"))
        require(6 <= len(company_files) <= 10, f"{task_dir.name}: invalid packaged context count")
        require((task_dir / "solution" / "solve.sh").is_file(), f"{task_dir.name}: missing oracle solution")


def main() -> None:
    validate_source()
    validate_materialized()
    validate_harbor()
    primary = Counter(case["primary_family"] for case in CASES)
    industries = len({case["industry"] for case in CASES})
    ambiguous = sum(case["ambiguity"]["two_defensible_actions"] for case in CASES)
    documents = sum(len(case["context_files"]) for case in CASES)
    print(
        "Challenge12 validation passed: "
        f"12 cases, {documents} documents, {industries} industries, "
        f"{ambiguous} ambiguous-action cases, primary families={dict(sorted(primary.items()))}."
    )


if __name__ == "__main__":
    main()
