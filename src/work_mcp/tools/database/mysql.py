from __future__ import annotations

import atexit
from collections.abc import Sequence
from contextlib import closing
from threading import RLock
from typing import Any, Callable, NoReturn, Protocol, TypeVar, cast

from ...config import DatabaseSettings
from .base import (
    AbstractDatabaseClient,
    DatabaseConnectionError,
    DatabaseNotFoundError,
    QueryExecutionError,
    QueryResult,
    TableNotFoundError,
)
from .normalize import normalize_database_value
from .strings import QUERY_MAX_LIMIT

try:
    import pymysql
except ImportError:  # pragma: no cover - exercised via runtime error path
    pymysql = None

LIST_DATABASES_SQL = """
SELECT SCHEMA_NAME
FROM INFORMATION_SCHEMA.SCHEMATA
ORDER BY SCHEMA_NAME
"""

CONNECTIVITY_SQL = """
SELECT
    @@hostname AS server_name,
    DATABASE() AS database_name,
    CURRENT_USER() AS login_name
"""

LIST_TABLES_SQL = """
SELECT TABLE_NAME
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = %s
  AND TABLE_TYPE = 'BASE TABLE'
ORDER BY TABLE_NAME
"""

TABLE_SCHEMA_SQL = """
SELECT
    c.COLUMN_NAME,
    c.COLUMN_TYPE,
    CASE WHEN c.IS_NULLABLE = 'YES' THEN 1 ELSE 0 END AS is_nullable,
    CASE WHEN k.COLUMN_NAME IS NULL THEN 0 ELSE 1 END AS is_primary_key
FROM INFORMATION_SCHEMA.COLUMNS AS c
LEFT JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE AS k
    ON k.TABLE_SCHEMA = c.TABLE_SCHEMA
    AND k.TABLE_NAME = c.TABLE_NAME
    AND k.COLUMN_NAME = c.COLUMN_NAME
    AND k.CONSTRAINT_NAME = 'PRIMARY'
WHERE c.TABLE_SCHEMA = %s
  AND c.TABLE_NAME = %s
ORDER BY c.ORDINAL_POSITION
"""

DATABASE_NOT_FOUND_CODES = {
    1044,  # access denied to database
    1049,  # unknown database
}
TABLE_NOT_FOUND_CODES = {
    1146,  # table doesn't exist
}
QUERY_ERROR_CODES = {
    1054,  # unknown column
    1064,  # SQL syntax error
    1149,  # syntax error in old SQL mode
    1222,  # incorrect number of rows in subquery
    1241,  # operand should contain one column
}
CONNECTION_ERROR_CODES = {
    0,     # unknown / generic connection failure
    1040,  # too many connections
    1042,  # unable to get host address
    1043,  # bad handshake
    1045,  # access denied (wrong credentials)
    2002,  # can't connect via socket
    2003,  # can't connect to host
    2005,  # unknown host
    2013,  # lost connection during query
    2055,  # lost connection (network write failure)
}

T = TypeVar("T")
_MySqlRow = Sequence[object]
_MySqlDescription = Sequence[Sequence[object]]


def _ensure_pymysql_available() -> None:
    if pymysql is None:
        raise DatabaseConnectionError(
            "MySQL driver is not installed. Add the 'pymysql' package to the environment."
        )


def _mysql_error_type() -> type[Exception]:
    if pymysql is None:
        return Exception
    return cast(type[Exception], pymysql.MySQLError)


def _coerce_mysql_connection(raw_connection: object) -> _MySqlConnection:
    return cast(_MySqlConnection, raw_connection)


class _MySqlCursor(Protocol):
    description: _MySqlDescription | None

    def execute(self, sql: str, params: object = None) -> object: ...

    def fetchall(self) -> list[_MySqlRow]: ...

    def fetchone(self) -> _MySqlRow | None: ...

    def fetchmany(self, size: int) -> list[_MySqlRow]: ...

    def close(self) -> None: ...


class _MySqlConnection(Protocol):
    def cursor(self) -> _MySqlCursor: ...

    def close(self) -> None: ...


def _raise_for_mysql_error(
        exc: Exception,
    *,
    database: str | None = None,
) -> NoReturn:
    code, message = _format_mysql_error(exc)
    lowered = message.lower()
    if code in DATABASE_NOT_FOUND_CODES:
        raise DatabaseNotFoundError(message) from exc
    if code in TABLE_NOT_FOUND_CODES or "doesn't exist" in lowered:
        raise TableNotFoundError(message) from exc
    if code in CONNECTION_ERROR_CODES:
        db_fragment = f" for database '{database}'" if database else ""
        raise DatabaseConnectionError(
            f"MySQL connection failed{db_fragment}: {message}"
        ) from exc
    if code in QUERY_ERROR_CODES:
        raise QueryExecutionError(message) from exc
    raise QueryExecutionError(message) from exc


def _is_connection_error(exc: Exception) -> bool:
    code, _ = _format_mysql_error(exc)
    return code in CONNECTION_ERROR_CODES


def _serialize_schema_row(row: _MySqlRow) -> dict[str, Any]:
    return {
        "column": str(row[0]),
        "type": str(row[1]),
        "nullable": bool(row[2]),
        "primary_key": bool(row[3]),
    }


def _normalize_value(value: Any) -> Any:
    return normalize_database_value(value)


def _pool_key(database: str | None) -> str:
    return database or ""


class MySqlClient(AbstractDatabaseClient):
    def __init__(self, settings: DatabaseSettings) -> None:
        self._settings = settings
        self._connections: dict[str, _MySqlConnection] = {}
        self._connections_lock = RLock()
        self._operation_locks: dict[str, RLock] = {}
        atexit.register(self.close)

    def list_databases(self) -> list[str]:
        def operation(cursor: _MySqlCursor) -> list[str]:
            cursor.execute(LIST_DATABASES_SQL)
            return [str(row[0]) for row in cursor.fetchall()]

        return self._run_with_cursor(None, operation)

    def list_tables(self, database: str) -> list[str]:
        def operation(cursor: _MySqlCursor) -> list[str]:
            cursor.execute(LIST_TABLES_SQL, (database,))
            return [str(row[0]) for row in cursor.fetchall()]

        return self._run_with_cursor(database, operation)

    def get_table_schema(self, database: str, table: str) -> list[dict[str, Any]]:
        def operation(cursor: _MySqlCursor) -> list[dict[str, Any]]:
            cursor.execute(TABLE_SCHEMA_SQL, (database, table))
            rows = cursor.fetchall()
            if not rows:
                raise TableNotFoundError(
                    f"Table '{table}' was not found in database '{database}'."
                )
            return [_serialize_schema_row(row) for row in rows]

        return self._run_with_cursor(database, operation)

    def execute_query(self, database: str, sql: str) -> QueryResult:
        def operation(cursor: _MySqlCursor) -> QueryResult:
            cursor.execute(sql)
            description = cursor.description or []
            columns = [str(item[0]) for item in description]
            fetched_rows = cursor.fetchmany(QUERY_MAX_LIMIT + 1)
            truncated = len(fetched_rows) > QUERY_MAX_LIMIT
            materialized_rows = [
                [_normalize_value(value) for value in row]
                for row in fetched_rows[:QUERY_MAX_LIMIT]
            ]
            return QueryResult(
                columns=columns,
                rows=materialized_rows,
                row_count=len(materialized_rows),
                truncated=truncated,
            )

        return self._run_with_cursor(database, operation)

    def close(self) -> None:
        with self._connections_lock:
            connections = list(self._connections.values())
            self._connections.clear()
        for connection in connections:
            with closing(connection):
                pass

    def _run_with_cursor(
        self,
        database_name: str | None,
        operation: Callable[[_MySqlCursor], T],
    ) -> T:
        operation_lock = self._get_operation_lock(database_name)
        with operation_lock:
            try:
                with closing(self._get_connection(database_name).cursor()) as cursor:
                    return operation(cursor)
            except _mysql_error_type() as exc:
                if _is_connection_error(exc):
                    self._discard_connection(database_name)
                    try:
                        with closing(
                            self._get_connection(database_name, force_new=True).cursor()
                        ) as cursor:
                            return operation(cursor)
                    except _mysql_error_type() as retry_exc:
                        _raise_for_mysql_error(retry_exc, database=database_name)
                _raise_for_mysql_error(exc, database=database_name)

    def _get_connection(
        self,
        database: str | None,
        *,
        force_new: bool = False,
    ) -> _MySqlConnection:
        pool_key = _pool_key(database)
        with self._connections_lock:
            if force_new:
                self._discard_connection(database)
            connection = self._connections.get(pool_key)
            if connection is not None:
                return connection
            connection = self._connect(database)
            self._connections[pool_key] = connection
            return connection

    def _discard_connection(self, database: str | None) -> None:
        pool_key = _pool_key(database)
        with self._connections_lock:
            connection = self._connections.pop(pool_key, None)
        if connection is None:
            return
        with closing(connection):
            pass

    def _get_operation_lock(self, database: str | None) -> RLock:
        pool_key = _pool_key(database)
        with self._connections_lock:
            lock = self._operation_locks.get(pool_key)
            if lock is None:
                lock = RLock()
                self._operation_locks[pool_key] = lock
            return lock

    def _connect(self, database: str | None) -> _MySqlConnection:
        _ensure_pymysql_available()
        try:
            raw_connection = cast(
                object,
                pymysql.connect(
                    host=self._settings.host,
                    port=self._settings.port,
                    user=self._settings.user,
                    password=self._settings.password,
                    database=database or None,
                    connect_timeout=self._settings.connect_timeout_seconds,
                    autocommit=True,
                    charset="utf8mb4",
                ),
            )
            if raw_connection is None:
                db_fragment = f" for database '{database}'" if database else ""
                raise DatabaseConnectionError(
                    f"MySQL connection failed{db_fragment}: pymysql.connect() returned None."
                )
            return _coerce_mysql_connection(raw_connection)
        except _mysql_error_type() as exc:
            _raise_for_mysql_error(exc, database=database)


def _format_mysql_error(exc: Exception) -> tuple[int, str]:
    code = 0
    if getattr(exc, "args", ()):
        first_arg = exc.args[0]
        if isinstance(first_arg, int):
            code = first_arg
    parts = [str(item).strip() for item in getattr(exc, "args", ()) if str(item).strip()]
    if not parts:
        return code, str(exc)
    return code, " | ".join(parts)


def probe_mysql_connectivity(
    settings: DatabaseSettings,
    *,
    timeout_seconds: int,
) -> dict[str, str]:
    _ensure_pymysql_available()
    try:
        raw_connection = cast(
            object,
            pymysql.connect(
                host=settings.host,
                port=settings.port,
                user=settings.user,
                password=settings.password,
                database=None,
                connect_timeout=timeout_seconds,
                autocommit=True,
                charset="utf8mb4",
            ),
        )
        with closing(_coerce_mysql_connection(raw_connection)) as connection:
            with closing(connection.cursor()) as cursor:
                cursor.execute(CONNECTIVITY_SQL)
                row = cursor.fetchone()
    except _mysql_error_type() as exc:
        _, message = _format_mysql_error(exc)
        raise RuntimeError(f"connectivity check failed: {message}") from exc

    if row is None:
        raise RuntimeError("connectivity check failed: MySQL returned no rows.")

    return {
        "server_name": str(row[0] or ""),
        "database_name": str(row[1] or ""),
        "login_name": str(row[2] or ""),
    }
