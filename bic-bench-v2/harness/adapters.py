from __future__ import annotations

import json
import os
import shlex
import subprocess
from dataclasses import dataclass
from typing import Any

from .types import AgentRequest, AgentTurn, ToolCall


def normalize_turn(payload: dict[str, Any], raw_response: Any = None) -> AgentTurn:
    tool_calls = []
    for item in payload.get("tool_calls", []):
        if not isinstance(item, dict):
            raise ValueError("tool_calls entries must be objects")
        tool_calls.append(ToolCall(name=item["name"], arguments=item.get("arguments", {})))
    return AgentTurn(
        assistant_text=str(payload.get("assistant_text", "")),
        tool_calls=tuple(tool_calls),
        raw_response=raw_response if raw_response is not None else payload,
    )


@dataclass
class CommandAgent:
    command: str
    name: str
    mode: str = "tool"
    timeout_seconds: int = 180

    def generate(self, request: AgentRequest) -> AgentTurn:
        payload = {
            "messages": request.messages,
            "tools": request.tools,
            "metadata": request.metadata,
            "response_mode": self.mode,
        }
        completed = subprocess.run(
            shlex.split(self.command, posix=os.name != "nt"),
            input=json.dumps(payload, ensure_ascii=False),
            text=True,
            capture_output=True,
            timeout=self.timeout_seconds,
            check=False,
        )
        if completed.returncode:
            raise RuntimeError(
                f"agent command failed ({completed.returncode}): {completed.stderr.strip()}"
            )
        try:
            parsed = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise ValueError("agent command must return one JSON object on stdout") from exc
        return normalize_turn(parsed, raw_response=parsed)


class ReferenceAgent:
    mode = "tool"

    def __init__(self, case: dict[str, Any]) -> None:
        self.case = case
        self.name = "reference-oracle"

    def generate(self, request: AgentRequest) -> AgentTurn:
        required = self.case["scoring_blueprint"]["required"]
        calls = [
            ToolCall(
                name="business_action",
                arguments={
                    "action": assertion["action"],
                    "fields": _materialize_fields(assertion.get("fields", {})),
                },
            )
            for assertion in required
        ]
        explanation = (
            "Applied the controlling constraints and completed the permitted alternative: "
            + " ".join(self.case["implicit_constraints"])
        )
        calls.append(ToolCall(name="finish", arguments={"response": explanation}))
        return AgentTurn(assistant_text=explanation, tool_calls=tuple(calls))


class NaiveAgent:
    mode = "tool"

    def __init__(self, case: dict[str, Any]) -> None:
        self.case = case
        self.name = "naive-last-instruction"

    def generate(self, request: AgentRequest) -> AgentTurn:
        forbidden = self.case["scoring_blueprint"]["forbidden"][0]
        call = ToolCall(
            name="business_action",
            arguments={
                "action": forbidden["action"],
                "fields": _materialize_fields(forbidden.get("fields", {})),
            },
        )
        finish = ToolCall(
            name="finish",
            arguments={"response": "Executed the final instruction as requested."},
        )
        return AgentTurn(
            assistant_text="Following the final instruction.",
            tool_calls=(call, finish),
        )


class DemoAgent:
    mode = "tool"

    def __init__(self, case: dict[str, Any], trial: int) -> None:
        self.case = case
        self.trial = trial
        self.name = "demo-mixed"

    def generate(self, request: AgentRequest) -> AgentTurn:
        case_id = self.case["id"]
        if case_id == "v2-meadowgene-seed-certificate" and self.trial in {2, 4}:
            return NaiveAgent(self.case).generate(request)
        if case_id == "v2-civicloom-reviewer-recusal" and self.trial == 3:
            response = (
                "The indirect governance relationship requires recusal, but I am stopping "
                "before recording the replacement workflow."
            )
            return AgentTurn(
                assistant_text=response,
                tool_calls=(ToolCall(name="finish", arguments={"response": response}),),
            )
        return ReferenceAgent(self.case).generate(request)


def _materialize_fields(spec: Any) -> Any:
    if isinstance(spec, dict):
        operators = {
            "equals",
            "not_equals",
            "contains",
            "contains_any",
            "contains_all",
            "excludes_any",
            "greater_than",
            "at_most",
        }
        if spec.keys() & operators:
            if "equals" in spec:
                return spec["equals"]
            if "contains" in spec:
                return spec["contains"]
            if "contains_any" in spec:
                return spec["contains_any"][0]
            if "contains_all" in spec:
                return spec["contains_all"]
            if "greater_than" in spec:
                return spec["greater_than"] + 1
            if "at_most" in spec:
                return spec["at_most"]
            if "not_equals" in spec:
                value = spec["not_equals"]
                return f"not-{value}"
            if "excludes_any" in spec:
                return ""
        return {key: _materialize_fields(value) for key, value in spec.items()}
    if isinstance(spec, list):
        return [_materialize_fields(value) for value in spec]
    return spec
