# Database Tool Module Design

Provides four read-only database tools for local agents that need to inspect live
server data during debugging. The first implementation targets SQL Server. The
module boundary should allow future engines, but the initial design optimizes for
correctness and safety over premature abstraction.

## Safety Boundary

These tools do not and cannot guarantee read-only behavior by SQL parsing alone.
The hard safety boundary is the database account

- The configured database user must be restricted to read-only access.
- Tool-layer SQL validation is best-effort defense in depth.
- If database permissions allow writes, this module must be treated as unsafe.

Do not describe the tool layer as a guarantee against state changes.

## Module Structure

```text
src/work_mcp/tools/database/
├── __init__.py
├── register.py # MCP tool registration only
├── service.py # argument validation, error mapping, response shaping
├── base.py # abstract client contract
├── factory.py # select concrete client from config
├── sqlserver.py # SQL Server implementation
├── security.py # best-effort read-only validation
└── strings.py # tool names, descriptions, reusable hints
```

## Layer Responsibilities

```text
register.py thin MCP wrappers and parameter annotations
    │
service.py validate input, call client/security, map failures
    │
security.py best-effort validation for single-statement SELECT queries
    │
base.py engine-neutral client interface
    ▲
factory.py choose concrete client
    │
sqlserver.py SQL Server implementation
```

`register.py` should stay minimal, matching the existing plugin pattern in this
repository. Database-specific query shaping belongs in the concrete client, not in
the registration layer.

## Configuration

All connection fields are sensitive and must be loaded from `.env` / environment only.
Do not load them from `config.yaml`.

### New `.env` variables

```text
DB_TYPE=sqlserver
DB_HOST=
DB_USER=
DB_PASSWORD=
DB_NAME=
DB_PORT=1433
DB_DRIVER=ODBC Driver 18 for SQL Server
DB_TRUST_SERVER_CERTIFICATE=false
DB_CONNECT_TIMEOUT_SECONDS=5
```

`DB_NAME` is the default database for connection bootstrap. Individual tools may still
target another database when supported by the engine.

- `DB_TYPE` supports `sqlserver` and `mysql`.
- `DB_PORT` defaults to `1433` for `sqlserver` and `3306` for `mysql`.
- `DB_DRIVER` is required for `sqlserver` and ignored for `mysql`.

### New dataclass in `config.py`

```python
@dataclass(frozen=True)
class DatabaseSettings:
    db_type: str
    host: str
    port: int
    user: str
    password: str
    default_database: str
    driver: str
    trust_server_certificate: bool
    connect_timeout_seconds: int
```

Add it to `Settings` as `database: DatabaseSettings | None`.

### Validation Rules

When `"database"` is in `enabled_plugins`

- `DB_TYPE` must be present and supported.
- `DB_HOST`, `DB_USER`, `DB_PASSWORD`, and `DB_NAME` must be non-empty.
- `DB_DRIVER` must be non-empty for `sqlserver`.
- `DB_PORT` and `DB_CONNECT_TIMEOUT_SECONDS` must be positive integers.

`KNOWN_PLUGINS` gains `"database"`.

## Tool Output Contract

Follow [docs/tool-design.md](/Users/david/codes/mcp/work-mcp/docs/tool-design.md).

- Invalid input or missing resources return recoverable failures.
- Known connection / authentication / driver failures return non-recoverable failures
  with `error_type`, `message`, and `hint`.
- Unexpected defects should raise and propagate.

## Security Model

`security.py` performs best-effort validation for `execute_query`

1. Parse the submitted SQL with `sqlparse`.
2. Reject multiple statements.
3. Reject non-`SELECT` statements.
4. Reject obvious write-like constructs such as `SELECT ... INTO`.

This validation is not the primary security boundary. The configured database account
must still be read-only.

## Factory

```python
SUPPORTED_DB_TYPES = frozenset({"sqlserver", "mysql"})

def get_db_client(config: DatabaseSettings) -> AbstractDatabaseClient:
    if config.db_type == "sqlserver":
        return SqlServerClient(config)
    if config.db_type == "mysql":
        return MySqlClient(config)
    raise ValueError(f"Unsupported db_type: {config.db_type!r}")
```

## Abstract Interface

```python
class AbstractDatabaseClient(ABC):
    @abstractmethod
    def list_databases(self) -> list[str]: ...

    @abstractmethod
    def list_tables(self, database: str) -> list[str]: ...

    @abstractmethod
    def get_table_schema(self, database: str, table: str) -> list[dict[str, object]]: ...

    @abstractmethod
    def execute_query(self, database: str, sql: str, limit: int) -> dict[str, object]: ...
```

`execute_query()` should enforce row limits inside the concrete client. Do not rewrite
SQL in `register.py`.

## Tools

### `db_list_databases`

Returns

```json
{
  "success": true, 
  "databases": ["app_db", "reporting_db"]
}
```

Failures

- `internal_error`: known connection, authentication, driver, or upstream DB failure.

### `db_list_tables`

Returns

```json
{
  "success": true, 
  "database": "app_db", 
  "tables": ["orders", "users"]
}
```

Failures

- `invalid_argument`: empty `database`
- `database_not_found`: database does not exist or is not accessible
- `internal_error`: connection / driver / auth failure

### `db_get_table_schema`

Returns

```json
{
  "success": true, 
  "database": "app_db", 
  "table": "orders", 
  "columns": [
    {"column": "id", "type": "int", "nullable": false, "primary_key": true}
  ]
}
```

Failures

- `invalid_argument`: empty `database` or `table`
- `database_not_found`
- `table_not_found`
- `internal_error`

### `db_execute_query`

Returns

```json
{
  "success": true, 
  "database": "app_db", 
  "columns": ["id", "status"], 
  "rows": [[1, "pending"]], 
  "row_count": 1, 
  "truncated": false
}
```

Rules

- Only a single `SELECT` statement is accepted.
- `limit` defaults to 5 and must be between 1 and 50.
- Row limiting is enforced by the concrete client.

Failures

- `invalid_argument`: empty `database` or `sql`, or invalid `limit`
- `readonly_violation`: rejected by best-effort SQL validation
- `database_not_found`
- `query_error`: known SQL error the caller can fix by adjusting the query
- `internal_error`: connection / auth / driver / upstream DB failure

## Dependencies

- `pyodbc`: SQL Server ODBC adapter
- `sqlparse`: SQL parsing for best-effort validation

`pyodbc` requires a SQL Server ODBC driver installed on the host OS. Document that in
`.env.example`.
