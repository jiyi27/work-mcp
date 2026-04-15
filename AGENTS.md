# Agent Guidance For Seahorse

This file is written for coding agents working in this repository. Follow these rules by default unless the user explicitly asks for something else. The guidance here may become stale as the codebase evolves, so if the repository and this file disagree, follow the code, call out the mismatch, and suggest updating this document.

## Project Structure

- `src/work_assistant_mcp/server.py` — MCP server composition root. Create the `FastMCP` instance here, define high-level server instructions, and register integration modules here.
- `src/work_assistant_mcp/config.py` — runtime configuration loading and validation. Centralize environment access in this module.
- `src/work_assistant_mcp/tools/` — MCP tool implementations. Keep each integration isolated here, either as a single module for simple cases or as a small package when it grows into multiple focused files.
- `src/work_assistant_mcp/__init__.py` — package entry point used by the console script.
- `tests/` — test suite for configuration logic, tool behavior, and regressions.
- `.env.example` — documented local development configuration.

## Architecture & Design Patterns

- **Single composition root**: Keep server bootstrapping in `server.py`. Integration modules should register their tools there; they should not construct separate MCP server instances.
- **Config at the boundary**: Read environment variables in `config.py`, validate once, and pass typed settings into runtime code. Avoid scattered `os.getenv()` calls across tool modules.
- **Actionable failures**: Raise concise `RuntimeError` messages for user-fixable issues such as missing config, invalid arguments, network failures, or upstream API errors.
- **Deterministic tool contract**: Successful tools should return structured dictionaries with stable keys. Avoid returning free-form text when structured data is possible.
- **MCP tool design**: Before adding or modifying any tool, read [docs/tool-design.md](docs/tool-design.md). It covers naming conventions, description style, parameter annotations, output shape, error categories, and what must not appear in tool output.

## Coding Style

- If the same string, number, metadata field, or structural assumption appears in more than one place, extract it to a shared constant, `Enum`, helper, or schema definition before writing the second use.
- Keep prompt text, hint text, and other reusable long strings in one clear location rather than scattering them across multiple files.
- Keep functions focused. Do not mix unrelated responsibilities in one function when that would make the code harder to extend, test, or reuse.
- Comments should explain intent or constraints, not restate obvious code behavior.

## Testing

- Write unit tests for pure logic with meaningful branching or edge cases.
- Use integration or wiring tests when the risk is config loading, service composition, repository behavior, or API/MCP adapters.
- Add regression tests when changing merge logic, prompt parsing, config loading, or storage format.
- Use `uv run --group dev python -m pytest` to run tests directly, or `make test` for the same command through the repo wrapper.
- Check `pyproject.toml` or `Makefile` for available commands.

## Final Phase

- After completing a task, verify it works. Run existing tests to confirm no regressions and no layer boundaries are broken.
- Do not add new tests by default. First check if existing tests already cover the changed behavior. Only add tests when the change is high-risk — core logic, complex branching, or merge/parse behavior, etc.
- If code changed, include a suggested commit message:
  - Format: `<type>: <summary>` or `<type>(<scope>): <summary>`
  - Common types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`
  - Short, specific, and lowercase.
