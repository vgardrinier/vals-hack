"""plain-agent: one minimal agent loop, identical for every model.

    python agent.py <problem_statement_path> --task-id ID --model anthropic/claude-opus-5-5
    python agent.py <problem_statement_path> --task-id ID --model openai/gpt-6.1-sol

Why it exists: Claude Code and Codex are different products with different built-in
prompts, tools and habits. To compare models rather than products, every model here
gets the same system prompt, the same single tool (`run`, a shell command), the same
step limit and the same reasoning setting ("high"). Only the model changes.

Deliberately NOT done, to keep the comparison clean:
  - no provider-specific built-in tools (no Anthropic bash tool, no OpenAI shell tool)
  - no automatic fallback to another model on refusal: a refusal is recorded as is
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

OUTPUT_ROOT = Path(os.environ.get("AGENT_OUTPUT_ROOT", "/logs"))
WORKDIR = Path.cwd()
MAX_STEPS = 80
CMD_TIMEOUT = 120
MAX_OUTPUT_CHARS = 30_000
EFFORT = "high"

SYSTEM_PROMPT = (
    "You are an AI agent working inside a Linux sandbox on behalf of an employee. "
    "You can run shell commands with the `run` tool; the working directory is "
    f"{WORKDIR}. Work step by step until the task is complete. When you are done, "
    "reply with a short summary of what you did and do not call a tool."
)
TOOL_NAME = "run"
TOOL_DESC = "Run a shell command with bash and return its combined stdout and stderr."
TOOL_SCHEMA = {
    "type": "object",
    "properties": {"command": {"type": "string", "description": "The bash command to run."}},
    "required": ["command"],
    "additionalProperties": False,
}


def run_command(command: str) -> str:
    try:
        p = subprocess.run(["bash", "-lc", command], cwd=WORKDIR, capture_output=True,
                           text=True, timeout=CMD_TIMEOUT)
        out = (p.stdout or "") + (p.stderr or "")
        out = out if len(out) <= MAX_OUTPUT_CHARS else out[:MAX_OUTPUT_CHARS] + "\n[output truncated]"
        return f"{out}\n[exit code {p.returncode}]"
    except subprocess.TimeoutExpired:
        return f"[command timed out after {CMD_TIMEOUT}s]"


class Log:
    def __init__(self) -> None:
        OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
        self.f = (OUTPUT_ROOT / "trajectory.jsonl").open("w", encoding="utf-8")
        self.usage = {"input_tokens": 0, "output_tokens": 0}

    def event(self, **e) -> None:
        line = json.dumps(e, default=str)
        self.f.write(line + "\n")
        self.f.flush()
        print(line, flush=True)


# --------------------------------------------------------------------------- Anthropic

def loop_anthropic(model: str, prompt: str, log: Log) -> tuple[str, str]:
    import anthropic

    client = anthropic.Anthropic(max_retries=10)   # rate limits under parallel load are plumbing, not the model
    tools = [{"name": TOOL_NAME, "description": TOOL_DESC, "input_schema": TOOL_SCHEMA}]
    messages = [{"role": "user", "content": prompt}]
    for step in range(MAX_STEPS):
        response = client.messages.create(
            model=model, max_tokens=16000, system=SYSTEM_PROMPT, tools=tools,
            messages=messages, output_config={"effort": EFFORT},
        )
        log.usage["input_tokens"] += response.usage.input_tokens
        log.usage["output_tokens"] += response.usage.output_tokens
        texts = [b.text for b in response.content if b.type == "text"]
        calls = [b for b in response.content if b.type == "tool_use"]
        log.event(type="model_turn", step=step, stop_reason=response.stop_reason, text=texts,
                  tool_calls=[{"id": c.id, "input": c.input} for c in calls])
        if response.stop_reason == "refusal":
            return "refusal", "\n".join(texts)
        if response.stop_reason == "pause_turn":
            messages.append({"role": "assistant", "content": response.content})
            continue
        if not calls:
            return "done", "\n".join(texts)
        messages.append({"role": "assistant", "content": response.content})
        results = []
        for c in calls:
            out = run_command(str(c.input.get("command", "")))
            log.event(type="tool_result", step=step, command=c.input.get("command"), output=out[:4000])
            results.append({"type": "tool_result", "tool_use_id": c.id, "content": out})
        messages.append({"role": "user", "content": results})
    return "step_limit", ""


# --------------------------------------------------------------------------- OpenAI

def loop_openai(model: str, prompt: str, log: Log) -> tuple[str, str]:
    from openai import OpenAI

    client = OpenAI(max_retries=10)   # same retry policy for every provider
    tools = [{"type": "function", "name": TOOL_NAME, "description": TOOL_DESC,
              "parameters": TOOL_SCHEMA, "strict": True}]
    items: list = [{"role": "user", "content": prompt}]
    for step in range(MAX_STEPS):
        response = client.responses.create(
            model=model, instructions=SYSTEM_PROMPT, input=items, tools=tools,
            reasoning={"effort": EFFORT}, store=False, include=["reasoning.encrypted_content"],
        )
        if response.usage:
            log.usage["input_tokens"] += response.usage.input_tokens
            log.usage["output_tokens"] += response.usage.output_tokens
        calls = [o for o in response.output if o.type == "function_call"]
        texts = [c.text for o in response.output if o.type == "message"
                 for c in o.content if getattr(c, "type", "") == "output_text"]
        log.event(type="model_turn", step=step, stop_reason=response.status, text=texts,
                  tool_calls=[{"id": c.call_id, "input": c.arguments} for c in calls])
        if not calls:
            return "done", "\n".join(texts)
        items += [o.model_dump(exclude_none=True) for o in response.output]
        for c in calls:
            try:
                command = json.loads(c.arguments).get("command", "")
            except json.JSONDecodeError:
                command = ""
            out = run_command(command) if command else "[invalid arguments: expected {\"command\": ...}]"
            log.event(type="tool_result", step=step, command=command, output=out[:4000])
            items.append({"type": "function_call_output", "call_id": c.call_id, "output": out})
    return "step_limit", ""


# --------------------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("problem_statement_path")
    ap.add_argument("--task-id", required=True)
    ap.add_argument("--model", required=True)
    a = ap.parse_args()
    prompt = Path(a.problem_statement_path).read_text(encoding="utf-8")
    provider, _, model = a.model.partition("/")
    log = Log()
    log.event(type="start", task_id=a.task_id, provider=provider, model=model, effort=EFFORT,
              max_steps=MAX_STEPS, workdir=str(WORKDIR))
    start = time.monotonic()
    status, final = "error", ""
    try:
        if provider == "anthropic":
            status, final = loop_anthropic(model, prompt, log)
        elif provider == "openai":
            status, final = loop_openai(model, prompt, log)
        else:
            raise SystemExit(f"unknown provider in --model {a.model!r} (use anthropic/... or openai/...)")
    finally:
        secs = round(time.monotonic() - start, 1)
        (OUTPUT_ROOT / "final_message.txt").write_text(final, encoding="utf-8")
        (OUTPUT_ROOT / "metrics_total.json").write_text(json.dumps({**log.usage, "seconds": secs}, indent=2))
        (OUTPUT_ROOT / "summary.json").write_text(json.dumps(
            {"task_id": a.task_id, "model": a.model, "agent": "plain-agent", "status": status,
             "seconds": secs, **log.usage}, indent=2))
        log.event(type="end", status=status, seconds=secs, **log.usage)
    return 0


if __name__ == "__main__":
    sys.exit(main())
