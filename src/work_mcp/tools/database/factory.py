from __future__ import annotations

from ...config import DB_TYPE_MYSQL, DB_TYPE_SQLSERVER, DatabaseSettings
from .base import AbstractDatabaseClient

SUPPORTED_DB_TYPES = frozenset({DB_TYPE_SQLSERVER, DB_TYPE_MYSQL})


def get_db_client(config: DatabaseSettings) -> AbstractDatabaseClient:
    if config.db_type == DB_TYPE_SQLSERVER:
        from .sqlserver import SqlServerClient

        return SqlServerClient(config)
    if config.db_type == DB_TYPE_MYSQL:
        from .mysql import MySqlClient

        return MySqlClient(config)
    raise ValueError(f"Unsupported db_type: {config.db_type!r}")


def check_database_connectivity(
    config: DatabaseSettings,
    *,
    timeout_seconds: int,
) -> dict[str, str]:
    if config.db_type == DB_TYPE_SQLSERVER:
        from .sqlserver import probe_sqlserver_connectivity

        return probe_sqlserver_connectivity(
            config,
            timeout_seconds=timeout_seconds,
        )
    if config.db_type == DB_TYPE_MYSQL:
        from .mysql import probe_mysql_connectivity

        return probe_mysql_connectivity(
            config,
            timeout_seconds=timeout_seconds,
        )
    raise ValueError(f"Unsupported db_type: {config.db_type!r}")
