from __future__ import annotations

import asyncio
import argparse
import functools
from dataclasses import replace
from typing import Any, Callable

from mcp.server.fastmcp import FastMCP

from .config import (
    ALLOWED_TRANSPORTS,
    ServerSettings,
    Settings,
    get_settings,
    validate_settings,
)
from .logger import configure as configure_logger, info, error
from .tools import PLUGIN_REGISTRY


# AOP-style cross-cutting concern: intercept every tool call to inject structured logging.
# In Python, this is the Decorator pattern — wrapping a function to extend its behavior without modifying it.
def _wrap_with_logging(tool_name: str, fn: Callable) -> Callable:
    @functools.wraps(fn)
    async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
        info("tool.called", {"tool": tool_name, "args": kwargs})
        try:
            result = await fn(*args, **kwargs)
        except Exception as exc:
            error("tool.failed", {"tool": tool_name, "args": kwargs}, exc=exc)
            raise
        info("tool.completed", {"tool": tool_name, "args": kwargs, "result": result})
        return result

    @functools.wraps(fn)
    def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
        info("tool.called", {"tool": tool_name, "args": kwargs})
        try:
            result = fn(*args, **kwargs)
        except Exception as exc:
            error("tool.failed", {"tool": tool_name, "args": kwargs}, exc=exc)
            raise
        info("tool.completed", {"tool": tool_name, "args": kwargs, "result": result})
        return result

    return async_wrapper if asyncio.iscoroutinefunction(fn) else sync_wrapper


def create_mcp(settings: Settings) -> FastMCP:
    """Build and return a configured FastMCP instance with the enabled tools registered."""
    http_kwargs: dict[str, Any] = (
        {"host": settings.server.host, "port": settings.server.port}
        if settings.server.transport == "streamable-http"
        else {}
    )
    mcp = FastMCP(
        name=settings.server_name,
        instructions=settings.server_instructions,
        **http_kwargs,
    )
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
        help="Override server.transport from config.yaml for this run.",
    )
    parser.add_argument(
        "--host",
        help="Override server.host from config.yaml for this run.",
    )
    parser.add_argument(
        "--port",
        type=int,
        help="Override server.port from config.yaml for this run.",
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
            server = replace(server, transport=transport)
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
    try:
        if transport == "streamable-http":
            mcp.run(transport="streamable-http")
        else:
            mcp.run()
    except KeyboardInterrupt:
        pass
