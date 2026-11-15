from __future__ import annotations

import copy
import json
import os
import sys
import time
from typing import Any

from openai import OpenAI


AGENT_MODEL = os.getenv("BIC_OPENAI_AGENT_MODEL", "gpt-6.1-sol")
JUDGE_MODEL = os.getenv("BIC_OPENAI_JUDGE_MODEL", "gpt-6.1-sol")
REASONING_EFFORT = os.getenv("BIC_OPENAI_REASONING_EFFORT", "medium")
TIMEOUT_SECONDS = float(os.getenv("BIC_OPENAI_TIMEOUT", "240"))

PRICES_PER_MILLION = {
    "gpt-6-astra": {"input": 10.0, "output": 50.0, "cached": 1.0},
    "gpt-6.1-sol": {"input": 2.0, "output": 10.0, "cached": 0.1},
    "gpt-6.1-terra": {"input": 1.0, "output": 5.0, "cached": 0.05},
    "gpt-6-luna": {"input": 0.1, "output": 0.5, "cached": 0.01},
}

AGENT_SCHEMA = {
    "type": "object",
    "properties": {
        "assistant_text": {"type": "string"},
        "actions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "description": (
                            "The concrete business operation, such as record_decision or "
                            "check_network_registration; never business_action or finish."
                        ),
                    },
                    "fields_json": {
                        "type": "string",
                        "description": "A JSON object encoded as a string.",
                    },
                },
                "required": ["action", "fields_json"],
                "additionalProperties": False,
            },
        },
        "final_response": {"type": "string"},
        "done": {"type": "boolean"},
    },
    "required": ["assistant_text", "actions", "final_response", "done"],
    "additionalProperties": False,
}

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "constraint_awareness": {"type": "number", "enum": [0, 0.5, 1]},
        "alternative_quality": {"type": "number", "enum": [0, 0.5, 1]},
        "awareness_explanation": {"type": "string"},
        "alternative_explanation": {"type": "string"},
    },
    "required": [
        "constraint_awareness",
        "alternative_quality",
        "awareness_explanation",
        "alternative_explanation",
    ],
    "additionalProperties": False,
}


def main() -> int:
    payload = json.load(sys.stdin)
    client = OpenAI(timeout=TIMEOUT_SECONDS)
    if "judge_version" in payload:
        result = run_judge(client, payload)
    else:
        result = run_agent(client, payload)
    json.dump(result, sys.stdout, ensure_ascii=False)
    return 0


def run_agent(client: OpenAI, payload: dict[str, Any]) -> dict[str, Any]:
    messages = payload["messages"]
    system = next(
        (message["content"] for message in messages if message.get("role") == "system"),
        "",
    )
    instructions = (
        system
        + "\n\nReturn a structured action plan. Put each business action's fields in "
        + "fields_json as a valid JSON object string. Use no more than four actions, "
        + "select the closest canonical operation from the schema enum, set done=true, "
        + "and provide a concise final_response when complete."
    )
    transcript = _transcript(message for message in messages if message.get("role") != "system")
    schema = copy.deepcopy(AGENT_SCHEMA)
    action_catalog = payload["tools"][0]["input_schema"]["properties"]["action"].get("enum")
    action_description = payload["tools"][0]["input_schema"]["properties"]["action"].get(
        "description"
    )
    if action_catalog:
        schema["properties"]["actions"]["items"]["properties"]["action"]["enum"] = action_catalog
    if action_description:
        schema["properties"]["actions"]["items"]["properties"]["action"][
            "description"
        ] = action_description
    started = time.perf_counter()
    response = client.responses.create(
        model=AGENT_MODEL,
        instructions=instructions,
        input=transcript,
        reasoning={"effort": REASONING_EFFORT},
        max_output_tokens=1200,
        text={
            "format": {
                "type": "json_schema",
                "name": "bic_agent_turn",
                "schema": schema,
                "strict": True,
            }
        },
        store=False,
    )
    parsed = json.loads(response.output_text)
    tool_calls = []
    for action in parsed["actions"]:
        fields = json.loads(action["fields_json"])
        if not isinstance(fields, dict):
            raise ValueError("fields_json must decode to an object")
        action_name = action["action"]
        if action_name == "business_action" and isinstance(fields.get("type"), str):
            action_name = fields.pop("type")
        if action_name == "finish":
            continue
        tool_calls.append(
            {
                "name": "business_action",
                "arguments": {"action": action_name, "fields": fields},
            }
        )
    if parsed["done"]:
        tool_calls.append(
            {
                "name": "finish",
                "arguments": {"response": parsed["final_response"]},
            }
        )
    return {
        "assistant_text": parsed["assistant_text"],
        "tool_calls": tool_calls,
        "_usage": _usage(response, time.perf_counter() - started),
    }


def run_judge(client: OpenAI, payload: dict[str, Any]) -> dict[str, Any]:
    judge_input = {key: value for key, value in payload.items() if key not in {"prompt"}}
    started = time.perf_counter()
    response = client.responses.create(
        model=JUDGE_MODEL,
        instructions=payload["prompt"],
        input=json.dumps(judge_input, ensure_ascii=False),
        reasoning={"effort": REASONING_EFFORT},
        max_output_tokens=700,
        text={
            "format": {
                "type": "json_schema",
                "name": "bic_judge_result",
                "schema": JUDGE_SCHEMA,
                "strict": True,
            }
        },
        store=False,
    )
    parsed = json.loads(response.output_text)
    parsed["_usage"] = _usage(response, time.perf_counter() - started)
    return parsed


def _transcript(messages: Any) -> str:
    sections = []
    for message in messages:
        role = message.get("role", "unknown").upper()
        content = message.get("content", "")
        calls = message.get("tool_calls")
        result = message.get("result")
        body = content
        if calls:
            body += "\nTOOL_CALLS: " + json.dumps(calls, ensure_ascii=False)
        if result is not None:
            body += "\nTOOL_RESULT: " + json.dumps(result, ensure_ascii=False)
        sections.append(f"[{role}]\n{body}")
    return "\n\n".join(sections)


def _usage(response: Any, elapsed_seconds: float) -> dict[str, Any]:
    usage = response.usage
    cached_tokens = 0
    details = getattr(usage, "input_tokens_details", None)
    if details is not None:
        cached_tokens = int(getattr(details, "cached_tokens", 0) or 0)
    input_tokens = int(usage.input_tokens)
    output_tokens = int(usage.output_tokens)
    uncached_tokens = max(0, input_tokens - cached_tokens)
    prices = PRICES_PER_MILLION.get(response.model)
    estimated_cost = None
    if prices:
        estimated_cost = (
            uncached_tokens * prices["input"]
            + cached_tokens * prices["cached"]
            + output_tokens * prices["output"]
        ) / 1_000_000
    return {
        "provider": "openai",
        "model": response.model,
        "input_tokens": input_tokens,
        "cached_input_tokens": cached_tokens,
        "output_tokens": output_tokens,
        "estimated_cost_usd": estimated_cost,
        "elapsed_seconds": round(elapsed_seconds, 3),
        "response_id": response.id,
    }


if __name__ == "__main__":
    raise SystemExit(main())
