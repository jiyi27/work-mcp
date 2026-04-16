from __future__ import annotations

import asyncio
import argparse
import functools
from dataclasses import replace
from typing import Any, Callable

from mcp.server.fastmcp import FastMCP

from .config import (
    DEFAULT_HTTP_HOST,
    DEFAULT_HTTP_PORT,
    ServerSettings,
    Settings,
    get_settings,
    validate_settings,
)
from .logger import configure as configure_logger, info, error
from .tools import PLUGIN_REGISTRY

ALLOWED_TRANSPORTS = frozenset({"stdio", "streamable-http"})
SERVER_INSTRUCTIONS = """\
You are connected to a work-assistant MCP server for a PHP application that runs exclusively on a remote server.

ENVIRONMENT FACTS
- The local workspace is for editing source code only.
- Real execution happens on the remote server, not on the local machine.
- Local edits are typically synced to the server within a few seconds.
- PHP is interpreted on the server, so no build step is normally required after sync.
- The local machine may not have the runtime config, shared database, global constants, or external service connections that exist on the server.
- Under normal conditions, local source code and server source code should match.
"""

"""
REMOTE FILE TOOLS: BOUNDARIES
- Remote filesystem tools are for inspecting runtime information on the server.
- Use them for:
  - live request and error logs
  - runtime config, bootstrap config, and global constants
- Do not use remote filesystem tools to read normal project source code.
- Read project code from the local workspace instead.

EXCEPTION
- If you suspect a sync failure and believe the server is still running older code, you may inspect the specific remote source file only to verify whether the sync took effect.

SERVER ROOTS
- The server may expose one or more allowed roots such as:
  - `kind=logs` for log inspection
  - `kind=config` for runtime config and constants
- Call `remote_describe_environment` at the start of a session when the available roots are not already known.
- If the roots were already established earlier in the conversation, do not call it again unnecessarily.

OPERATING RULE
- Use local code for source inspection.
- Use remote tools only for runtime evidence and server-side environment data.
"""

# AOP-style cross-cutting concern: intercept every tool call to inject structured logging.
# In Python, this is the Decorator pattern — wrapping a function to extend its behavior without modifying it.
def _wrap_with_logging(tool_name: str, fn: Callable) -> Callable:
    @functools.wraps(fn)
    async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
        info("tool.request", {"tool": tool_name, "args": kwargs})
        try:
            result = await fn(*args, **kwargs)
        except Exception as exc:
            error("tool.failed", {"tool": tool_name, "args": kwargs}, exc=exc)
            raise
        info("tool.response", {"tool": tool_name, "result": result})
        return result

    @functools.wraps(fn)
    def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
        info("tool.request", {"tool": tool_name, "args": kwargs})
        try:
            result = fn(*args, **kwargs)
        except Exception as exc:
            error("tool.failed", {"tool": tool_name, "args": kwargs}, exc=exc)
            raise
        info("tool.response", {"tool": tool_name, "result": result})
        return result

    return async_wrapper if asyncio.iscoroutinefunction(fn) else sync_wrapper


def create_mcp(settings: Settings) -> FastMCP:
    """Build and return a configured FastMCP instance with the enabled tools registered."""
    http_kwargs: dict[str, Any] = (
        {"host": settings.server.host, "port": settings.server.port}
        if settings.server.transport == "streamable-http"
        else {}
    )
    mcp = FastMCP(instructions=SERVER_INSTRUCTIONS, **http_kwargs)
    original_tool = mcp.tool

    # Replaces mcp.tool with a version that wraps each registered function with logging.
    def mcp_tool_with_logging(*deco_args: Any, **deco_kwargs: Any):
        decorator = original_tool(*deco_args, **deco_kwargs)

        def wrapper(fn: Callable) -> Callable:
            tool_name = deco_kwargs.get("name") or fn.__name__
            return decorator(_wrap_with_logging(tool_name, fn))

        return wrapper

    # Monkey-patch: replace the original mcp.tool function with our wrapped version.
    # From this point on, every @mcp.tool(...) call goes through mcp_tool_with_logging instead.
    mcp.tool = mcp_tool_with_logging

    for plugin_name in settings.enabled_plugins:
        register_fn = PLUGIN_REGISTRY.get(plugin_name)
        if register_fn is None:
            known = ", ".join(sorted(PLUGIN_REGISTRY))
            raise RuntimeError(
                f"Unknown plugin '{plugin_name}' in config.yaml. "
                f"Available plugins: {known}"
            )
        register_fn(mcp, settings)
    return mcp


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="work-mcp")
    parser.add_argument(
        "--transport",
        choices=sorted(ALLOWED_TRANSPORTS),
        help="Select how the server is exposed for this run.",
    )
    parser.add_argument(
        "--host",
        help="Override the HTTP host for this run.",
    )
    parser.add_argument(
        "--port",
        type=int,
        help="Override the HTTP port for this run.",
    )
    return parser


def _apply_cli_overrides(
    settings: Settings,
    *,
    transport: str | None,
    host: str | None,
    port: int | None,
) -> Settings:
    server = settings.server
    if transport is not None:
        if transport == "stdio":
            server = ServerSettings(transport=transport, host=None, port=None)
        else:
            server = ServerSettings(
                transport=transport,
                host=DEFAULT_HTTP_HOST,
                port=DEFAULT_HTTP_PORT,
            )
    if host is not None:
        server = replace(server, host=host)
    if port is not None:
        server = replace(server, port=port)
    if server.transport == "stdio":
        server = replace(server, host=None, port=None)
    updated = replace(settings, server=server)
    validate_settings(updated)
    return updated


def main(argv: list[str] | None = None) -> None:
    """Entry point for the MCP server."""
    try:
        args = _build_parser().parse_args(argv)
        settings = _apply_cli_overrides(
            get_settings(),
            transport=args.transport,
            host=args.host,
            port=args.port,
        )
        configure_logger(log_dir=settings.log_dir, level=settings.log_level)
        mcp = create_mcp(settings)
        transport = settings.server.transport
        if transport == "streamable-http":
            mcp.run(transport="streamable-http")
        else:
            mcp.run()
    except RuntimeError as exc:
        raise SystemExit(f"Error: {exc}") from None
    except KeyboardInterrupt:
        pass
