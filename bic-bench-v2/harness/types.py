from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


JsonObject = dict[str, Any]


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: JsonObject


@dataclass(frozen=True)
class AgentTurn:
    assistant_text: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    raw_response: Any = None


@dataclass(frozen=True)
class AgentRequest:
    messages: tuple[JsonObject, ...]
    tools: tuple[JsonObject, ...]
    metadata: JsonObject


class AgentAdapter(Protocol):
    name: str
    mode: str

    def generate(self, request: AgentRequest) -> AgentTurn:
        """Return one normalized assistant turn."""


@dataclass
class ActionRecord:
    index: int
    action: str
    fields: JsonObject
    tool_name: str = "business_action"
    status: str = "recorded"


@dataclass
class LoopResult:
    case_id: str
    trial: int
    agent_name: str
    agent_mode: str
    actions: list[ActionRecord] = field(default_factory=list)
    final_response: str = ""
    trajectory: JsonObject = field(default_factory=dict)
