## work-mcp

An MCP server for work-related tools used by local agents.

Tools are grouped by plugin. Each plugin is enabled or disabled as a unit in `config.yaml`.

| Plugin | Tools                                                                    |
| ----------- | ------------------------------------------------------------------- |
| `database`  | `db_list_databases`, `db_list_tables`, `db_get_table_schema`, `db_execute_query` |
| `dingtalk`  | `dingtalk_send_markdown`                                            |
| `jira`      | `jira_get_latest_assigned_issue`, `jira_get_attachment_image`, `jira_start_issue`, `jira_resolve_issue` |
| `log_search` | `list_log_files`, `search_log` |

## Configuration

Configuration is intentionally split by sensitivity, not by override priority.

- `.env` contains sensitive credentials only.
- `config.yaml` contains non-sensitive behavior and plugin settings only.
- A single setting should be defined in one place only. This project does not use environment variables to override `config.yaml`.
- Server startup mode is not stored in `config.yaml`. The packaged command defaults to `stdio`; use CLI flags or `make` targets when you want HTTP.

To disable a plugin and all its tools, comment out its name in `plugins.enabled` in `config.yaml`.

### Startup Health Checks

Runtime dependency probes are controlled in `config.yaml`:

```yaml
startup:
  healthcheck:
    enabled: false
    timeout_seconds: 10
```

- `startup.healthcheck.enabled` defaults to `false`. When enabled, server startup fails fast if a supported plugin's live dependency check fails.
- `startup.healthcheck.timeout_seconds` applies to each startup probe and defaults to `10`.
- This repository's checked-in `config.yaml` enables startup health checks for local use.
- Today, dynamic startup checks are implemented for `jira` and `database`. Other plugins still use static config validation only.

### Database

Configure a read-only SQL Server account for live debugging queries.

**1. Set credentials in `.env`:**

```env
DB_TYPE=sqlserver
DB_HOST=your-sqlserver-host.example.com
DB_PORT=1433
DB_USER=readonly_user
DB_PASSWORD=your_password_here
DB_NAME=master
DB_DRIVER=ODBC Driver 18 for SQL Server
DB_TRUST_SERVER_CERTIFICATE=false
DB_CONNECT_TIMEOUT_SECONDS=5
```

- `DB_USER` must be a read-only database account. Tool-layer SQL validation is only defense in depth and is not the primary safety boundary.
- `DB_NAME` is the default database used for connection bootstrap. The tools can still inspect other visible databases.
- `DB_DRIVER` must match an installed ODBC driver on the host machine. For SQL Server, install the Microsoft ODBC Driver first.
- `DB_TRUST_SERVER_CERTIFICATE=true` is only appropriate for environments where you intentionally bypass certificate validation.
- When `startup.healthcheck.enabled=true`, the database plugin performs a live startup probe against the configured database driver and executes a lightweight SQL query against `DB_NAME`. Startup stops if the connection or query fails.

**2. Enable in `config.yaml`:**

```yaml
plugins:
  enabled:
    - database
```

**3. Use the tools in this order when exploring data:**

- `db_list_databases`
- `db_list_tables`
- `db_get_table_schema`
- `db_execute_query`

`db_execute_query` only accepts a single `SELECT` statement and caps returned rows.

### DingTalk

**1. Create a robot** — open the group settings in DingTalk → 机器人管理 → add a 自定义 webhook robot. Copy the webhook URL. If you enable 加签, also copy the signing secret.

**2. Set credentials in `.env`:**

```env
DINGTALK_WEBHOOK_URL=https://oapi.dingtalk.com/robot/send?access_token=your_token_here
DINGTALK_SECRET=SECxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

`DINGTALK_SECRET` is only required when the robot has 加签 enabled. If it is required but missing, sends will fail with a signature mismatch error.

**3. Enable in `config.yaml`:**

```yaml
plugins:
  enabled:
    - dingtalk
```

### Jira

**1. Set credentials in `.env`:**

```env
JIRA_BASE_URL=https://your-jira-instance.example.com
JIRA_API_TOKEN=your_jira_api_token_here
JIRA_PROJECT_KEY=PROJECT1
```

- `JIRA_API_TOKEN` — create one at your Jira profile → Personal Access Tokens.
- `JIRA_PROJECT_KEY` — the short key for the project this server is allowed to query and update (e.g. `IOS`, `PROJECT1`).
- When `startup.healthcheck.enabled=true`, the Jira plugin probes `GET /rest/api/2/serverInfo` and `GET /rest/api/2/myself` using the configured base URL and token. Startup stops if Jira is unreachable or authentication fails.

**2. Discover your workflow status names:**

```bash
uv run python scripts/inspect_jira_issue_workflow.py YOUR-123
```

This prints every status name and available transition for that issue. Use the output to fill in the next step.

**3. Configure `config.yaml`:**

```yaml
plugins:
  enabled:
    - jira

jira:
  latest_assigned_statuses:  # statuses that jira_get_latest_assigned_issue will return
    - 待处理
    - 已接收
    - 处理中
  start_target_status: 已接收    # target status for jira_start_issue
  resolve_target_status: 已解决  # target status for jira_resolve_issue
  attachments:
    max_images: 5
    max_bytes_per_image: 1048576
```

These must be **exact Jira status names** (not category names like `In Progress` or `Done`). If multiple transitions reach the same target status, the tool returns a `transition_ambiguous` error — rename statuses or adjust the workflow to resolve it.

### Log Search

Configure a log root directory that the tools can browse and search.

```yaml
plugins:
  enabled:
    - log_search

log_search:
  log_base_dir: /absolute/path/to/logs
```

- `list_log_files` lists one level of files and directories under the log root or a relative path.
- `search_log` searches a single file selected from `list_log_files`.
- `log_base_dir` should point to the top-level directory that contains your service, date, or instance log folders.

### Other `config.yaml` settings

```yaml
logging:
  dir: logs
  level: info   # debug | info | warning | error
```

- `logging.dir` is optional and defaults to `logs`.
- Relative paths are resolved from the process working directory, so `logs` means `./logs` wherever you start the server. Absolute paths are allowed.
- `logging.level` is optional and must be one of `debug`, `info`, `warning`, or `error`.

## Adding a New Tool

1. Implement `register_<name>_tools(mcp: FastMCP, settings: Settings)` under `src/work_mcp/tools/`.
2. Keep simple plugins in a single module such as `src/work_mcp/tools/<name>.py`.
3. When a plugin grows into multiple focused files, group it as a package such as `src/work_mcp/tools/<name>/`.
4. Add an entry to `PLUGIN_REGISTRY` in `src/work_mcp/tools/__init__.py`.
5. Add the plugin name to `plugins.enabled` in `config.yaml`.

## Agent Setup

Point your MCP client or agent at the packaged entry point:

```json
{
  "mcpServers": {
    "work-mcp": {
      "command": "uv",
      "args": ["run", "work-mcp"],
      "cwd": "/absolute/path/to/work-mcp"
    }
  }
}
```

If your MCP client starts servers from the current repository root, `cwd` can usually be omitted.

This launches the server over `stdio`, which is the default MCP setup for local agents.

## Run

```bash
uv run work-mcp
```

This starts the server over `stdio`.

Run in HTTP mode:

```bash
make run
```

Override the bind address or port when needed:

```bash
make run HOST=0.0.0.0 PORT=9000
```

Or call the entry point directly:

```bash
uv run work-mcp --transport streamable-http --host 0.0.0.0 --port 8182
```

For an agent or MCP client that connects over HTTP, point it at the running server's `/mcp` endpoint, for example `http://127.0.0.1:8182/mcp`.

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
  

uv run python scripts/preview_tool.py call db_list_databases \
  --args '{}'


uv run python scripts/preview_tool.py call jira_get_attachment_image \
  --args '{"issue_key":"PAKISTAN-174","attachment_id":"24132"}'
```

Run smoke tests:

```bash
uv run pytest
```

Inspect one Jira issue's current status and available workflow transitions:

```bash
uv run python scripts/inspect_jira_issue_workflow.py IOS-123
```

This single command prints:

- all visible Jira `statusCategory` values
- all visible Jira `status` values
- the issue's current status
- every transition currently available for that issue
