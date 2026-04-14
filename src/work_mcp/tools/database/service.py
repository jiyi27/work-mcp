from __future__ import annotations

from typing import Any

from ...config import Settings
from ...hints import INTERNAL_ERROR_RETRY_HINT, required_param_hint
from .base import (
    AbstractDatabaseClient,
    DatabaseConnectionError,
    DatabaseNotFoundError,
    QueryExecutionError,
    TableNotFoundError,
)
from .factory import get_db_client
from .security import ReadOnlyViolation, validate_read_only_query
from .strings import (
    HINT_DATABASE_NOT_FOUND,
    HINT_DATABASES_FOUND,
    HINT_NO_DATABASES,
    HINT_TABLE_NOT_FOUND,
    query_complete_hint,
    query_error_hint,
    query_truncated_hint,
)


def _invalid_argument(param_name: str) -> dict[str, Any]:
    return {
        "success": False,
        "error_type": "invalid_argument",
        "hint": required_param_hint(param_name),
    }


def _internal_error(message: str) -> dict[str, Any]:
    return {
        "success": False,
        "error_type": "internal_error",
        "message": message,
        "hint": INTERNAL_ERROR_RETRY_HINT,
    }


class DatabaseService:
    def __init__(
        self,
        settings: Settings,
        client: AbstractDatabaseClient | None = None,
    ) -> None:
        if settings.database is None:
            raise RuntimeError("Database plugin enabled without database settings.")
        self._settings = settings
        self._client = client or get_db_client(settings.database)

    def list_databases(self) -> dict[str, Any]:
        try:
            databases = self._client.list_databases()
        except DatabaseConnectionError as exc:
            return _internal_error(str(exc))
        response: dict[str, Any] = {"success": True, "databases": databases}
        if not databases:
            response["hint"] = HINT_NO_DATABASES
        else:
            response["hint"] = HINT_DATABASES_FOUND
        return response

    def list_tables(self, database: str) -> dict[str, Any]:
        database_name = database.strip()
        if not database_name:
            return _invalid_argument("database")

        try:
            tables = self._client.list_tables(database_name)
        except DatabaseNotFoundError:
            return {
                "success": False,
                "error_type": "database_not_found",
                "hint": HINT_DATABASE_NOT_FOUND,
            }
        except DatabaseConnectionError as exc:
            return _internal_error(str(exc))

        return {"success": True, "database": database_name, "tables": tables}

    def get_table_schema(self, database: str, table: str) -> dict[str, Any]:
        database_name = database.strip()
        table_name = table.strip()
        if not database_name:
            return _invalid_argument("database")
        if not table_name:
            return _invalid_argument("table")

        try:
            columns = self._client.get_table_schema(database_name, table_name)
        except DatabaseNotFoundError:
            return {
                "success": False,
                "error_type": "database_not_found",
                "hint": HINT_DATABASE_NOT_FOUND,
            }
        except TableNotFoundError:
            return {
                "success": False,
                "error_type": "table_not_found",
                "hint": HINT_TABLE_NOT_FOUND.format(
                    database=database_name,
                    table=table_name,
                ),
            }
        except DatabaseConnectionError as exc:
            return _internal_error(str(exc))

        return {
            "success": True,
            "database": database_name,
            "table": table_name,
            "columns": columns,
        }

    def execute_query(self, database: str, sql: str) -> dict[str, Any]:
        database_name = database.strip()
        sql_text = sql.strip()

        if not database_name:
            return _invalid_argument("database")
        if not sql_text:
            return _invalid_argument("sql")

        try:
            validate_read_only_query(sql_text)
        except ReadOnlyViolation as exc:
            return {
                "success": False,
                "error_type": "readonly_violation",
                "hint": str(exc),
            }

        try:
            result = self._client.execute_query(database_name, sql_text)
        except DatabaseNotFoundError:
            return {
                "success": False,
                "error_type": "database_not_found",
                "hint": HINT_DATABASE_NOT_FOUND,
            }
        except QueryExecutionError as exc:
            return {
                "success": False,
                "error_type": "query_error",
                "message": str(exc),
                "hint": query_error_hint(self._settings.database.db_type),
            }
        except DatabaseConnectionError as exc:
            return _internal_error(str(exc))

        return {
            "success": True,
            "database": database_name,
            "columns": result.columns,
            "rows": result.rows,
            "row_count": result.row_count,
            "truncated": result.truncated,
            "hint": (
                query_truncated_hint(self._settings.database.db_type)
                if result.truncated
                else query_complete_hint()
            ),
        }
