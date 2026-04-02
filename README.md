## work-assistant-mcp

An MCP server for work-related tools used by local agents.

Current tools:

- `dingtalk_send_markdown`
- `jira_get_current_fault`
- `jira_accept_issue`
- `jira_resolve_issue`

## What This Server Is For

Use this server when a local agent needs to send work updates into a DingTalk group, for example:

- task progress updates
- completion notifications
- error reports
- manual smoke-test messages

Use this server when a local agent needs to interact with Jira fault issues, for example:

- fetching the latest open fault assigned to the current user
- accepting a fault when work starts
- resolving a fault when the fix is ready for verification

## Configuration

Configuration is split into two files by sensitivity:

### `config.yaml` — non-sensitive settings

Controls which integrations are enabled and sets logging, server options, and Jira policy. Committed to the repository.

```yaml
server:
  name: work-assistant-mcp
  instructions: "A work-focused MCP server with notification tools for local agents."

logging:
  dir: logs
  level: info   # debug | info | warning | error

integrations:
  enabled:
    - dingtalk
    # - jira
    # comment out any line to disable that integration at startup

jira:
  accept_transitions:
    - 已接收
    - Accept
  resolve_transitions:
    - 已解决
    - Resolved
  attachments:
    max_images: 5
    max_bytes_per_image: 1048576
```

To disable an integration without removing it from the codebase, comment out its name in `integrations.enabled`.
When `jira` is enabled, `jira.accept_transitions` and `jira.resolve_transitions` must be configured explicitly.

### `.env` — sensitive credentials

Copy `.env.example` to `.env` and fill in the required credentials:

```env
DINGTALK_WEBHOOK_URL=https://oapi.dingtalk.com/robot/send?access_token=your_token_here
DINGTALK_SECRET=SECxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
JIRA_BASE_URL=https://your-jira-instance.example.com
JIRA_EMAIL=you@example.com
JIRA_API_TOKEN=your_jira_api_token_here
JIRA_PROJECT_KEYS=PROJECT1,PROJECT2
```

Notes:

- `DINGTALK_WEBHOOK_URL` is required.
- `DINGTALK_SECRET` is optional only if the robot does not have "加签" enabled.
- If "加签" is enabled in DingTalk, `DINGTALK_SECRET` must be set or sends will fail with a signature mismatch error.
- `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`, and `JIRA_PROJECT_KEYS` are required only when the `jira` integration is enabled.
- `JIRA_PROJECT_KEYS` is a comma-separated allowlist of Jira projects this server can query.
- Keep real tokens and secrets only in local `.env` or environment variables. Do not commit them.

### Environment variable overrides

Environment variables take priority over `config.yaml`. This is useful for CI/CD or Docker deployments:

| Variable                   | Overrides       |
| -------------------------- | --------------- |
| `WORK_ASSISTANT_LOG_DIR`   | `logging.dir`   |
| `WORK_ASSISTANT_LOG_LEVEL` | `logging.level` |

## Adding a New Tool

1. Implement `register_<name>_tools(mcp: FastMCP, settings: Settings)` in `src/work_assistant_mcp/tools/<name>.py`.
2. Add an entry to `INTEGRATION_REGISTRY` in `src/work_assistant_mcp/tools/__init__.py`.
3. Add the integration name to `integrations.enabled` in `config.yaml`.

## Agent Setup

Point your MCP client or agent at the packaged entry point:

```json
{
  "mcpServers": {
    "work-assistant": {
      "command": "uv",
      "args": ["run", "work-assistant-mcp"],
      "cwd": "/absolute/path/to/work-assistant-mcp"
    }
  }
}
```

If your MCP client starts servers from the current repository root, `cwd` can usually be omitted.

Agent guidance:

- Use `dingtalk_send_markdown` when the user or team should be notified in DingTalk.
- Set `title` to a short subject line.
- Set `markdown` to the full message body.
- Do not send routine chatter unless the user asked for a notification or the workflow clearly requires one.
- Call `jira_get_current_fault` to retrieve the latest open fault assigned to the current user, including image attachments encoded as base64 when available.
- Call `jira_accept_issue` once the issue is understood and work is starting.
- Call `jira_resolve_issue` once the fix is complete and ready for verification.

## Run

```bash
uv run work-assistant-mcp
```

## Validate Locally

Use `scripts/preview_tool.py` to preview and debug tools registered by this server.

List tools:

```bash
uv run python scripts/preview_tool.py list
```

Show one tool's schema:

```bash
uv run python scripts/preview_tool.py describe dingtalk_send_markdown
```

Call one tool:

```bash
uv run python scripts/preview_tool.py call dingtalk_send_markdown \
  --args '{"title":"Smoke Test","markdown":"hello from local preview"}'
```

Run smoke tests:

```bash
uv run pytest
```
