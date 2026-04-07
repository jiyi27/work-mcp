# MCP Tool Design

## Naming

- Use `snake_case` with a verb prefix: `send_`, `get_`, `create_`, `list_`.
- Style: `verb_noun` or `service_verb_noun` (e.g. `get_issue`, `dingtalk_send_message`).
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

FastMCP returns a JSON Schema (names + types) to the agent automatically. Only add parameter descriptions when the name alone is ambiguous. When a description is needed, use `Annotated` so it appears in the schema — not a docstring `Args:` block which the agent cannot see:

```python
from typing import Annotated

def dingtalk_send_message(
    title: Annotated[str, "Short subject shown in DingTalk notification previews"],
    ...
```

## What a Tool Should Return

A tool's output is a control signal, not a log entry. It tells the agent what happened and what to do next. Only include information the agent can actually act on. Never expose internal implementation details that the agent has no parameter to influence — doing so causes it to hallucinate actions or loop on unrecoverable errors.

System instructions alone cannot handle tool failures reliably: they are written before runtime and cannot anticipate the specific failure, resource, or state a tool encounters. Structured output closes that gap at the point where the information is available.

### Deciding which shape to return

```
Did the operation complete successfully?
  Yes → return Success
  No → can the caller fix it by changing the call arguments?
    Yes → return Recoverable Failure
    No → does the tool recognize and understand the failure?
      Yes → return Non-Recoverable Failure
      No → let the exception propagate (do not catch it)
```

### 1. Success

The operation completed. Include only what the agent needs to continue the workflow.

```json
{
  "success": true,
  "id": "<resource identifier>"
}
```

No extra fields. The agent should proceed to the next step.

### 2. Recoverable Failure — the caller can fix it

A predictable, named failure the agent can act on by changing its next call (e.g. wrong input, resource not found, invalid state). The hint must tell the agent exactly what to do — never ask it to "assess" or "evaluate", because that leads to guessing.

```json
{
  "success": false,
  "error_type": "resource_not_found",
  "hint": "Resource not found. Do not guess the identifier. Notify the user and stop."
}
```

**Rules:**
- Use a stable `error_type` string (machine-readable).
- The `hint` must be a direct instruction, not an open-ended suggestion.
- Only include fields the agent can use to correct its next call.
- Do not add retry counts unless the failure is actually transient.

### 3. Non-Recoverable Failure — the tool understands it but the caller cannot fix it

A known integration failure the agent cannot resolve by changing arguments (e.g. downstream API failure, server misconfiguration, missing configured workflow mapping). The failure is understood well enough that the tool can return a stable shape and a clear hint.

```json
{
  "success": false,
  "error_type": "internal_error",
  "message": "downstream API returned 500 while processing request",
  "hint": "An internal error occurred. Retry up to 2 times; if still failing, stop and notify the user with the message above."
}
```

**Rules:**
- Never expose raw internal state unless that state is the direct reason the tool could not complete and the agent must stop and notify the user.
- The `message` provides critical context for both the agent and the human. Preserve detailed upstream error reasons (e.g., timeout descriptions, HTTP error body summaries) in this field. Do not swallow them with generic wrappers like "HTTP 500 error", which prevent diagnosis.
- The `hint` may include a bounded retry policy when the failure is plausibly transient.

### 4. Unexpected Exceptions — let them propagate

If the tool hits a genuinely unexpected exception (programming defect, unhandled runtime error), let it propagate. Do not catch every `Exception` at the server wrapper layer just to force a structured result. Doing so hides real bugs behind a generic retryable error and changes MCP-visible behavior in ways that are hard to debug.

This document defines the content-level output contract. It does not replace MCP's own error channel.

## What NOT to Include in Output

| Field                                                           | Reason to exclude                                                                                                                                        |
| --------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Internal option lists unrelated to the failure                  | Agent has no parameter to pass them — exposing these causes it to misuse other parameters; configuration belongs in server config, owned by the operator |
| Internal state fields unrelated to the failure                  | Agent cannot change internal state directly via this tool                                                                                                |
| Raw downstream API errors                                       | Too noisy; wrap in `message` under non-recoverable failure instead                                                                                       |
| Open-ended hints ("assess whether X", "check if Y applies")     | Leads to guessing and retry loops                                                                                                                        |
| Tool-selection speculation                                      | Prefer describing the intended next action unless a concrete tool name is part of a fixed workflow                                                       |

## Example: Jira Workflow Tools

`jira_start_issue(issue_key)` — the server reads `jira.start_target_status`, fetches the issue's currently available Jira transitions, and executes the single transition whose destination status matches the configured target. If no transition reaches that status, or multiple transitions do, the tool returns a structured failure with the current status and available target statuses so the agent can stop and notify the user cleanly.
