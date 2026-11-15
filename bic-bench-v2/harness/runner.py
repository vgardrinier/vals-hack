from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from scoring.hybrid import score_trial
from scoring.judge import Judge

from .prompts import LOOP_VERSION, SYSTEM_PROMPT, build_user_prompt
from .tools import TOOL_DEFINITIONS, BusinessToolEnvironment
from .types import AgentAdapter, AgentRequest, LoopResult


AgentFactory = Callable[[dict[str, Any], int], AgentAdapter]


@dataclass(frozen=True)
class RunnerConfig:
    trials: int = 5
    max_steps: int = 8
    concurrency: int = 1
    run_id: str = ""

    def __post_init__(self) -> None:
        if self.trials < 1:
            raise ValueError("trials must be at least 1")
        if self.max_steps < 1:
            raise ValueError("max_steps must be at least 1")
        if not 1 <= self.concurrency <= 5:
            raise ValueError("concurrency must be between 1 and 5")


class EvaluationRunner:
    def __init__(
        self,
        config: RunnerConfig,
        agent_factory: AgentFactory,
        judge: Judge,
        output_root: Path,
    ) -> None:
        self.config = config
        self.agent_factory = agent_factory
        self.judge = judge
        self.output_root = output_root

    def run(self, cases: list[dict[str, Any]]) -> tuple[dict[str, Any], Path]:
        if not cases:
            raise ValueError("at least one case is required")
        run_id = self.config.run_id or datetime.now(timezone.utc).strftime("run-%Y%m%dT%H%M%SZ")
        run_dir = self.output_root / run_id
        trajectory_root = run_dir / "trajectories"
        trajectory_root.mkdir(parents=True, exist_ok=False)

        started_at = _utc_now()
        jobs = [
            (case, trial)
            for case in cases
            for trial in range(1, self.config.trials + 1)
        ]
        results = []
        with ThreadPoolExecutor(max_workers=self.config.concurrency) as executor:
            futures = {
                executor.submit(self._run_one, case, trial): (case["id"], trial)
                for case, trial in jobs
            }
            for future in as_completed(futures):
                results.append(future.result())
        results.sort(key=lambda item: (item["case_id"], item["trial"]))

        for result in results:
            case_dir = trajectory_root / result["case_id"]
            case_dir.mkdir(parents=True, exist_ok=True)
            trajectory_path = case_dir / f"trial-{result['trial']:03d}.json"
            trajectory_path.write_text(
                json.dumps(result.pop("trajectory"), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            result["trajectory_path"] = trajectory_path.relative_to(run_dir).as_posix()

        sample_agent = self.agent_factory(cases[0], 1)
        payload = {
            "schema_version": "bic-run-v2.0",
            "run_id": run_id,
            "started_at": started_at,
            "completed_at": _utc_now(),
            "loop_version": LOOP_VERSION,
            "agent": {"name": sample_agent.name, "mode": sample_agent.mode},
            "judge": {"name": self.judge.name},
            "config": asdict(self.config) | {"run_id": run_id},
            "case_count": len(cases),
            "trial_count": len(results),
            "case_ids": [case["id"] for case in cases],
            "trials": results,
        }
        (run_dir / "run.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return payload, run_dir

    def _run_one(self, case: dict[str, Any], trial: int) -> dict[str, Any]:
        agent = self.agent_factory(case, trial)
        loop_result = run_agent_loop(
            case=case,
            trial=trial,
            agent=agent,
            max_steps=self.config.max_steps,
        )
        actions = [asdict(action) for action in loop_result.actions]
        score = score_trial(
            case=case,
            actions=actions,
            final_response=loop_result.final_response,
            judge=self.judge,
        )
        return {
            "case_id": case["id"],
            "trial": trial,
            "difficulty": case["difficulty"]["tier"],
            "industry": case["industry"],
            "category": case["category"],
            "score": score.as_dict(),
            "agent_usage": _collect_agent_usage(loop_result.trajectory),
            "trajectory": loop_result.trajectory,
        }


def run_agent_loop(
    case: dict[str, Any],
    trial: int,
    agent: AgentAdapter,
    max_steps: int,
) -> LoopResult:
    environment = BusinessToolEnvironment()
    user_prompt = build_user_prompt(case, agent.mode)
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    trajectory_steps = []
    started_at = _utc_now()
    last_text = ""

    for step in range(1, max_steps + 1):
        request = AgentRequest(
            messages=tuple(messages),
            tools=TOOL_DEFINITIONS,
            metadata={
                "benchmark": "bic-bench-v2",
                "loop_version": LOOP_VERSION,
                "case_id": case["id"],
                "trial": trial,
                "step": step,
                "max_steps": max_steps,
                "offline_environment": True,
            },
        )
        turn = agent.generate(request)
        last_text = turn.assistant_text
        calls = [
            {"name": call.name, "arguments": call.arguments}
            for call in turn.tool_calls
        ]
        messages.append(
            {
                "role": "assistant",
                "content": turn.assistant_text,
                "tool_calls": calls,
            }
        )
        tool_results = []
        for call in turn.tool_calls:
            result = environment.execute(call.name, call.arguments)
            tool_result = {"name": call.name, "result": result}
            tool_results.append(tool_result)
            messages.append({"role": "tool", **tool_result})
            if environment.finished:
                break
        trajectory_steps.append(
            {
                "step": step,
                "assistant_text": turn.assistant_text,
                "tool_calls": calls,
                "tool_results": tool_results,
                "raw_response": _json_safe(turn.raw_response),
            }
        )
        if environment.finished:
            break

    final_response = environment.final_response or last_text
    terminated = "finish" if environment.finished else "max_steps"
    trajectory = {
        "schema_version": "bic-trajectory-v2.0",
        "case_id": case["id"],
        "trial": trial,
        "agent": {"name": agent.name, "mode": agent.mode},
        "loop_version": LOOP_VERSION,
        "started_at": started_at,
        "completed_at": _utc_now(),
        "max_steps": max_steps,
        "terminated": terminated,
        "system_prompt": SYSTEM_PROMPT,
        "user_prompt": user_prompt,
        "tool_definitions": TOOL_DEFINITIONS,
        "steps": trajectory_steps,
        "recorded_actions": [asdict(action) for action in environment.actions],
        "final_response": final_response,
    }
    return LoopResult(
        case_id=case["id"],
        trial=trial,
        agent_name=agent.name,
        agent_mode=agent.mode,
        actions=environment.actions,
        final_response=final_response,
        trajectory=trajectory,
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_safe(value: Any) -> Any:
    try:
        json.dumps(value)
    except (TypeError, ValueError):
        return repr(value)
    return value


def _collect_agent_usage(trajectory: dict[str, Any]) -> dict[str, Any]:
    calls = []
    for step in trajectory["steps"]:
        raw = step.get("raw_response")
        if isinstance(raw, dict) and isinstance(raw.get("_usage"), dict):
            calls.append(raw["_usage"])
    return {
        "calls": len(calls),
        "input_tokens": sum(int(call.get("input_tokens", 0)) for call in calls),
        "cached_input_tokens": sum(int(call.get("cached_input_tokens", 0)) for call in calls),
        "output_tokens": sum(int(call.get("output_tokens", 0)) for call in calls),
        "estimated_cost_usd": round(
            sum(float(call.get("estimated_cost_usd") or 0) for call in calls), 8
        ),
        "elapsed_seconds": round(
            sum(float(call.get("elapsed_seconds", 0)) for call in calls), 3
        ),
        "models": sorted({str(call.get("model")) for call in calls if call.get("model")}),
    }
