# add new remote-fs plugin

## Background

The local agent runs outside the target server environment. In practice, many diagnosis tasks require server-side context such as deployed code, runtime configuration files, and recent logs.

Granting full remote shell access would solve that visibility gap, but it expands the risk surface far beyond the actual need. The need here is observation, not execution.

## Purpose

This proposal defines a small set of read-only MCP tools for inspecting server-side files over a remote transport such as Streamable HTTP.

The goals are:

- Let the agent inspect deployed code, configuration, and logs without write access
- Keep the tool surface narrow and predictable
- Return stable structured data so the agent can navigate efficiently
- Restrict access to configured read-only roots
- Avoid wasteful full-file reads unless the agent explicitly chooses to read a range

## Scope

These tools are intended for:

- Viewing directory structure under approved roots
- Searching for files by name or by content
- Reading a selected range from a known file
- Searching a known file from the end toward the beginning to find the newest matching lines

These tools are not intended for:

- Writing or editing files
- Running arbitrary shell commands
- Managing processes or services
- Streaming log follow output
- Accessing paths outside configured allowed roots

## Access Model

The server operator configures one or more allowed roots. Each root represents a read-only area the agent may inspect, such as:

- application source directory
- configuration directory
- log directory

Each tool that accepts a path must only operate on paths under those configured roots.

## Workflow

```
get_allowed_roots          → learn which roots are available
    │
    ├─ list_tree           → browse directory layout
    │
    ├─ search_files        → locate files or matching lines across roots
    │       │
    │       └─ read_file   → read a specific range from a known file
    │
    ├─ read_file           → read a known file from a specific line or from the tail
    │
    └─ search_file_reverse → find the newest matching lines in a known file
```

The design intent is:

- `search_files` locates where to look
- `search_file_reverse` locates the newest relevant log matches in one file
- `read_file` reads only the necessary range from a known file

This avoids turning the remote-fs plugin into a "read everything" interface.

## Path Access Control

All tools that accept a `path` must resolve it through one shared guard.

The remote-fs case differs from a local working-directory tool in two ways:

- the server may expose multiple roots
- the agent may legitimately pass absolute paths returned by `get_allowed_roots`

So the access check must:

- allow absolute paths
- normalize symlinks and `..` with `resolve()`
- verify that the resolved path is inside at least one configured root

Recommended shared helper:

```python
from pathlib import Path


class PathNotAllowedError(Exception):
    """The resolved path falls outside all configured roots."""


def resolve_allowed_path(raw_path: str, allowed_roots: tuple[Path, ...]) -> Path:
    resolved = Path(raw_path).resolve()
    for root in allowed_roots:
        try:
            resolved.relative_to(root)
            return resolved
        except ValueError:
            continue
    raise PathNotAllowedError(raw_path)
```

Resolve and validate root paths once in config loading. Do not repeatedly resolve configured roots on every tool call.

Example config shape:

```yaml
remote_fs:
  roots:
    - name: app
      path: /srv/myapp
      kind: code
      description: Deployed application source

    - name: logs
      path: /var/log/myapp
      kind: logs
      description: Application log files

    - name: config
      path: /etc/myapp
      kind: config
      description: Production configuration
```

```python
@dataclass(frozen=True)
class AllowedRoot:
    name: str
    path: Path
    kind: str
    description: str


@dataclass(frozen=True)
class RemoteFsSettings:
    roots: tuple[AllowedRoot, ...]
```

## Tool Set

The final tool set is intentionally small:

1. `get_allowed_roots`
2. `list_tree`
3. `search_files`
4. `read_file`
5. `search_file_reverse`

### Why these 5

- `get_allowed_roots` tells the agent what it is allowed to inspect
- `list_tree` supports browsing when the exact target file is unknown
- `search_files` supports cross-file discovery without reading everything
- `read_file` supports reading only a selected range from a known file
- `search_file_reverse` keeps the useful part of today's `log_search`: newest-match-first lookup in append-heavy files

### Why not `stat_path`

`stat_path` is not core to the workflow:

- `list_tree` already returns file type, size, and `mtime`
- `read_file` and search tools already return path-related failures

Checking file metadata is easy, but it does not justify a dedicated tool at this stage.

## Tool Details

### `get_allowed_roots`

Return the list of configured read-only roots that the agent may access.

Parameters: none

**Success**

```json
{
  "success": true,
  "roots": [
    {
      "name": "app",
      "path": "/srv/myapp",
      "kind": "code",
      "description": "Deployed application source"
    },
    {
      "name": "logs",
      "path": "/var/log/myapp",
      "kind": "logs",
      "description": "Application log files"
    }
  ],
  "hint": "..."
}
```

**Empty**

```json
{
  "success": true,
  "roots": [],
  "hint": "..."
}
```

---

### `list_tree`

Return a directory listing for a path under an allowed root.

Parameters:

- `path`: directory path to inspect
- `depth`: number of directory levels to expand

The server caps the number of returned entries. Hidden files and directories are included.

**Success**

```json
{
  "success": true,
  "path": "/srv/myapp/config",
  "entries": [
    {
      "path": "/srv/myapp/config/app.yaml",
      "name": "app.yaml",
      "type": "file",
      "size": 1824,
      "mtime": "2026-04-14T09:10:00Z",
      "depth": 1
    },
    {
      "path": "/srv/myapp/config/env",
      "name": "env",
      "type": "directory",
      "size": null,
      "mtime": "2026-04-13T22:41:00Z",
      "depth": 1
    }
  ],
  "truncated": false,
  "hint": "..."
}
```

**Recoverable failures**

| `error_type` | Cause |
|---|---|
| `path_not_found` | The path does not exist |
| `not_a_directory` | The path exists but is a file |
| `path_not_allowed` | The path is outside all configured roots |

---

### `search_files`

Search file contents or file names under one or more allowed roots.

Use this to locate which file and line to inspect next.

Parameters:

- `query`: text to search for in file contents. Omit to search by file name only using `path_glob`
- `root`: root name or path to limit the search scope
- `path_glob`: file name filter such as `**/*.py` or `**/*.log`
- `regex`: whether `query` is a regular expression
- `max_matches`: maximum number of matches to return

This tool is for discovery, not full reading. It should return compact match previews, not large content blocks.

**Success**

```json
{
  "success": true,
  "query": "DATABASE_URL",
  "matches": [
    {
      "path": "/srv/myapp/.env",
      "line": 12,
      "preview": "DATABASE_URL=postgres://..."
    },
    {
      "path": "/srv/myapp/config/settings.py",
      "line": 34,
      "preview": "database_url = os.getenv(\"DATABASE_URL\")"
    }
  ],
  "match_count": 2,
  "truncated": false,
  "hint": "..."
}
```

**No matches**

```json
{
  "success": true,
  "query": "DATABASE_URL",
  "matches": [],
  "match_count": 0,
  "truncated": false,
  "hint": "..."
}
```

**Recoverable failures**

| `error_type` | Cause |
|---|---|
| `path_not_allowed` | The specified root is outside all configured roots |
| `invalid_regex` | `regex: true` but `query` is not a valid regular expression |
| `invalid_argument` | `query` and `path_glob` are both absent |

---

### `read_file`

Read a selected range from a known file.

Use this only after the file is already known. The intent is targeted reading, not dumping the whole file by default.

Parameters:

- `path`: file path to read
- `start_line`: 1-based line number to start from
- `max_lines`: maximum number of lines to return
- `tail`: number of lines to return from the end of the file. When `tail > 0`, ignore `start_line`

This keeps the read API simple:

- normal read: `path + start_line + max_lines`
- tail read: `path + tail`

Avoid combining `start_line`, `end_line`, and `tail` in one interface. That adds parameter combinations without improving the core workflow.

**Success**

```json
{
  "success": true,
  "path": "/srv/myapp/config/settings.py",
  "start_line": 1,
  "end_line": 80,
  "total_lines": 240,
  "content": "     1\timport os\n     2\t...\n",
  "truncated": false,
  "hint": "..."
}
```

**Tail read**

```json
{
  "success": true,
  "path": "/var/log/myapp/server.log",
  "tail": 100,
  "start_line": 1941,
  "end_line": 2040,
  "total_lines": 2040,
  "content": "...",
  "truncated": false,
  "hint": "..."
}
```

**Recoverable failures**

| `error_type` | Cause |
|---|---|
| `path_not_found` | The path does not exist |
| `not_a_file` | The path exists but is a directory |
| `path_not_allowed` | The path is outside all configured roots |
| `invalid_argument` | `start_line`, `max_lines`, or `tail` is invalid |
| `binary_file_not_supported` | The file appears to be binary |

---

### `search_file_reverse`

Search a known file from the end toward the beginning and return the newest matches first.

Use this for append-heavy files such as logs, where the latest matching lines are usually the useful ones.

Parameters:

- `path`: file path to search
- `query`: text to search for
- `max_matches`: maximum number of matches to return
- `before`: number of context lines before each match
- `after`: number of context lines after each match
- `regex`: whether `query` is a regular expression

This tool keeps the useful part of the current log search design:

- scan from the end
- stop after enough recent matches are found
- return small contextual windows instead of the whole file

It is not limited to JSON logs. It works for plain text logs and other line-oriented files as well.

**Success**

```json
{
  "success": true,
  "path": "/var/log/myapp/server.log",
  "query": "ERROR",
  "matches": [
    {
      "line": 2040,
      "match": "ERROR request_id=abc123 timeout while calling upstream",
      "before": [
        "INFO request_id=abc123 calling upstream"
      ],
      "after": []
    },
    {
      "line": 2018,
      "match": "ERROR request_id=xyz999 invalid response payload",
      "before": [
        "INFO request_id=xyz999 processing request"
      ],
      "after": [
        "WARN request_id=xyz999 response parse failed"
      ]
    }
  ],
  "match_count": 2,
  "order": "newest_first",
  "truncated": false,
  "hint": "..."
}
```

**No matches**

```json
{
  "success": true,
  "path": "/var/log/myapp/server.log",
  "query": "ERROR",
  "matches": [],
  "match_count": 0,
  "order": "newest_first",
  "truncated": false,
  "hint": "..."
}
```

**Recoverable failures**

| `error_type` | Cause |
|---|---|
| `path_not_found` | The path does not exist |
| `not_a_file` | The path exists but is a directory |
| `path_not_allowed` | The path is outside all configured roots |
| `invalid_argument` | `query`, `max_matches`, `before`, or `after` is invalid |
| `invalid_regex` | `regex: true` but `query` is not a valid regular expression |
| `binary_file_not_supported` | The file appears to be binary |

## Hint Design

The design principle is:

- descriptions stay short
- parameter annotations exist only when the name is ambiguous
- hints carry the workflow guidance

All hint text belongs in `strings.py`. Do not inline hint text at the call site.

Several error cases share the same instruction across tools. Define those once and reuse them.

### Shared constants

```python
HINT_PATH_NOT_ALLOWED = (
    "The path is outside all configured roots. Stop and notify the user: "
    "the requested path is not accessible."
)

HINT_PATH_NOT_FOUND = (
    "The path does not exist. Do not guess a replacement path. Use "
    "get_allowed_roots, list_tree, or search_files to locate the correct path."
)

HINT_NOT_A_FILE = (
    "The path is a directory, not a file. Use list_tree to inspect its contents."
)

HINT_NOT_A_DIRECTORY = (
    "The path is a file, not a directory. Use read_file to read a range from it."
)

HINT_BINARY_FILE_NOT_SUPPORTED = (
    "The file appears to be binary. Do not retry with the same tool. "
    "Notify the user that this tool only supports text files."
)
```

### `get_allowed_roots`

```python
HINT_ROOTS_FOUND = (
    "The available roots are now known. Choose a root and continue with "
    "list_tree or search_files."
)

HINT_NO_ROOTS = (
    "No roots are configured on the server. Stop and notify the user: "
    "the remote inspection tools have no allowed roots configured."
)
```

### `list_tree`

```python
HINT_LIST_TREE_COMPLETE = (
    "The directory listing is complete. If you already know the target file, "
    "use read_file. Otherwise use search_files to narrow the search."
)

HINT_LIST_TREE_TRUNCATED = (
    "The directory listing reached the server limit. Do not keep browsing "
    "blindly. Use search_files with a narrower root or path_glob."
)

HINT_LIST_TREE_PATH_NOT_FOUND = (
    "The directory path does not exist. Verify the path against the allowed "
    "roots or use list_tree on a higher-level directory first."
)
```

### `search_files`

```python
HINT_SEARCH_COMPLETE = (
    "Matches were found. Pick the most relevant path and line, then use "
    "read_file to read a small range around that location."
)

HINT_SEARCH_TRUNCATED = (
    "The search result reached the server limit. Narrow the search with a more "
    "specific root, path_glob, or query before retrying."
)

HINT_SEARCH_NO_MATCHES = (
    "No matches were found. Check the query text, file pattern, and chosen "
    "root. If the target is a log file and you already know its path, use "
    "search_file_reverse instead of broad cross-file search."
)

HINT_SEARCH_INVALID_REGEX = (
    "The query is not a valid regular expression. Fix the pattern and retry."
)

HINT_SEARCH_INVALID_ARGUMENT = (
    "At least one of query or path_glob is required. Provide a content query, "
    "a file name pattern, or both."
)
```

### `read_file`

```python
HINT_READ_FILE_COMPLETE = (
    "The requested range was returned. Continue analysis, or call read_file "
    "again with a different range if more context is needed."
)

HINT_READ_FILE_TRUNCATED = (
    "More lines exist outside the returned range. If more context is needed, "
    "call read_file again with the next range."
)

HINT_READ_FILE_EMPTY = (
    "The file exists but contains no text lines."
)

HINT_READ_FILE_INVALID_ARGUMENT = (
    "The requested line range is invalid. Use a positive start_line, positive "
    "max_lines, and a non-negative tail."
)
```

### `search_file_reverse`

```python
HINT_REVERSE_SEARCH_COMPLETE = (
    "Recent matches were found. Use the returned context to analyze the issue. "
    "If more surrounding lines are needed, call read_file for the matched path "
    "and line range."
)

HINT_REVERSE_SEARCH_TRUNCATED = (
    "The newest matches reached the server limit. If you need fewer but richer "
    "results, retry with a more specific query or smaller match count."
)

HINT_REVERSE_SEARCH_NO_MATCHES = (
    "No matches were found in this file. Verify the query text. If the file "
    "path may be wrong, use list_tree or search_files first."
)

HINT_REVERSE_SEARCH_INVALID_ARGUMENT = (
    "The search arguments are invalid. Provide a non-empty query and valid "
    "positive limits for matches and context lines."
)

HINT_REVERSE_SEARCH_INVALID_REGEX = (
    "The query is not a valid regular expression. Fix the pattern and retry."
)
```

## Output Shape Summary

All tools return structured JSON with stable field names.

**Success**

```json
{
  "success": true,
  "<data fields>": "...",
  "hint": "..."
}
```

The `hint` field should be present on success whenever the result implies a concrete next step or when the result shape may otherwise lead the agent to over-read or re-run the wrong tool.

**Recoverable failure**

```json
{
  "success": false,
  "error_type": "<stable_string>",
  "hint": "<direct instruction to the agent>"
}
```

**Non-recoverable failure**

```json
{
  "success": false,
  "error_type": "internal_error",
  "message": "<error detail for the user>",
  "hint": "<retry policy and stop instruction>"
}
```

## Tool Descriptions and Parameter Annotations

The design intent here is to keep descriptions short. The description should answer only:

- what data the tool returns
- when the agent should call it

Do not push workflow logic into `description=`. That belongs in hints.

Only annotate parameters whose names are not self-explanatory.

### `get_allowed_roots`

```python
GET_ALLOWED_ROOTS_DESCRIPTION = """\
Return the list of server directories the agent may inspect.
"""
```

No parameter annotations needed.

### `list_tree`

```python
LIST_TREE_DESCRIPTION = """\
Return a directory listing for a path under an allowed root.
"""
```

```python
def list_tree(
    path: str,
    depth: Annotated[int, "Number of directory levels to expand."] = 1,
) -> dict: ...
```

### `search_files`

```python
SEARCH_FILES_DESCRIPTION = """\
Search file contents or file names under allowed roots.
"""
```

```python
def search_files(
    query: Annotated[str, "Text to find in file contents. Omit to search by file name only using path_glob."] = "",
    root: Annotated[str, "Root name or path to limit the search scope. Omit to search all roots."] = "",
    path_glob: Annotated[str, "File name filter such as **/*.py or **/*.log."] = "",
    regex: Annotated[bool, "Treat query as a regular expression."] = False,
    max_matches: int = 50,
) -> dict: ...
```

### `read_file`

```python
READ_FILE_DESCRIPTION = """\
Read a selected range from a known file.
"""
```

```python
def read_file(
    path: str,
    start_line: Annotated[int, "1-based line number to start from."] = 1,
    max_lines: Annotated[int, "Maximum number of lines to return."] = 200,
    tail: Annotated[int, "Read the last N lines. Overrides start_line when greater than 0."] = 0,
) -> dict: ...
```

### `search_file_reverse`

```python
SEARCH_FILE_REVERSE_DESCRIPTION = """\
Search a known file from the end and return the newest matches first.
"""
```

```python
def search_file_reverse(
    path: str,
    query: str,
    max_matches: Annotated[int, "Maximum number of matches to return."] = 20,
    before: Annotated[int, "Number of context lines before each match."] = 3,
    after: Annotated[int, "Number of context lines after each match."] = 3,
    regex: Annotated[bool, "Treat query as a regular expression."] = False,
) -> dict: ...
```

## Summary

This tool set is intentionally narrow.

It gives the agent enough remote visibility to:

- discover accessible server roots
- browse directories
- locate relevant files and line numbers
- read only selected file ranges
- find the newest matching lines in log-like files

It does not try to be a remote shell, a process inspector, or a full log platform. That is deliberate.
