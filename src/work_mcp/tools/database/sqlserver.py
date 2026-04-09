from __future__ import annotations

from contextlib import closing
from typing import Any, NoReturn

import pyodbc

from ...config import DatabaseSettings
from .base import (
    AbstractDatabaseClient,
    DatabaseConnectionError,
    DatabaseNotFoundError,
    QueryExecutionError,
    QueryResult,
    TableNotFoundError,
)

LIST_DATABASES_SQL = """
SELECT name
FROM sys.databases
WHERE state_desc = 'ONLINE'
ORDER BY name
"""

LIST_TABLES_SQL = """
SELECT TABLE_NAME
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_TYPE = 'BASE TABLE'
ORDER BY TABLE_NAME
"""

TABLE_SCHEMA_SQL = """
SELECT
    c.COLUMN_NAME,
    c.DATA_TYPE,
    c.CHARACTER_MAXIMUM_LENGTH,
    CASE WHEN c.IS_NULLABLE = 'YES' THEN 1 ELSE 0 END AS is_nullable,
    CASE WHEN pk.COLUMN_NAME IS NULL THEN 0 ELSE 1 END AS is_primary_key
FROM INFORMATION_SCHEMA.COLUMNS AS c
LEFT JOIN (
    SELECT ku.TABLE_NAME, ku.COLUMN_NAME
    FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS AS tc
    INNER JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE AS ku
        ON tc.CONSTRAINT_NAME = ku.CONSTRAINT_NAME
    WHERE tc.CONSTRAINT_TYPE = 'PRIMARY KEY'
) AS pk
    ON pk.TABLE_NAME = c.TABLE_NAME
    AND pk.COLUMN_NAME = c.COLUMN_NAME
WHERE c.TABLE_NAME = ?
ORDER BY c.ORDINAL_POSITION
"""


class SqlServerClient(AbstractDatabaseClient):
    def __init__(self, settings: DatabaseSettings) -> None:
        self._settings = settings

    def list_databases(self) -> list[str]:
        with closing(self._connect()) as connection, closing(connection.cursor()) as cursor:
            cursor.execute(LIST_DATABASES_SQL)
            return [str(row[0]) for row in cursor.fetchall()]

    def list_tables(self, database: str) -> list[str]:
        with closing(self._connect(database)) as connection, closing(connection.cursor()) as cursor:
            cursor.execute(LIST_TABLES_SQL)
            return [str(row[0]) for row in cursor.fetchall()]

    def get_table_schema(self, database: str, table: str) -> list[dict[str, Any]]:
        with closing(self._connect(database)) as connection, closing(connection.cursor()) as cursor:
            cursor.execute(TABLE_SCHEMA_SQL, table)
            rows = cursor.fetchall()
            if not rows:
                raise TableNotFoundError(
                    f"Table '{table}' was not found in database '{database}'."
                )
            return [self._serialize_schema_row(row) for row in rows]

    def execute_query(self, database: str, sql: str, limit: int) -> QueryResult:
        with closing(self._connect(database)) as connection, closing(connection.cursor()) as cursor:
            try:
                cursor.execute(sql)
            except pyodbc.Error as exc:
                self._raise_for_pyodbc_error(exc, database=database)

            description = cursor.description or []
            columns = [str(item[0]) for item in description]
            fetched_rows = cursor.fetchmany(limit + 1)
            truncated = len(fetched_rows) > limit
            materialized_rows = [
                [self._normalize_value(value) for value in row]
                for row in fetched_rows[:limit]
            ]
            return QueryResult(
                columns=columns,
                rows=materialized_rows,
                row_count=len(materialized_rows),
                truncated=truncated,
            )

    def _connect(self, database: str | None = None) -> pyodbc.Connection:
        try:
            connection = pyodbc.connect(
                self._connection_string(database or self._settings.default_database),
                timeout=self._settings.connect_timeout_seconds,
                autocommit=True,
            )
            if connection is None:
                db_fragment = f" for database '{database}'" if database else ""
                raise DatabaseConnectionError(
                    f"SQL Server connection failed{db_fragment}: pyodbc.connect() returned None."
                )
            return connection
        except pyodbc.Error as exc:
            self._raise_for_pyodbc_error(exc, database=database)

    def _connection_string(self, database: str) -> str:
        trust_cert = "yes" if self._settings.trust_server_certificate else "no"
        return (
            f"DRIVER={{{self._settings.driver}}};"
            f"SERVER={self._settings.host},{self._settings.port};"
            f"DATABASE={database};"
            f"UID={self._settings.user};"
            f"PWD={self._settings.password};"
            "Encrypt=yes;"
            f"TrustServerCertificate={trust_cert};"
        )

    def _raise_for_pyodbc_error(
        self,
        exc: pyodbc.Error,
        *,
        database: str | None = None,
    ) -> NoReturn:
        message = _format_pyodbc_error(exc)
        lowered = message.lower()
        if "cannot open database" in lowered or "unknown database" in lowered:
            raise DatabaseNotFoundError(message) from exc
        if "invalid object name" in lowered:
            raise TableNotFoundError(message) from exc
        if any(
            marker in lowered
            for marker in (
                "login failed",
                "access denied",
                "timeout expired",
                "data source name not found",
                "server does not exist",
                "network-related",
                "could not open a connection",
                "odbc driver",
                "client unable to establish connection",
                "connection is busy",
            )
        ):
            db_fragment = f" for database '{database}'" if database else ""
            raise DatabaseConnectionError(
                f"SQL Server connection failed{db_fragment}: {message}"
            ) from exc
        raise QueryExecutionError(message) from exc

    def _serialize_schema_row(self, row: Any) -> dict[str, Any]:
        data_type = str(row[1])
        length = row[2]
        if length and isinstance(length, int) and length > 0 and data_type in {
            "varchar",
            "nvarchar",
            "char",
            "nchar",
            "binary",
            "varbinary",
        }:
            data_type = f"{data_type}({length})"

        return {
            "column": str(row[0]),
            "type": data_type,
            "nullable": bool(row[3]),
            "primary_key": bool(row[4]),
        }

    def _normalize_value(self, value: Any) -> Any:
        if isinstance(value, bytes):
            return value.hex()
        return value


def _format_pyodbc_error(exc: pyodbc.Error) -> str:
    parts = [str(item).strip() for item in exc.args if str(item).strip()]
    if not parts:
        return str(exc)
    return " | ".join(parts)
