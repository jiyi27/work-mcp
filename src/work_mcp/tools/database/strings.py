from __future__ import annotations

from ...hints import (
    STOP_AND_NOTIFY_USER_INSTRUCTION,
    STOP_NOTIFY_AND_ASK_USER_HOW_TO_PROCEED_INSTRUCTION,
)

TOOL_DB_LIST_DATABASES = "db_list_databases"
TOOL_DB_LIST_TABLES = "db_list_tables"
TOOL_DB_GET_TABLE_SCHEMA = "db_get_table_schema"
TOOL_DB_EXECUTE_QUERY = "db_execute_query"

QUERY_DEFAULT_LIMIT = 5
QUERY_MAX_LIMIT = 50

DB_LIST_DATABASES_DESCRIPTION = f"""\
List databases visible to the configured SQL Server account.

Use this first when you need to inspect live database data but do not yet know which
database contains the relevant tables.
"""

DB_LIST_TABLES_DESCRIPTION = f"""\
List tables in a specific database.

Use this after {TOOL_DB_LIST_DATABASES} to identify candidate tables before requesting
schema details or running a query.
"""

DB_GET_TABLE_SCHEMA_DESCRIPTION = f"""\
Return the column definitions for a database table.

Use this before writing a query so you can confirm the available columns, data types,
nullability, and primary-key fields.
"""

DB_EXECUTE_QUERY_DESCRIPTION = f"""\
Execute a read-only SELECT query against a database and return structured rows.

Use this to inspect live data during debugging after confirming the table schema with
{TOOL_DB_GET_TABLE_SCHEMA}. Only a single SELECT statement is accepted.
"""

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

HINT_QUERY_ERROR = (
    f"The query failed. Call {TOOL_DB_GET_TABLE_SCHEMA} to verify table and column names, "
    "then retry with a corrected SELECT statement. "
    "Retry at most once; if still failing, stop and tell the user the error message above."
)

HINT_NO_DATABASES = (
    "No databases were returned. The configured user account may lack visibility permissions. "
    f"{STOP_AND_NOTIFY_USER_INSTRUCTION}"
)
