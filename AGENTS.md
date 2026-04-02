# Repository Guidelines

## Project Structure

- `src/work_assistant_mcp/server.py` — MCP server composition root. Create the `FastMCP` instance here, define high-level server instructions, and register integration modules here.
- `src/work_assistant_mcp/config.py` — runtime configuration loading and validation. Centralize environment access in this module.
- `src/work_assistant_mcp/tools/` — MCP tool implementations. Keep each integration isolated here, either as a single module for simple cases or as a small package when it grows into multiple focused files.
- `src/work_assistant_mcp/__init__.py` — package entry point used by the console script.
- `tests/` — test suite for configuration logic, tool behavior, and regressions.
- `.env.example` — documented local development configuration.

## Development Commands

- `uv sync` — install dependencies into the local virtual environment.
- `uv run work-assistant-mcp` — run the MCP server through the packaged entry point.
- `uv run python -m work_assistant_mcp.server` — run the server module directly when debugging imports or startup behavior.
- `uv run pytest` — run the test suite.

## Architecture & Design Patterns

- **Single composition root**: Keep server bootstrapping in `server.py`. Integration modules should register their tools there; they should not construct separate MCP server instances.
- **Config at the boundary**: Read environment variables in `config.py`, validate once, and pass typed settings into runtime code. Avoid scattered `os.getenv()` calls across tool modules.
- **Integration modularity**: Keep each external integration isolated under `tools/`. Use a single module for simple integrations and a package for larger ones. Each integration may expose multiple tools, but registration should stay simple and explicit.
- **Standard-library first**: This project is intentionally small. Prefer the Python standard library unless an added dependency clearly improves correctness or maintainability.
- **Actionable failures**: Raise concise `RuntimeError` messages for user-fixable issues such as missing config, invalid arguments, network failures, or upstream API errors.
- **Deterministic tool contract**: Successful tools should return structured dictionaries with stable keys. Avoid returning free-form text when structured data is possible.
- **Scale by addition, not abstraction**: This repository will grow by adding more tools. Prefer extending the existing pattern with small modules rather than introducing framework-heavy layers early.
- **MCP tool design**: Before adding or modifying any tool, read [docs/tool-design.md](docs/tool-design.md). It covers naming conventions, description style, parameter annotations, output shape, error categories, and what must not appear in tool output.

## Testing Guidelines

- Favor behavior tests over implementation-detail tests. Validate what a tool returns or raises for valid input, invalid input, missing config, and remote error cases.
- Mock network boundaries. Do not let tests call real external services.
- Add regression tests whenever changing config parsing, request payload shape, or error handling.

## Configuration & Security

- Update `.env.example` whenever adding a required setting.
- Validate required configuration early and fail fast with a clear error message.

## Change Guidance For LLM Agents

- Prefer small, local edits that preserve the current architecture. Do not introduce frameworks, DI layers, or abstractions the project does not need yet.
- When adding a new integration or a new tool within an integration, place it under `src/work_assistant_mcp/tools/`, keep its registration explicit in `src/work_assistant_mcp/server.py`, document any required configuration, and add tests for success and failure paths.
- When changing runtime behavior, update docs in the same change if startup, configuration, or tool usage changes.
- Do not overwrite unrelated local modifications in this repository. The worktree may already contain user changes.

## Commit Message Guidelines

- Format: `<type>: <summary>` or `<type>(<scope>): <summary>`.
- Common types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`.
- Keep messages short, specific, and lowercase.

## Final Response Requirement For LLM Agents

- After any change to code, tests, docs, or configuration files, include one suggested commit message in the final response.
- Follow the commit message format above.
- Put it on its own line prefixed with `Suggested commit message:`.
