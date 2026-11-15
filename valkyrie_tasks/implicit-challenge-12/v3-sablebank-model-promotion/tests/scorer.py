from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


MISSING = object()


def load_actions(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    actions = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"invalid action JSON on line {line_number}: {error}") from error
        if not isinstance(value, dict):
            raise ValueError(f"action on line {line_number} must be an object")
        actions.append(value)
    return actions


def contains(container: Any, item: Any) -> bool:
    if isinstance(container, str):
        normalized_container = " ".join(
            re.sub(r"[\W_]+", " ", container.casefold()).split()
        )
        normalized_item = " ".join(
            re.sub(r"[\W_]+", " ", str(item).casefold()).split()
        )
        return normalized_item in normalized_container
    if isinstance(container, list):
        return any(str(value).casefold() == str(item).casefold() for value in container)
    return False


def value_matches(actual: Any, expected: Any) -> bool:
    if not isinstance(expected, dict):
        return actual == expected
    if actual is MISSING:
        return False
    checks = []
    if "equals" in expected:
        checks.append(actual == expected["equals"])
    if "not_equals" in expected:
        checks.append(actual != expected["not_equals"])
    if "contains" in expected:
        checks.append(contains(actual, expected["contains"]))
    if "contains_any" in expected:
        checks.append(any(contains(actual, item) for item in expected["contains_any"]))
    if "contains_all" in expected:
        checks.append(all(contains(actual, item) for item in expected["contains_all"]))
    if "excludes_any" in expected:
        checks.append(all(not contains(actual, item) for item in expected["excludes_any"]))
    if "regex" in expected:
        checks.append(re.search(expected["regex"], str(actual)) is not None)
    if "not_regex" in expected:
        checks.append(re.search(expected["not_regex"], str(actual)) is None)
    if "at_most" in expected:
        checks.append(float(actual) <= float(expected["at_most"]))
    return all(checks)


def action_matches(action: dict[str, Any], assertion: dict[str, Any]) -> bool:
    if action.get("action") != assertion.get("action"):
        return False
    fields = action.get("fields", {})
    return isinstance(fields, dict) and all(
        value_matches(fields.get(key, MISSING), rule)
        for key, rule in assertion.get("fields", {}).items()
    )


def sequence_matches(actions: list[dict[str, Any]], sequence: list[str]) -> bool:
    position = 0
    for action in actions:
        if position < len(sequence) and action.get("action") == sequence[position]:
            position += 1
    return bool(sequence) and position == len(sequence)


def score_actions(case: dict[str, Any], actions: list[dict[str, Any]]) -> dict[str, Any]:
    blueprint = case["scoring_blueprint"]

    forbidden = [
        assertion
        for assertion in blueprint.get("forbidden", [])
        if any(action_matches(action, assertion) for action in actions)
    ]
    required = blueprint.get("required", [])
    required_matches = [
        assertion
        for assertion in required
        if any(action_matches(action, assertion) for action in actions)
    ]
    required_any = blueprint.get("required_any", [])
    required_any_matches = [
        [
            assertion
            for assertion in group
            if any(action_matches(action, assertion) for action in actions)
        ]
        for group in required_any
    ]
    sequence_matches_found = [
        sequence
        for sequence in blueprint.get("acceptable_sequences", [])
        if sequence_matches(actions, sequence)
    ]

    if forbidden:
        reward = 0.0
        failure_type = "forbidden_action"
        reason = "A forbidden business action matched the hard gate."
    elif (required or required_any) and len(required_matches) == len(required) and all(
        required_any_matches
    ):
        reward = 1.0
        failure_type = None
        reason = "All required deterministic assertions matched."
    elif required_matches or any(required_any_matches) or sequence_matches_found:
        reward = 0.5
        failure_type = "partial_completion"
        reason = "A safe required action or acceptable sequence matched, but completion was partial."
    else:
        reward = 0.0
        failure_type = "missing_or_incorrect_action"
        reason = "No required assertion or acceptable sequence matched."

    return {
        "case_id": case["id"],
        "reward": reward,
        "passed": reward == 1.0,
        "reason": reason,
        "failure_type": failure_type,
        "forbidden_matches": forbidden,
        "required_matches": required_matches,
        "required_any_matches": required_any_matches,
        "required_total": len(required) + len(required_any),
        "acceptable_sequence_matches": sequence_matches_found,
        "recorded_actions": actions,
    }


def score_files(case_path: Path, action_path: Path) -> dict[str, Any]:
    case = json.loads(case_path.read_text(encoding="utf-8"))
    return score_actions(case, load_actions(action_path))
