from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from .tools.dingtalk import register_dingtalk_tools

mcp = FastMCP(
    name="work-assistant-mcp",
    instructions="A work-focused MCP server with notification tools for local agents.",
)

register_dingtalk_tools(mcp)


def main() -> None:
    """Entry point for the MCP server."""
    mcp.run()
