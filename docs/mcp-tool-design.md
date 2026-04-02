# MCP Tool Design Guidelines

## Naming

- Use `snake_case` with a verb prefix: `send_`, `get_`, `create_`, `list_`.
- Style: `verb_noun` or `service_verb` (e.g. `dingtalk_send_message`).
- Avoid leaking implementation details in the name (e.g. transport type, wire format).

## Description

Write descriptions from the agent's perspective — tell it *when* to call the tool, not how it works internally. Emphasis varies by tool type:

| Tool type | Focus |
|---|---|
| Action (send, write, execute) | When to use it + what outcome it produces |
| Query (read, search, fetch) | What data it returns + when the caller needs it |
| Transform (parse, format, compute) | Input → output mapping |

Example (action tool):

```
Send a formatted notification to the DingTalk group.

Use this to report task progress, completion, errors, or any update
that the user or team should be aware of.
```

## Parameter Descriptions

MCP returns a JSON Schema (names + types) to the agent automatically. Only add parameter descriptions when the name alone is ambiguous. When a description is needed, use `Annotated` so it appears in the schema — not a docstring `Args:` block which the agent cannot see:

```python
from typing import Annotated

def dingtalk_send_message(
    title: Annotated[str, "Short subject shown in DingTalk notification previews"],
    ...
```
