from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any

from work_mcp.config import get_settings
from work_mcp.logger import configure as configure_logger
from work_mcp.server import create_mcp


def _build_mcp():
    settings = get_settings()
    configure_logger(log_dir=settings.log_dir, level=settings.log_level)
    return create_mcp(settings)


async def _list_tools() -> None:
    mcp = _build_mcp()
    tools = await mcp.list_tools()
    payload = [
        {
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.inputSchema,
            "output_schema": tool.outputSchema,
        }
        for tool in tools
    ]
    print(json.dumps(payload, ensure_ascii=False, indent=2))


async def _describe_tool(name: str) -> None:
    mcp = _build_mcp()
    tools = await mcp.list_tools()
    for tool in tools:
        if tool.name != name:
            continue

        payload = {
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.inputSchema,
            "output_schema": tool.outputSchema,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    raise RuntimeError(f"Unknown tool: {name}")


async def _call_tool(name: str, arguments: dict[str, Any]) -> None:
    mcp = _build_mcp()
    content, structured = await mcp.call_tool(name, arguments)

    rendered_content = []
    for item in content:
        rendered_content.append(
            {
                "type": getattr(item, "type", None),
                "text": getattr(item, "text", None),
            }
        )

    print(
        json.dumps(
            {
                "content": rendered_content,
                "structured": structured,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Preview locally registered MCP tools and invoke one directly."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list", help="List all locally registered tools.")

    describe_parser = subparsers.add_parser(
        "describe",
        help="Show schema details for one local tool.",
    )
    describe_parser.add_argument("tool_name", help="Registered MCP tool name.")

    call_parser = subparsers.add_parser("call", help="Invoke one local tool by name.")
    call_parser.add_argument("tool_name", help="Registered MCP tool name.")
    call_parser.add_argument(
        "--args",
        default="{}",
        help="JSON object passed as tool arguments.",
    )

    return parser.parse_args()


def main() -> None:
    try:
        args = _parse_args()
        if args.command == "list":
            asyncio.run(_list_tools())
            return

        if args.command == "describe":
            asyncio.run(_describe_tool(args.tool_name))
            return

        try:
            parsed_args = json.loads(args.args)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Invalid JSON for --args: {exc.msg}") from exc

        if not isinstance(parsed_args, dict):
            raise RuntimeError("--args must decode to a JSON object.")

        asyncio.run(_call_tool(args.tool_name, parsed_args))
    except Exception as exc:
        print(f"preview_tool failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
