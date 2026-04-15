## work-mcp

An MCP server for work-related tools used by local agents.

Tools are grouped by plugin. Each plugin is enabled or disabled as a unit in `config.yaml`.

| Plugin | Tools                                                                    |
| ----------- | ------------------------------------------------------------------- |
| `database`  | `db_list_databases`, `db_list_tables`, `db_get_table_schema`, `db_execute_query` |
| `dingtalk`  | `dingtalk_send_markdown`                                            |
| `jira`      | `jira_get_latest_assigned_issue`, `jira_start_issue`, `jira_resolve_issue` |
| `log_search` | `list_log_files`, `search_log` |
| `remote_fs` | `remote_get_allowed_roots`, `remote_list_tree`, `remote_search_files`, `remote_read_file`, `remote_search_file_reverse` |

## Configuration

All configuration lives in `config.yaml`. To disable a plugin and all its tools, comment out its name in `plugins.enabled`.

### Database

Configure a read-only database account for live debugging queries. Supports SQL Server and MySQL.

**Configure in `config.yaml`:**

SQL Server:

```yaml
plugins:
  enabled:
    - database

database:
  type: sqlserver
  host: your-sqlserver-host.example.com
  port: 1433
  user: readonly_user
  password: your_password_here
  driver: ODBC Driver 18 for SQL Server
  trust_server_certificate: true
  connect_timeout_seconds: 5
```

MySQL:

```yaml
plugins:
  enabled:
    - database

database:
  type: mysql
  host: your-mysql-host.example.com
  port: 3306
  user: readonly_user
  password: your_password_here
  connect_timeout_seconds: 5
```

- `user` must be a read-only database account. Tool-layer SQL validation is only defense in depth and is not the primary safety boundary.
- SQL Server requires the Microsoft ODBC Driver installed on the host. `driver` must match the installed driver name.
- `trust_server_certificate: true` is only appropriate for environments where you intentionally bypass certificate validation (SQL Server only).
- MySQL uses `pymysql` — no ODBC driver needed. `driver` and `trust_server_certificate` are ignored for MySQL.
- When `startup.healthcheck.enabled=true`, the database plugin performs a live connectivity probe on startup. Startup stops if the connection fails.

### DingTalk

**1. Create a robot** — open the group settings in DingTalk → Robot Management → add a custom webhook robot. Copy the webhook URL. If you enable additional secret which used to replace keyword, also copy the signing secret.

**2. Configure in `config.yaml`:**

```yaml
plugins:
  enabled:
    - dingtalk

dingtalk:
  webhook_url: https://oapi.dingtalk.com/robot/send?access_token=your_token_here
  secret: SECxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

`secret` is only required when the robot has additional secret enabled. If it is required but missing, sends will fail with a signature mismatch error.

### Jira

**1. Discover your workflow status names:**

```bash
uv run python scripts/inspect_jira_issue_workflow.py YOUR-123
```

This prints every status name and available transition for that issue. Use the output to fill in the next step.

**2. Configure in `config.yaml`:**

```yaml
plugins:
  enabled:
    - jira

jira:
  base_url: https://your-jira-instance.example.com
  api_token: your_jira_api_token_here
  project_key: PROJECT1
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

- `api_token` — create one at your Jira profile → Personal Access Tokens.
- `project_key` — the short key for the project this server is allowed to query and update (e.g. `IOS`, `PROJECT1`).
- When `startup.healthcheck.enabled=true`, the Jira plugin probes `GET /rest/api/2/serverInfo` and `GET /rest/api/2/myself` using the configured base URL and token. Startup stops if Jira is unreachable or authentication fails.

These must be **exact Jira status names** (not category names like `In Progress` or `Done`). If multiple transitions reach the same target status, the tool returns a `transition_ambiguous` error — rename statuses or adjust the workflow to resolve it.

> **Note**
> Jira image attachments are currently exposed as metadata only. Most MCP coding clients still operate as text-first chat workflows, and returning raw image bytes or base64 does not reliably trigger image understanding. In practice that mostly wastes context window, so this server surfaces attachment metadata and asks the agent to request a user summary when visual details may matter.

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

### Remote FS

Configure one or more read-only roots that the agent may inspect remotely.

```yaml
plugins:
  enabled:
    - remote_fs

remote_fs:
  roots:
    - name: app
      path: /srv/myapp
      kind: code
      description: Deployed application source

    - name: logs
      path: /var/log/myapp
      kind: logs
      description: Application log files

    - name: config
      path: /etc/myapp
      kind: config
      description: Production configuration
```

- `remote_get_allowed_roots` returns the configured roots and their metadata.
- `remote_list_tree` browses directories under an allowed root.
- `remote_search_files` locates files or matching lines across one or more roots.
- `remote_read_file` reads a bounded line range from a known text file, including tail reads.
- `remote_search_file_reverse` scans a known text file from the end and returns the newest matches first.
- Every configured `path` must already exist and must be a directory.
- Roots are read-only boundaries. Tools cannot access paths outside the configured roots.

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
