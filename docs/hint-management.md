# Hint Management

## Background

Tool output hints are short instructions embedded in error responses that tell the
agent what to do next. As the number of tools grows, hints written inline inside
each tool become hard to keep consistent and review. This document records the
decisions made around hint content and where they live in the codebase.

---

## Decision 1 — Centralize hints in `hints.py`

**What:** All hint strings are defined as module-level constants in
`src/work_assistant_mcp/hints.py`, grouped by domain. Tool implementations
import from there instead of writing strings inline.

**Why:** Inline strings spread across multiple files make it impossible to audit
hint quality in one pass, or to apply a wording change consistently. A single
file makes every hint visible at a glance and keeps review focused.

**Structure:**
```
hints.py
  # common
  INTERNAL_ERROR = "..."

  # jira
  JIRA_ISSUE_NOT_FOUND = "..."
  JIRA_ACCEPT_BEFORE_RESOLVE = "..."

  # dingtalk
  DINGTALK_INTERNAL_ERROR = "..."
```

---

## Decision 2 — Retry limit only on `internal_error`

**What:** `internal_error` hints instruct the agent to retry up to 2 times before
stopping. `invalid_input` and `issue_not_found` hints do not include a retry
count.

**Why:**

- `internal_error` is typically transient (network blip, downstream API
  temporarily unavailable). A bounded retry makes sense.
- `invalid_input` means the agent passed a bad parameter. The fix is to correct
  the parameter and retry immediately — a count is irrelevant and would add
  noise.
- `issue_not_found` is a definitive negative. Retrying cannot help and risks a
  loop.

**Standard wording for `internal_error`:**
```
An internal error occurred. Retry up to 2 times;
if still failing, stop and notify the user with the message above.
```

**Exception — dingtalk `internal_error`:** The DingTalk tool is itself the
notification channel. Telling it to "notify the user" on failure is circular.
Its hint instead reads:
```
An internal error occurred. Stop and tell the user in your reply:
the notification could not be sent.
```

---

## Decision 3 — Avoid hardcoding tool names in hints

**What:** Hints must not reference specific tool names (e.g.
`"call jira_accept_issue first"`).

**Why:** Hardcoding a tool name removes the agent's ability to reason about what
is available in the current session. If the named tool is not loaded, the agent
will either fail or hallucinate an invocation. Hinting at the *intent* instead
lets the agent select the right tool itself.

**Example — resolve before accept:**

Bad:
```
If it is still in Todo, call jira_accept_issue first.
```

Good:
```
If it is still in Todo, check whether any available tool can first
move it to an Accepted state, then retry.
```

---

## Decision 4 — Unified exception fallback in `_wrap_with_logging`

**What:** The logging wrapper in `server.py` catches unhandled exceptions and
returns a structured `internal_error` dict instead of re-raising.

**Why:** Without this, any uncaught exception propagates to FastMCP, which
returns an `isError: true` protocol-level error. The agent receives no hint and
must guess what to do. By catching here, every failure path — whether handled
inside the tool or not — produces a response with a consistent hint.

**Trade-off acknowledged:** Catching and returning converts a protocol-level
error (`isError: true`) into a content-level error (`success: false`). Some
MCP clients treat `isError: true` specially (e.g. automatic retry). That
mechanism is bypassed here. This is acceptable because our hint already encodes
the retry policy explicitly; we do not want to rely on client-side behaviour
that may differ across hosts.

`BaseException` subclasses (`KeyboardInterrupt`, `SystemExit`) are not affected
because the wrapper uses `except Exception`.
