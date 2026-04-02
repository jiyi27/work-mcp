# MCP Tool Design

## Naming

- Use `snake_case` with a verb prefix: `send_`, `get_`, `create_`, `list_`.
- Style: `verb_noun` or `service_verb` (e.g. `dingtalk_send_message`).
- Avoid leaking implementation details in the name (e.g. transport type, wire format).

## Description

Write descriptions from the agent's perspective — tell it *when* to call the tool, not how it works internally. Emphasis varies by tool type:

| Tool type                          | Focus                                           |
| ---------------------------------- | ----------------------------------------------- |
| Action (send, write, execute)      | When to use it + what outcome it produces       |
| Query (read, search, fetch)        | What data it returns + when the caller needs it |
| Transform (parse, format, compute) | Input → output mapping                          |

Example (action tool):

```
Send a formatted notification to the DingTalk group.

Use this to report task progress, completion, errors, or any update
that the user or team should be aware of.
```

## Parameters

MCP returns a JSON Schema (names + types) to the agent automatically. Only add parameter descriptions when the name alone is ambiguous. When a description is needed, use `Annotated` so it appears in the schema — not a docstring `Args:` block which the agent cannot see:

```python
from typing import Annotated

def dingtalk_send_message(
    title: Annotated[str, "Short subject shown in DingTalk notification previews"],
    ...
```

## Output Contract

A tool's output should only contain information the model can act on. Never expose internal implementation details that the model has no parameter to act upon — doing so causes the model to hallucinate actions or loop on unrecoverable errors.

### Error Feedback as a Control Signal

Error feedback in tool output is not a logging concern — it is a control signal that tells the agent what to do next. Relying on system instructions alone to handle error cases is insufficient: system instructions are written before runtime and cannot anticipate the specific failure, resource, or state that a tool encountered. Structured error output closes that gap at the point where the information is available.

Errors must be categorized so the agent knows whether it can recover. The tool should only return structured error output for failures it understands at the tool or integration boundary. Genuinely unexpected exceptions should continue to propagate through MCP as protocol-level errors rather than being converted into normal tool results.

### 1. Success

The operation completed. Include only what the model needs to continue the workflow.

```json
{
  "success": true,
  "id": "<resource identifier>"
}
```

No extra fields. The model should proceed to the next step.

### 2. Domain Error

A predictable, named failure the model can act on (e.g. wrong input, resource not found, invalid state). The hint must tell the model exactly what to do — never ask it to "assess" or "evaluate", because that leads to guessing.

```json
{
  "success": false,
  "error_type": "resource_not_found",
  "hint": "Resource not found. Do not guess the identifier. Notify the user and stop."
}
```

**Rules for domain errors:**
- Use a stable `error_type` string (machine-readable).
- The `hint` must be a direct instruction, not an open-ended suggestion.
- Only include fields the model can use to correct its next call.
- Do not add retry counts unless the failure is actually transient.

### 3. Internal Error

A known but non-recoverable integration failure inside the tool (e.g. downstream API failure, server misconfiguration, missing configured workflow mapping). The model cannot directly fix the underlying problem, but the failure is still understood well enough that the tool can return a stable shape and a clear hint.

```json
{
  "success": false,
  "error_type": "internal_error",
  "message": "downstream API returned 500 while processing request",
  "hint": "An internal error occurred. Retry up to 2 times; if still failing, stop and notify the user with the message above."
}
```

**Rules for internal errors:**
- Never expose raw internal state (e.g. available options the model cannot select from).
- The `message` is for the human to read, not for the model to act on.
- Use this shape for expected boundary failures that the tool explicitly handles.
- The `hint` may include a bounded retry policy when the failure is plausibly transient.

### Unexpected Exceptions

This document defines the content-level output contract of a tool. It does not replace MCP's own error channel.

If the tool hits a genuinely unexpected exception such as a programming defect or an unhandled runtime error, let that exception propagate. Do not catch every `Exception` at the server wrapper layer just to force a structured `internal_error` result. Doing so changes MCP-visible behavior and can hide real bugs behind a generic retryable error.

## What NOT to Include in Output

| Field                                                           | Reason to exclude                                                                                                                                        |
| --------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Internal option lists (e.g. available transitions, enum values) | Model has no parameter to pass them — exposing these causes it to misuse other parameters; configuration belongs in server config, owned by the operator |
| Internal state fields (e.g. current status, raw config)         | Model cannot change internal state directly via this tool                                                                                                |
| Raw downstream API errors                                       | Too noisy; wrap in `message` under `internal_error` instead                                                                                              |
| Open-ended hints ("assess whether X", "check if Y applies")     | Leads to guessing and retry loops                                                                                                                        |
| Tool-selection speculation                                      | Prefer describing the intended next action unless a concrete tool name is part of a fixed workflow                                                       |

## Example: Jira Workflow Tools

`jira_accept_issue(issue_key)` — the server internally resolves which Jira workflow transition represents "accept" based on `JIRA_ACCEPT_TRANSITIONS` config. The model only passes `issue_key`. If no matching transition is found, the tool returns `internal_error` (server misconfiguration), not a list of available transitions for the model to choose from.
