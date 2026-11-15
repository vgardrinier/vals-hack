# Fixed evaluation protocol

## Invariants

Every target model receives the same:

- system prompt from `harness/prompts.py`;
- ordered context documents and task template;
- `business_action` and `finish` tool definitions, including one fixed benchmark-wide action catalog;
- maximum step count;
- offline simulated action environment;
- hidden verifier data exclusion;
- trajectory schema and hybrid scoring formula.

The target model never receives `implicit_constraints`, `expected_behavior`, `failure_criteria`, or the case-to-assertion mapping in `scoring_blueprint`. Those fields are loaded only by the scorer and local oracle baselines. The `business_action.action` enum exposes the same union of canonical operations and field-key signatures for all 70 tasks, analogous to a stable enterprise API catalog; it does not identify which operation is correct for a case or disclose expected field values.

## Agent loop

1. Load visible context documents and the public task.
2. Build the versioned system and user prompts.
3. Ask the adapter for one normalized turn.
4. Record assistant text and tool calls.
5. Execute tool calls in the local simulator.
6. Append tool results to the conversation.
7. Stop on `finish`; otherwise repeat until `max_steps`.
8. Persist the complete prompt, tools, normalized turns, raw adapter responses, tool results, actions, final response, and termination reason.
9. Apply deterministic forbidden and required assertions.
10. Skip semantic judging after a hard failure; otherwise invoke the versioned judge rubric.

## Adapter contract

`--agent command` launches one subprocess per model turn. The harness writes one JSON object to stdin:

```json
{
  "messages": [{"role": "system", "content": "..."}],
  "tools": [{"name": "business_action", "input_schema": {}}],
  "metadata": {"case_id": "...", "trial": 1, "step": 1},
  "response_mode": "tool"
}
```

The command returns one JSON object on stdout:

```json
{
  "assistant_text": "Concise decision explanation",
  "tool_calls": [
    {
      "name": "business_action",
      "arguments": {"action": "create_retest_request", "fields": {"lot_id": "MG-442"}}
    },
    {"name": "finish", "arguments": {"response": "Placed the lot on hold and requested retesting."}}
  ]
}
```

For pure-text models, use `--agent-mode text`. The prompt requests the same normalized JSON envelope. Provider-specific scripts may use native tool calling internally, but they must emit this provider-neutral envelope.

## Judge contract

`--judge command` writes the versioned rubric, hidden ground truth, recorded actions, and final response to a judge subprocess. The judge returns:

```json
{
  "constraint_awareness": 1,
  "alternative_quality": 0.5,
  "awareness_explanation": "...",
  "alternative_explanation": "..."
}
```

Scores must be exactly `0`, `0.5`, or `1`. Leaderboard mode refuses the heuristic smoke-test judge.

## Trials and concurrency

- Normal default: 5 trials per case.
- Leaderboard mode: exactly 8 trials per case.
- Concurrency: configurable from 1 to 5 and capped at 5.
- Full 70-case execution requires explicit `--all`.
- Reports use population standard deviation. The overall deviation is calculated across per-trial aggregate case means.
