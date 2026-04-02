from __future__ import annotations

import asyncio
import functools
from typing import Any, Callable

from mcp.server.fastmcp import FastMCP

from .config import Settings, get_settings
from .logger import configure as configure_logger, info, error
from .tools import INTEGRATION_REGISTRY


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
    mcp = FastMCP(
        name=settings.server_name,
        instructions=settings.server_instructions,
    )
    original_tool = mcp.tool

    def tool_with_logging(*deco_args: Any, **deco_kwargs: Any):
        decorator = original_tool(*deco_args, **deco_kwargs)

        def wrapper(fn: Callable) -> Callable:
            tool_name = deco_kwargs.get("name") or fn.__name__
            return decorator(_wrap_with_logging(tool_name, fn))

        return wrapper

    mcp.tool = tool_with_logging  # type: ignore[method-assign]

    for integration_name in settings.enabled_integrations:
        register_fn = INTEGRATION_REGISTRY.get(integration_name)
        if register_fn is None:
            known = ", ".join(sorted(INTEGRATION_REGISTRY))
            raise RuntimeError(
                f"Unknown integration '{integration_name}' in config.yaml. "
                f"Available integrations: {known}"
            )
        register_fn(mcp, settings)
    return mcp


def main() -> None:
    """Entry point for the MCP server."""
    settings = get_settings()
    configure_logger(log_dir=settings.log_dir, level=settings.log_level)
    mcp = create_mcp(settings)
    mcp.run()
