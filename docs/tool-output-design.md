# Tool Output Design

## Core Principle

A tool's output should only contain information the model can act on.
Never expose internal implementation details that the model has no parameter
to act upon — doing so causes the model to hallucinate actions or loop on
unrecoverable errors.

## Output Categories

Every tool returns one of three shapes.

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

A predictable, named failure that the model could recover from (e.g. wrong
input, invalid state). The hint must tell the model exactly what to do — never
ask it to "assess" or "evaluate", because that leads to guessing.

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

### 3. Internal Error

An unexpected or unrecoverable failure inside the tool (e.g. downstream API
is down, server misconfiguration, unexpected exception). The model cannot fix
this — it should report it and stop.

```json
{
  "success": false,
  "error_type": "internal_error",
  "message": "downstream API returned 500 while processing request",
  "hint": "An internal error occurred. Notify the user with the message above and stop."
}
```

**Rules for internal errors:**
- Never expose raw internal state (e.g. available options the model cannot select from).
- The `message` is for the human to read, not for the model to act on.
- The `hint` must instruct the model to stop and surface the error.

## What NOT to Include in Output

| Field                                                           | Reason to exclude                                                                         |
| --------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| Internal option lists (e.g. available transitions, enum values) | Model has no parameter to pass them — exposing these causes it to misuse other parameters |
| Internal state fields (e.g. current status, raw config)         | Model cannot change internal state directly via this tool                                 |
| Raw downstream API errors                                       | Too noisy; wrap in `message` under `internal_error` instead                               |
| Open-ended hints ("assess whether X", "check if Y applies")     | Leads to guessing and retry loops                                                         |

## Why the Model Must Not Control Internal Options Directly

Tool parameters define what the model is **allowed** to control.
If a tool resolves internal options (e.g. which workflow transition to trigger,
which queue to route to) based on its own configuration, those options must
not appear in the output — the server owns that decision, not the model.

Exposing internal option lists in output (or as parameters) bypasses the
server's validation layer and gives the model control it was not designed to have.
Configuration of those options belongs in server config (env vars, config files),
owned by the operator.

## Example: Jira Workflow Tools

`jira_accept_issue(issue_key)` — the server internally resolves which Jira
workflow transition represents "accept" based on `JIRA_ACCEPT_TRANSITIONS` config.
The model only passes `issue_key`. If no matching transition is found, the tool
returns `internal_error` (server misconfiguration), not a list of available
transitions for the model to choose from.
