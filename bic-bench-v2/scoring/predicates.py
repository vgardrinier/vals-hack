from __future__ import annotations

from typing import Any


MISSING = object()


def action_matches(action: dict[str, Any], assertion: dict[str, Any]) -> bool:
    if action.get("action") != assertion.get("action"):
        return False
    fields = action.get("fields", {})
    if not isinstance(fields, dict):
        return False
    return all(_value_matches(fields.get(key, MISSING), expected) for key, expected in assertion.get("fields", {}).items())


def find_matches(
    actions: list[dict[str, Any]], assertions: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    matches = []
    for assertion in assertions:
        matching_indices = [
            index
            for index, action in enumerate(actions)
            if action_matches(action, assertion)
        ]
        if matching_indices:
            matches.append({"assertion": assertion, "action_indices": matching_indices})
    return matches


def _value_matches(actual: Any, expected: Any) -> bool:
    if not isinstance(expected, dict) or not _contains_operator(expected):
        return actual == expected
    if actual is MISSING:
        return False
    checks = []
    if "equals" in expected:
        checks.append(actual == expected["equals"])
    if "not_equals" in expected:
        checks.append(actual != expected["not_equals"])
    if "contains" in expected:
        checks.append(_contains(actual, expected["contains"]))
    if "contains_any" in expected:
        checks.append(any(_contains(actual, item) for item in expected["contains_any"]))
    if "contains_all" in expected:
        checks.append(all(_contains(actual, item) for item in expected["contains_all"]))
    if "excludes_any" in expected:
        checks.append(all(not _contains(actual, item) for item in expected["excludes_any"]))
    if "greater_than" in expected:
        checks.append(_compare(actual, expected["greater_than"], lambda left, right: left > right))
    if "at_most" in expected:
        checks.append(_compare(actual, expected["at_most"], lambda left, right: left <= right))
    if "at_least" in expected:
        checks.append(_compare(actual, expected["at_least"], lambda left, right: left >= right))
    if "less_than" in expected:
        checks.append(_compare(actual, expected["less_than"], lambda left, right: left < right))
    return all(checks)


def _contains_operator(value: dict[str, Any]) -> bool:
    return bool(
        value.keys()
        & {
            "equals",
            "not_equals",
            "contains",
            "contains_any",
            "contains_all",
            "excludes_any",
            "greater_than",
            "at_most",
            "at_least",
            "less_than",
        }
    )


def _contains(container: Any, item: Any) -> bool:
    if isinstance(container, str):
        return str(item).casefold() in container.casefold()
    if isinstance(container, (list, tuple, set)):
        if isinstance(item, str):
            return any(str(value).casefold() == item.casefold() for value in container)
        return item in container
    if isinstance(container, dict):
        return item in container or item in container.values()
    return False


def _compare(actual: Any, expected: Any, operator: Any) -> bool:
    try:
        return bool(operator(actual, expected))
    except TypeError:
        return False
