from __future__ import annotations

from ...config import DB_TYPE_MYSQL, DB_TYPE_SQLSERVER
from ...hints import (
    STOP_AND_NOTIFY_USER_INSTRUCTION,
    STOP_NOTIFY_AND_ASK_USER_HOW_TO_PROCEED_INSTRUCTION,
)

TOOL_DB_LIST_DATABASES = "db_list_databases"
TOOL_DB_LIST_TABLES = "db_list_tables"
TOOL_DB_GET_TABLE_SCHEMA = "db_get_table_schema"
TOOL_DB_EXECUTE_QUERY = "db_execute_query"

QUERY_MAX_LIMIT = 10

DB_LIST_DATABASES_DESCRIPTION = f"""\
List all available databases.

Use this when the user reports a data issue — such as a missing record, unexpected
behavior, or data mismatch — and you need to query the database to investigate.
If you already know the target database name, skip this and call {TOOL_DB_LIST_TABLES}
or {TOOL_DB_EXECUTE_QUERY} directly.
"""

DB_LIST_TABLES_DESCRIPTION = f"""\
List tables in a specific database.

Use this when you know the database name but are unsure which table holds the relevant
data. You can also use it before running a query to confirm a table exists.
"""

DB_GET_TABLE_SCHEMA_DESCRIPTION = f"""\
Return the column definitions for a database table.

Use this when you are unsure of the exact column names or data types before writing a
query. Confirms available columns, data types, nullability, and primary-key fields.
"""

def database_engine_label(db_type: str) -> str:
    if db_type == DB_TYPE_MYSQL:
        return "MySQL"
    if db_type == DB_TYPE_SQLSERVER:
        return "SQL Server"
    return "the configured database"


def _database_syntax_label(db_type: str) -> str:
    if db_type == DB_TYPE_MYSQL:
        return "MySQL-compatible"
    if db_type == DB_TYPE_SQLSERVER:
        return "SQL Server-compatible"
    return "database-compatible"


def db_execute_query_description(db_type: str) -> str:
    engine_label = database_engine_label(db_type)
    syntax_label = _database_syntax_label(db_type)
    return f"""\
Execute a read-only SELECT query against a {engine_label} database and return structured rows.

Use this to inspect live data. If you are unsure of the column names or data types,
call {TOOL_DB_GET_TABLE_SCHEMA} first. If you already know the schema, call this directly.

Write targeted queries: filter with WHERE clauses and cap the row count using
{syntax_label} limiting syntax — returning unnecessary rows pollutes your context
and wastes tokens. Do not use this tool for bulk data retrieval.
"""


def query_truncated_hint(db_type: str) -> str:
    engine_label = database_engine_label(db_type)
    syntax_label = _database_syntax_label(db_type)
    return (
        f"The result was truncated to keep a single response to at most {QUERY_MAX_LIMIT} rows and "
        "protect agent context. If you need a smaller or more specific result, refine the SQL with "
        f"WHERE clauses and a stable ORDER BY clause. The current database engine is {engine_label}; "
        f"use {syntax_label} limiting or pagination syntax if needed."
    )


def query_complete_hint() -> str:
    return "All rows were returned. Proceed with the data."


def query_error_hint(db_type: str) -> str:
    engine_label = database_engine_label(db_type)
    return (
        "The query failed. Verify table and column names, then check whether the SQL matches "
        f"{engine_label} syntax and retry once. If the query still fails after one correction, "
        "stop and tell the user the error message above."
    )

HINT_DATABASE_NOT_FOUND = (
    "The database was not found or is not accessible. Before retrying: "
    "(1) check the source code or ORM models to confirm the actual database name used at runtime — "
    "it may differ from the logical or environment name; "
    f"(2) call {TOOL_DB_LIST_DATABASES} to see what databases are visible to the configured account. "
    "If the database still cannot be found after retrying with a confirmed name, "
    f"{STOP_NOTIFY_AND_ASK_USER_HOW_TO_PROCEED_INSTRUCTION}"
)

HINT_TABLE_NOT_FOUND = (
    "The table '{{table}}' was not found in database '{{database}}'. Before retrying: "
    "(1) check the source code or ORM models to confirm the actual table name used at runtime — "
    "the ORM model class name often differs from the underlying SQL table name; "
    "(2) verify you are querying the correct database for this data; "
    f"(3) call {TOOL_DB_LIST_TABLES} to see the tables that actually exist. "
    "If the table still cannot be found after retrying with a confirmed name, "
    f"{STOP_NOTIFY_AND_ASK_USER_HOW_TO_PROCEED_INSTRUCTION}"
)

HINT_DATABASES_FOUND = (
    f"You now know which databases are available. Proceed with {TOOL_DB_LIST_TABLES} "
    f"or {TOOL_DB_EXECUTE_QUERY} directly — do not call {TOOL_DB_LIST_DATABASES} again."
)

HINT_NO_DATABASES = (
    "No databases were returned. The configured user account may lack visibility permissions. "
    f"{STOP_AND_NOTIFY_USER_INSTRUCTION}"
)
