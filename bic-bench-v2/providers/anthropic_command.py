from __future__ import annotations

import copy
import json
import os
import sys
import time
from typing import Any

import anthropic


AGENT_MODEL = os.getenv("BIC_ANTHROPIC_AGENT_MODEL", "claude-opus-5-5")
JUDGE_MODEL = os.getenv("BIC_ANTHROPIC_JUDGE_MODEL", "claude-opus-5-5")
EFFORT = os.getenv("BIC_ANTHROPIC_EFFORT", "medium")
TIMEOUT_SECONDS = float(os.getenv("BIC_ANTHROPIC_TIMEOUT", "300"))
AGENT_MAX_TOKENS = int(os.getenv("BIC_ANTHROPIC_AGENT_MAX_TOKENS", "4096"))
JUDGE_MAX_TOKENS = int(os.getenv("BIC_ANTHROPIC_JUDGE_MAX_TOKENS", "1200"))

PRICES_PER_MILLION = {
    "claude-opus-5-5": {
        "input": 4.0,
        "output": 20.0,
        "cache_read": 0.20,
        "cache_write_5m": 5.0,
        "cache_write_1h": 8.0,
    }
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
    client = anthropic.Anthropic(timeout=TIMEOUT_SECONDS)
    result = run_judge(client, payload) if "judge_version" in payload else run_agent(client, payload)
    json.dump(result, sys.stdout, ensure_ascii=False)
    return 0


def run_agent(client: anthropic.Anthropic, payload: dict[str, Any]) -> dict[str, Any]:
    messages = payload["messages"]
    system = next(
        (message["content"] for message in messages if message.get("role") == "system"),
        "",
    )
    system += (
        "\n\nReturn a structured action plan. Put each business action's fields in "
        "fields_json as a valid JSON object string. The action value must be the "
        "concrete operation, never a tool-envelope name such as business_action or "
        "finish. Use no more than four actions, keep every field concise, set "
        "done=true, and provide a concise final_response when complete."
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
    response = client.messages.create(
        model=AGENT_MODEL,
        max_tokens=AGENT_MAX_TOKENS,
        system=system,
        messages=[{"role": "user", "content": transcript}],
        output_config={
            "effort": EFFORT,
            "format": {"type": "json_schema", "schema": schema},
        },
    )
    parsed = json.loads(_text(response))
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


def run_judge(client: anthropic.Anthropic, payload: dict[str, Any]) -> dict[str, Any]:
    judge_input = {key: value for key, value in payload.items() if key != "prompt"}
    started = time.perf_counter()
    response = client.messages.create(
        model=JUDGE_MODEL,
        max_tokens=JUDGE_MAX_TOKENS,
        system=payload["prompt"],
        messages=[
            {
                "role": "user",
                "content": json.dumps(judge_input, ensure_ascii=False),
            }
        ],
        output_config={
            "effort": EFFORT,
            "format": {"type": "json_schema", "schema": JUDGE_SCHEMA},
        },
    )
    parsed = json.loads(_text(response))
    parsed["_usage"] = _usage(response, time.perf_counter() - started)
    return parsed


def _text(message: Any) -> str:
    return "".join(block.text for block in message.content if block.type == "text")


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


def _usage(message: Any, elapsed_seconds: float) -> dict[str, Any]:
    usage = message.usage
    input_tokens = int(usage.input_tokens)
    output_tokens = int(usage.output_tokens)
    cache_read = int(usage.cache_read_input_tokens or 0)
    cache_write = int(usage.cache_creation_input_tokens or 0)
    prices = PRICES_PER_MILLION.get(message.model)
    estimated_cost = None
    if prices:
        base_input = max(0, input_tokens - cache_read - cache_write)
        estimated_cost = (
            base_input * prices["input"]
            + cache_read * prices["cache_read"]
            + cache_write * prices["cache_write_5m"]
            + output_tokens * prices["output"]
        ) / 1_000_000
    return {
        "provider": "anthropic",
        "model": message.model,
        "input_tokens": input_tokens,
        "cached_input_tokens": cache_read,
        "cache_creation_input_tokens": cache_write,
        "output_tokens": output_tokens,
        "estimated_cost_usd": estimated_cost,
        "elapsed_seconds": round(elapsed_seconds, 3),
        "response_id": message.id,
    }


if __name__ == "__main__":
    raise SystemExit(main())
