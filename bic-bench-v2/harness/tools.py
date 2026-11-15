from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .types import ActionRecord


def _load_action_contracts() -> dict[str, tuple[str, ...]]:
    cases_root = Path(__file__).resolve().parents[1] / "cases"
    contracts: dict[str, set[str]] = {}
    for path in cases_root.glob("*.json"):
        case = json.loads(path.read_text(encoding="utf-8"))
        blueprint = case["scoring_blueprint"]
        for assertion in blueprint["required"] + blueprint["forbidden"]:
            contracts.setdefault(assertion["action"], set()).update(
                assertion.get("fields", {}).keys()
            )
        for sequence in blueprint.get("acceptable_sequences", []):
            for action in sequence:
                contracts.setdefault(action, set())
    if not contracts:
        raise RuntimeError("the fixed business action catalog is empty")
    return {
        action: tuple(sorted(fields))
        for action, fields in sorted(contracts.items())
    }


ACTION_CONTRACTS = _load_action_contracts()
ACTION_CATALOG = tuple(ACTION_CONTRACTS)
ACTION_CONTRACT_DESCRIPTION = "; ".join(
    f"{action}({', '.join(fields)})" for action, fields in ACTION_CONTRACTS.items()
)


TOOL_DEFINITIONS = (
    {
        "name": "business_action",
        "description": "Record one simulated business action. This tool never contacts a real external service.",
        "input_schema": {
            "type": "object",
            "required": ["action", "fields"],
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ACTION_CATALOG,
                    "description": (
                        "Select the closest canonical operation from the fixed benchmark-wide "
                        "catalog. The catalog is identical for every task and model. Use the "
                        "exact field keys in these fixed API signatures when applicable: "
                        + ACTION_CONTRACT_DESCRIPTION
                    ),
                },
                "fields": {"type": "object"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "finish",
        "description": "End the task with a concise explanation of the decision and completed actions.",
        "input_schema": {
            "type": "object",
            "required": ["response"],
            "properties": {"response": {"type": "string"}},
            "additionalProperties": False,
        },
    },
)


class BusinessToolEnvironment:
    def __init__(self) -> None:
        self.actions: list[ActionRecord] = []
        self.final_response = ""
        self.finished = False

    def execute(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name == "business_action":
            action = arguments.get("action")
            fields = arguments.get("fields")
            if not isinstance(action, str) or not action:
                return {"ok": False, "error": "action must be a non-empty string"}
            if not isinstance(fields, dict):
                return {"ok": False, "error": "fields must be an object"}
            record = ActionRecord(index=len(self.actions) + 1, action=action, fields=fields)
            self.actions.append(record)
            return {"ok": True, "record": asdict(record)}
        if name == "finish":
            response = arguments.get("response")
            if not isinstance(response, str):
                return {"ok": False, "error": "response must be a string"}
            self.final_response = response
            self.finished = True
            return {"ok": True, "finished": True}
        return {"ok": False, "error": f"unknown tool: {name}"}
