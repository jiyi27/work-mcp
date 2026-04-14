from __future__ import annotations

import asyncio
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

from work_mcp.config import (
    DatabaseSettings,
    ServerSettings,
    Settings,
    default_startup_settings,
)
from work_mcp.server import create_mcp
from work_mcp.tools.database.base import (
    AbstractDatabaseClient,
    DatabaseConnectionError,
    DatabaseNotFoundError,
    QueryExecutionError,
    QueryResult,
    TableNotFoundError,
)
from work_mcp.tools.database.factory import check_database_connectivity, get_db_client
from work_mcp.tools.database.mysql import MySqlClient
from work_mcp.tools.database.normalize import normalize_database_value
from work_mcp.tools.database.sqlserver import SqlServerClient
from work_mcp.tools.database.security import ReadOnlyViolation, validate_read_only_query
from work_mcp.tools.database.service import DatabaseService
from work_mcp.tools.database.strings import QUERY_MAX_LIMIT

_DEFAULT_SERVER = ServerSettings(transport="stdio", host=None, port=None)
_DEFAULT_DATABASE = DatabaseSettings(
    db_type="sqlserver",
    host="db.example.internal",
    port=1433,
    user="readonly_user",
    password="secret",
    driver="ODBC Driver 18 for SQL Server",
    trust_server_certificate=False,
    connect_timeout_seconds=5,
)
_DEFAULT_MYSQL_DATABASE = DatabaseSettings(
    db_type="mysql",
    host="mysql.example.internal",
    port=3306,
    user="readonly_user",
    password="secret",
    driver="",
    trust_server_certificate=False,
    connect_timeout_seconds=5,
)


def _make_settings(**overrides: object) -> Settings:
    defaults = dict(
        server=_DEFAULT_SERVER,
        startup=default_startup_settings(),
        dingtalk_webhook_url="https://example.invalid/webhook",
        dingtalk_secret=None,
        jira_base_url="https://jira.example.invalid",
        jira_api_token="jira-token",
        jira_project_key="IOS",
        log_dir=Path("logs"),
        log_level="info",
        enabled_plugins=("database",),
        jira_latest_assigned_statuses=("待处理", "已接收", "处理中"),
        jira_start_target_status="已接收",
        jira_resolve_target_status="已解决",
        jira_attachment_max_images=5,
        jira_attachment_max_bytes=1_048_576,
        log_search=None,
        database=_DEFAULT_DATABASE,
    )
    defaults.update(overrides)
    return Settings(**defaults)  # type: ignore[arg-type]


class FakeDatabaseClient(AbstractDatabaseClient):
    def __init__(self) -> None:
        self.listed_databases = ["app_db", "reporting_db"]

    def list_databases(self) -> list[str]:
        return self.listed_databases

    def list_tables(self, database: str) -> list[str]:
        if database == "missing_db":
            raise DatabaseNotFoundError("missing")
        return ["orders", "users"]

    def get_table_schema(self, database: str, table: str) -> list[dict[str, object]]:
        if database == "missing_db":
            raise DatabaseNotFoundError("missing")
        if table == "missing_table":
            raise TableNotFoundError("missing")
        return [
            {
                "column": "id",
                "type": "int",
                "nullable": False,
                "primary_key": True,
            }
        ]

    def execute_query(self, database: str, sql: str) -> QueryResult:
        if database == "missing_db":
            raise DatabaseNotFoundError("missing")
        if "bad_column" in sql:
            raise QueryExecutionError("Invalid column name 'bad_column'.")
        if "boom" in sql:
            raise DatabaseConnectionError("connection lost")
        rows = [[1, "pending"], [2, "done"], [3, "failed"]]
        return QueryResult(
            columns=["id", "status"],
            rows=rows[:QUERY_MAX_LIMIT],
            row_count=len(rows[:QUERY_MAX_LIMIT]),
            truncated=len(rows) > QUERY_MAX_LIMIT,
        )


class FakeDatabaseClientWithLargeResult(AbstractDatabaseClient):
    def list_databases(self) -> list[str]:
        return ["app_db"]

    def list_tables(self, database: str) -> list[str]:
        return ["orders"]

    def get_table_schema(self, database: str, table: str) -> list[dict[str, object]]:
        return []

    def execute_query(self, database: str, sql: str) -> QueryResult:
        rows = [[item, f"status-{item}"] for item in range(QUERY_MAX_LIMIT + 5)]
        return QueryResult(
            columns=["id", "status"],
            rows=rows[:QUERY_MAX_LIMIT],
            row_count=QUERY_MAX_LIMIT,
            truncated=True,
        )


def test_validate_read_only_query_rejects_multiple_statements() -> None:
    try:
        validate_read_only_query("SELECT 1; SELECT 2")
    except ReadOnlyViolation as exc:
        assert "single statement" in str(exc)
    else:
        raise AssertionError("expected ReadOnlyViolation")


def test_validate_read_only_query_rejects_non_select_statement() -> None:
    try:
        validate_read_only_query("UPDATE users SET active = 1")
    except ReadOnlyViolation as exc:
        assert "Only SELECT statements" in str(exc)
    else:
        raise AssertionError("expected ReadOnlyViolation")


def test_validate_read_only_query_rejects_select_into() -> None:
    try:
        validate_read_only_query("SELECT * INTO backup_users FROM users")
    except ReadOnlyViolation as exc:
        assert "SELECT INTO" in str(exc)
    else:
        raise AssertionError("expected ReadOnlyViolation")


def test_database_service_returns_empty_database_hint() -> None:
    client = FakeDatabaseClient()
    client.listed_databases = []
    service = DatabaseService(_make_settings(), client=client)

    structured = service.list_databases()

    assert structured["success"] is True
    assert structured["databases"] == []
    assert "hint" in structured


def test_database_service_returns_structured_query_error() -> None:
    service = DatabaseService(_make_settings(), client=FakeDatabaseClient())

    structured = service.execute_query("app_db", "SELECT bad_column FROM users")

    assert structured == {
        "success": False,
        "error_type": "query_error",
        "message": "Invalid column name 'bad_column'.",
        "hint": "The query failed. Verify table and column names, then check whether the SQL matches SQL Server syntax and retry once. If the query still fails after one correction, stop and tell the user the error message above.",
    }


def test_database_service_returns_internal_error_for_connection_failure() -> None:
    service = DatabaseService(_make_settings(), client=FakeDatabaseClient())

    structured = service.execute_query("app_db", "SELECT boom FROM users")

    assert structured == {
        "success": False,
        "error_type": "internal_error",
        "message": "connection lost",
        "hint": "An internal error occurred. Retry up to 2 times; if still failing, stop and notify the user with the message above.",
    }


def test_database_service_returns_successful_query_result() -> None:
    service = DatabaseService(_make_settings(), client=FakeDatabaseClient())

    structured = service.execute_query("app_db", "SELECT id, status FROM users")

    assert structured == {
        "success": True,
        "database": "app_db",
        "columns": ["id", "status"],
        "rows": [[1, "pending"], [2, "done"], [3, "failed"]],
        "row_count": 3,
        "truncated": False,
        "hint": "The query result fit within the tool's response limit. If you need a different slice of data, refine the SQL with WHERE clauses, a stable ORDER BY clause, or SQL Server-compatible limiting syntax for SQL Server.",
    }


def test_database_service_returns_truncated_query_hint() -> None:
    service = DatabaseService(_make_settings(), client=FakeDatabaseClient())
    service._client = FakeDatabaseClientWithLargeResult()

    structured = service.execute_query("app_db", "SELECT id, status FROM users")

    assert structured == {
        "success": True,
        "database": "app_db",
        "columns": ["id", "status"],
        "rows": [[item, f"status-{item}"] for item in range(QUERY_MAX_LIMIT)],
        "row_count": QUERY_MAX_LIMIT,
        "truncated": True,
        "hint": f"The result was truncated to keep a single response to at most {QUERY_MAX_LIMIT} rows and protect agent context. If you need a smaller or more specific result, refine the SQL with WHERE clauses and a stable ORDER BY clause. The current database engine is SQL Server; use SQL Server-compatible limiting or pagination syntax if needed.",
    }


def test_database_service_returns_mysql_specific_query_error_hint() -> None:
    service = DatabaseService(_make_settings(database=_DEFAULT_MYSQL_DATABASE), client=FakeDatabaseClient())

    structured = service.execute_query("app_db", "SELECT bad_column FROM users")

    assert structured == {
        "success": False,
        "error_type": "query_error",
        "message": "Invalid column name 'bad_column'.",
        "hint": "The query failed. Verify table and column names, then check whether the SQL matches MySQL syntax and retry once. If the query still fails after one correction, stop and tell the user the error message above.",
    }


def test_database_tools_are_registered_when_database_plugin_enabled() -> None:
    mcp = create_mcp(_make_settings())

    tools = asyncio.run(mcp.list_tools())

    assert [tool.name for tool in tools] == [
        "db_list_databases",
        "db_list_tables",
        "db_get_table_schema",
        "db_execute_query",
    ]


def test_db_execute_query_description_mentions_sqlserver_syntax() -> None:
    mcp = create_mcp(_make_settings())

    tools = asyncio.run(mcp.list_tools())
    execute_query_tool = next(tool for tool in tools if tool.name == "db_execute_query")

    assert "SQL Server database" in execute_query_tool.description
    assert "SQL Server-compatible limiting or pagination syntax" in execute_query_tool.description


def test_db_execute_query_description_mentions_mysql_syntax() -> None:
    mcp = create_mcp(_make_settings(database=_DEFAULT_MYSQL_DATABASE))

    tools = asyncio.run(mcp.list_tools())
    execute_query_tool = next(tool for tool in tools if tool.name == "db_execute_query")

    assert "MySQL database" in execute_query_tool.description
    assert "MySQL-compatible limiting or pagination syntax" in execute_query_tool.description


def test_normalize_database_value_returns_json_safe_values() -> None:
    assert normalize_database_value(bytes.fromhex("00ff")) == "00ff"
    assert normalize_database_value(bytearray(b"\x01\x02")) == "0102"
    assert normalize_database_value(memoryview(b"\x03\x04")) == "0304"
    assert normalize_database_value(datetime(2024, 1, 2, 3, 4, 5)) == "2024-01-02T03:04:05"
    assert normalize_database_value(date(2024, 1, 2)) == "2024-01-02"
    assert normalize_database_value(time(3, 4, 5)) == "03:04:05"
    assert normalize_database_value(timedelta(hours=2, minutes=3)) == "2:03:00"
    assert normalize_database_value(Decimal("99.90")) == "99.90"
    assert normalize_database_value(UUID("12345678-1234-5678-1234-567812345678")) == (
        "12345678-1234-5678-1234-567812345678"
    )
    assert normalize_database_value("plain-text") == "plain-text"


class _StubCursor:
    def __init__(self, connection: "_StubConnection") -> None:
        self._connection = connection
        self.description = [("name",)]
        self._rows: list[tuple[object, ...]] = []
        self._position = 0

    def execute(self, sql: str, *params: object) -> None:
        self._connection.execute_calls += 1
        self._connection.executed_sql.append((sql, params))
        if self._connection.fail_first_execute:
            self._connection.fail_first_execute = False
            raise self._connection.error_type("08S01", "Communication link failure")
        self._rows = self._connection.rows
        self._position = 0

    def fetchall(self) -> list[tuple[object, ...]]:
        return list(self._rows)

    def fetchone(self) -> tuple[object, ...] | None:
        if not self._rows:
            return None
        return self._rows[0]

    def fetchmany(self, size: int) -> list[tuple[object, ...]]:
        start = self._position
        end = start + size
        self._position = min(end, len(self._rows))
        return list(self._rows[start:end])

    def close(self) -> None:
        self._connection.closed_cursors += 1


class _StubConnection:
    def __init__(
        self,
        rows: list[tuple[object, ...]],
        *,
        fail_first_execute: bool = False,
        error_type: type[Exception] = RuntimeError,
    ) -> None:
        self.rows = rows
        self.fail_first_execute = fail_first_execute
        self.error_type = error_type
        self.execute_calls = 0
        self.executed_sql: list[tuple[str, tuple[object, ...]]] = []
        self.closed_cursors = 0
        self.close_calls = 0

    def cursor(self) -> _StubCursor:
        return _StubCursor(self)

    def close(self) -> None:
        self.close_calls += 1


def test_sqlserver_client_reuses_connection_per_database(monkeypatch) -> None:
    connect_calls: list[str] = []
    connection = _StubConnection(rows=[("app_db",)], error_type=Exception)

    def fake_connect(connection_string: str, **_: object) -> _StubConnection:
        connect_calls.append(connection_string)
        return connection

    monkeypatch.setattr("work_mcp.tools.database.sqlserver.pyodbc.connect", fake_connect)

    client = SqlServerClient(_DEFAULT_DATABASE)

    assert client.list_databases() == ["app_db"]
    assert client.list_databases() == ["app_db"]
    assert len(connect_calls) == 1
    assert "DATABASE=" not in connect_calls[0]


def test_check_database_connectivity_uses_db_type_factory(monkeypatch) -> None:
    connect_calls: list[str] = []
    connection = _StubConnection(
        rows=[("db-server-1", "master", "readonly_user")],
        error_type=Exception,
    )

    def fake_connect(connection_string: str, **_: object) -> _StubConnection:
        connect_calls.append(connection_string)
        return connection

    monkeypatch.setattr("work_mcp.tools.database.sqlserver.pyodbc.connect", fake_connect)

    payload = check_database_connectivity(
        _DEFAULT_DATABASE,
        timeout_seconds=3,
    )

    assert payload == {
        "server_name": "db-server-1",
        "database_name": "master",
        "login_name": "readonly_user",
    }
    assert len(connect_calls) == 1
    assert "DATABASE=" not in connect_calls[0]


def test_get_db_client_returns_mysql_client() -> None:
    client = get_db_client(_DEFAULT_MYSQL_DATABASE)

    assert isinstance(client, MySqlClient)


def test_sqlserver_client_reconnects_after_connection_error(monkeypatch) -> None:
    error_type = type("FakePyodbcError", (Exception,), {})
    first_connection = _StubConnection(
        rows=[("app_db",)],
        fail_first_execute=True,
        error_type=error_type,
    )
    second_connection = _StubConnection(rows=[("app_db",)], error_type=error_type)
    issued_connections = [first_connection, second_connection]
    connect_calls: list[str] = []

    def fake_connect(connection_string: str, **_: object) -> _StubConnection:
        connect_calls.append(connection_string)
        return issued_connections.pop(0)

    monkeypatch.setattr("work_mcp.tools.database.sqlserver.pyodbc.connect", fake_connect)
    monkeypatch.setattr("work_mcp.tools.database.sqlserver.pyodbc.Error", error_type)

    client = SqlServerClient(_DEFAULT_DATABASE)

    assert client.list_databases() == ["app_db"]
    assert len(connect_calls) == 2
    assert first_connection.close_calls == 1
    assert second_connection.execute_calls == 1


def test_sqlserver_client_normalizes_query_values(monkeypatch) -> None:
    connect_calls: list[str] = []
    connection = _StubConnection(
        rows=[
            (
                datetime(2024, 1, 2, 3, 4, 5),
                date(2024, 1, 2),
                time(3, 4, 5),
                Decimal("19.95"),
                b"\xaa\xbb",
            )
        ],
        error_type=Exception,
    )

    def fake_connect(connection_string: str, **_: object) -> _StubConnection:
        connect_calls.append(connection_string)
        return connection

    monkeypatch.setattr("work_mcp.tools.database.sqlserver.pyodbc.connect", fake_connect)

    client = SqlServerClient(_DEFAULT_DATABASE)

    result = client.execute_query("app_db", "SELECT * FROM orders")

    assert len(connect_calls) == 1
    assert result.rows == [[
        "2024-01-02T03:04:05",
        "2024-01-02",
        "03:04:05",
        "19.95",
        "aabb",
    ]]


def test_sqlserver_execute_query_reconnects_after_connection_error(monkeypatch) -> None:
    error_type = type("FakePyodbcError", (Exception,), {})
    first_connection = _StubConnection(
        rows=[("app_db",)],
        fail_first_execute=True,
        error_type=error_type,
    )
    second_connection = _StubConnection(rows=[("recovered",)], error_type=error_type)
    issued_connections = [first_connection, second_connection]
    connect_calls: list[str] = []

    def fake_connect(connection_string: str, **_: object) -> _StubConnection:
        connect_calls.append(connection_string)
        return issued_connections.pop(0)

    monkeypatch.setattr("work_mcp.tools.database.sqlserver.pyodbc.connect", fake_connect)
    monkeypatch.setattr("work_mcp.tools.database.sqlserver.pyodbc.Error", error_type)

    client = SqlServerClient(_DEFAULT_DATABASE)

    result = client.execute_query("app_db", "SELECT * FROM orders")

    assert result.rows == [["recovered"]]
    assert len(connect_calls) == 2
    assert first_connection.close_calls == 1
    assert second_connection.execute_calls == 1


def test_mysql_client_reuses_connection_per_database(monkeypatch) -> None:
    connect_calls: list[dict[str, object]] = []
    connection = _StubConnection(rows=[("app_db",)], error_type=Exception)

    def fake_connect(**kwargs: object) -> _StubConnection:
        connect_calls.append(kwargs)
        return connection

    monkeypatch.setattr(
        "work_mcp.tools.database.mysql.pymysql",
        SimpleNamespace(connect=fake_connect, MySQLError=Exception),
    )

    client = MySqlClient(_DEFAULT_MYSQL_DATABASE)

    assert client.list_databases() == ["app_db"]
    assert client.list_databases() == ["app_db"]
    assert len(connect_calls) == 1
    assert connect_calls[0]["database"] is None


def test_check_mysql_database_connectivity_uses_db_type_factory(monkeypatch) -> None:
    connect_calls: list[dict[str, object]] = []
    connection = _StubConnection(
        rows=[("mysql-server-1", "app_db", "readonly_user@%")],
        error_type=Exception,
    )

    def fake_connect(**kwargs: object) -> _StubConnection:
        connect_calls.append(kwargs)
        return connection

    monkeypatch.setattr(
        "work_mcp.tools.database.mysql.pymysql",
        SimpleNamespace(connect=fake_connect, MySQLError=Exception),
    )

    payload = check_database_connectivity(
        _DEFAULT_MYSQL_DATABASE,
        timeout_seconds=3,
    )

    assert payload == {
        "server_name": "mysql-server-1",
        "database_name": "app_db",
        "login_name": "readonly_user@%",
    }
    assert len(connect_calls) == 1
    assert connect_calls[0]["database"] is None


def test_mysql_client_reconnects_after_connection_error(monkeypatch) -> None:
    error_type = type("FakeMySQLError", (Exception,), {})
    first_connection = _StubConnection(
        rows=[("app_db",)],
        fail_first_execute=True,
        error_type=error_type,
    )
    second_connection = _StubConnection(rows=[("app_db",)], error_type=error_type)
    issued_connections = [first_connection, second_connection]
    connect_calls: list[dict[str, object]] = []

    def fake_connect(**kwargs: object) -> _StubConnection:
        connect_calls.append(kwargs)
        return issued_connections.pop(0)

    monkeypatch.setattr(
        "work_mcp.tools.database.mysql.pymysql",
        SimpleNamespace(connect=fake_connect, MySQLError=error_type),
    )

    client = MySqlClient(_DEFAULT_MYSQL_DATABASE)

    assert client.list_databases() == ["app_db"]
    assert len(connect_calls) == 2
    assert first_connection.close_calls == 1
    assert second_connection.execute_calls == 1


def test_mysql_execute_query_reconnects_after_connection_error(monkeypatch) -> None:
    error_type = type("FakeMySQLError", (Exception,), {})
    first_connection = _StubConnection(
        rows=[("app_db",)],
        fail_first_execute=True,
        error_type=error_type,
    )
    second_connection = _StubConnection(rows=[("recovered",)], error_type=error_type)
    issued_connections = [first_connection, second_connection]
    connect_calls: list[dict[str, object]] = []

    def fake_connect(**kwargs: object) -> _StubConnection:
        connect_calls.append(kwargs)
        return issued_connections.pop(0)

    monkeypatch.setattr(
        "work_mcp.tools.database.mysql.pymysql",
        SimpleNamespace(connect=fake_connect, MySQLError=error_type),
    )

    client = MySqlClient(_DEFAULT_MYSQL_DATABASE)

    result = client.execute_query("app_db", "SELECT * FROM products")

    assert result.rows == [["recovered"]]
    assert len(connect_calls) == 2
    assert first_connection.close_calls == 1
    assert second_connection.execute_calls == 1


def test_mysql_client_normalizes_query_values(monkeypatch) -> None:
    connect_calls: list[dict[str, object]] = []
    connection = _StubConnection(
        rows=[
            (
                datetime(2024, 1, 2, 3, 4, 5),
                date(2024, 1, 2),
                Decimal("99.90"),
                timedelta(minutes=90),
                bytearray(b"\x00\x10"),
            )
        ],
        error_type=Exception,
    )

    def fake_connect(**kwargs: object) -> _StubConnection:
        connect_calls.append(kwargs)
        return connection

    monkeypatch.setattr(
        "work_mcp.tools.database.mysql.pymysql",
        SimpleNamespace(connect=fake_connect, MySQLError=Exception),
    )

    client = MySqlClient(_DEFAULT_MYSQL_DATABASE)

    result = client.execute_query("app_db", "SELECT * FROM products")

    assert len(connect_calls) == 1
    assert result.rows == [[
        "2024-01-02T03:04:05",
        "2024-01-02",
        "99.90",
        "1:30:00",
        "0010",
    ]]


def test_sqlserver_client_caps_rows_at_query_max_limit(monkeypatch) -> None:
    connection = _StubConnection(
        rows=[(str(index),) for index in range(QUERY_MAX_LIMIT + 3)],
        error_type=Exception,
    )

    def fake_connect(connection_string: str, **_: object) -> _StubConnection:
        return connection

    monkeypatch.setattr("work_mcp.tools.database.sqlserver.pyodbc.connect", fake_connect)

    client = SqlServerClient(_DEFAULT_DATABASE)

    result = client.execute_query("app_db", "SELECT * FROM orders ORDER BY name")

    assert result.rows == [[str(index)] for index in range(QUERY_MAX_LIMIT)]
    assert result.row_count == QUERY_MAX_LIMIT
    assert result.truncated is True


def test_mysql_client_caps_rows_at_query_max_limit(monkeypatch) -> None:
    connection = _StubConnection(
        rows=[(str(index),) for index in range(QUERY_MAX_LIMIT + 3)],
        error_type=Exception,
    )

    def fake_connect(**_: object) -> _StubConnection:
        return connection

    monkeypatch.setattr(
        "work_mcp.tools.database.mysql.pymysql",
        SimpleNamespace(connect=fake_connect, MySQLError=Exception),
    )

    client = MySqlClient(_DEFAULT_MYSQL_DATABASE)

    result = client.execute_query("app_db", "SELECT * FROM orders ORDER BY name")

    assert result.rows == [[str(index)] for index in range(QUERY_MAX_LIMIT)]
    assert result.row_count == QUERY_MAX_LIMIT
    assert result.truncated is True
