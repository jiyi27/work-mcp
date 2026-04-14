from __future__ import annotations

from pathlib import Path


class PathNotAllowedError(Exception):
    """The resolved path falls outside all configured roots."""


def resolve_allowed_path(raw_path: str, allowed_roots: tuple[Path, ...]) -> Path:
    """Resolve the given path and verify it falls inside at least one allowed root.

    Accepts absolute paths (e.g. those returned by get_allowed_roots).
    Normalizes symlinks and '..' via resolve().
    """
    resolved = Path(raw_path).resolve()
    for root in allowed_roots:
        try:
            resolved.relative_to(root)
            return resolved
        except ValueError:
            continue
    raise PathNotAllowedError(raw_path)
