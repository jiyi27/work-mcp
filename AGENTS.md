# Repository Guidelines

## Project Structure

- `src/work_assistant_mcp/server.py` — MCP server composition root. Create the `FastMCP` instance here, define high-level server instructions, and register tool modules here.
- `src/work_assistant_mcp/config.py` — runtime configuration loading and validation. Centralize environment access in this module.
- `src/work_assistant_mcp/tools/` — MCP tool implementations. Each tool or integration should live in a focused module under this package.
- `src/work_assistant_mcp/__init__.py` — package entry point used by the console script.
- `tests/` — test suite for configuration logic, tool behavior, and regressions.
- `.env.example` — documented local development configuration.

## Development Commands

- `uv sync` — install dependencies into the local virtual environment.
- `uv run work-assistant-mcp` — run the MCP server through the packaged entry point.
- `uv run python -m work_assistant_mcp.server` — run the server module directly when debugging imports or startup behavior.
- `uv run pytest` — run the test suite.

## Architecture & Design Patterns

- **Single composition root**: Keep server bootstrapping in `server.py`. Tool modules should register themselves; they should not construct separate MCP server instances.
- **Config at the boundary**: Read environment variables in `config.py`, validate once, and pass typed settings into runtime code. Avoid scattered `os.getenv()` calls across tool modules.
- **Tool modularity**: Keep each tool or external integration isolated in its own module under `tools/`. Registration should stay simple and explicit.
- **Standard-library first**: This project is intentionally small. Prefer the Python standard library unless an added dependency clearly improves correctness or maintainability.
- **Actionable failures**: Raise concise `RuntimeError` messages for user-fixable issues such as missing config, invalid arguments, network failures, or upstream API errors.
- **Deterministic tool contract**: Successful tools should return structured dictionaries with stable keys. Avoid returning free-form text when structured data is possible.
- **Scale by addition, not abstraction**: This repository will grow by adding more tools. Prefer extending the existing pattern with small modules rather than introducing framework-heavy layers early.

## Coding Style

- Use type hints throughout. Keep signatures and return types explicit, especially for tool functions and config helpers.
- Prefer small functions with clear ownership: parse/validate inputs, load settings, perform I/O, and format result.
- Reuse shared constants for environment variable names, timeouts, or repeated strings once they appear in more than one place.
- Comments should explain intent or a non-obvious constraint, not restate the code.
- Keep modules focused. If a tool grows beyond basic request/response handling, extract helpers instead of letting one function accumulate branching.
- Write new code to fit the existing project shape. Do not introduce patterns that the repository does not already need.

## Testing Guidelines

- Use `pytest` for all tests. Name files `test_*.py`.
- Favor behavior tests over implementation-detail tests. Validate what a tool returns or raises for valid input, invalid input, missing config, and remote error cases.
- Mock network boundaries. Do not let tests call real external services.
- Add regression tests whenever changing config parsing, request payload shape, or error handling.
- Run `uv run pytest` before finalizing substantial changes.

## Configuration & Security

- Keep secrets only in environment variables or local `.env`; never commit real tokens, webhook URLs, or other credentials.
- Update `.env.example` whenever adding a required setting.
- Validate required configuration early and fail fast with a clear error message.
- Treat outbound integrations as untrusted boundaries: set explicit timeouts, surface upstream errors clearly, and avoid leaking unnecessary secret values in exceptions or logs.

## Change Guidance For LLM Agents

- Prefer small, local edits that preserve the current architecture. Do not introduce frameworks, DI layers, or abstractions the project does not need yet.
- When adding a new tool, place it under `src/work_assistant_mcp/tools/`, keep its registration explicit in `src/work_assistant_mcp/server.py`, document any required configuration, and add tests for success and failure paths.
- When changing runtime behavior, update docs in the same change if startup, configuration, or tool usage changes.
- Do not overwrite unrelated local modifications in this repository. The worktree may already contain user changes.

## Commit Message Guidelines

- Format: `<type>: <summary>` or `<type>(<scope>): <summary>`.
- Common types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`.
- Keep messages short, specific, and lowercase.
