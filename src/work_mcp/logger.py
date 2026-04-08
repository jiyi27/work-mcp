from __future__ import annotations

import inspect
import json
import os
import sys
import traceback
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


_context_id_var: ContextVar[str] = ContextVar("context_id", default="")
_LEVELS = {"debug": 0, "info": 1, "warning": 2, "error": 3}
_LOGGER_FILE = os.path.abspath(__file__)
_MAX_LOG_STRING_LENGTH = 1000
_LOG_TRUNCATION_MARKER = "...<truncated>..."


@dataclass
class _LoggerConfig:
    log_dir: Path = Path("logs")
    level: str = "info"


_config = _LoggerConfig()


def configure(*, log_dir: str | Path = "logs", level: str = "info") -> None:
    """Update logger settings for the current process."""
    normalized_level = level.lower()
    if normalized_level not in _LEVELS:
        valid = ", ".join(sorted(_LEVELS))
        raise ValueError(f"Unknown log level: {level!r}. Expected one of: {valid}")

    _config.log_dir = Path(log_dir)
    _config.level = normalized_level


def set_context_id(context_id: str) -> None:
    _context_id_var.set(context_id)


def get_context_id() -> str:
    return _context_id_var.get()


def clear_context_id() -> None:
    _context_id_var.set("")


def _serialize_exception(exc: BaseException) -> dict[str, object]:
    frames = traceback.extract_tb(exc.__traceback__)
    result: dict[str, object] = {
        "error_type": type(exc).__name__,
        "error": str(exc),
        "traceback": "".join(
            traceback.format_exception(type(exc), exc, exc.__traceback__)
        ),
    }
    if not frames:
        return result

    origin_frame = frames[0]
    trigger_frame = frames[-1]
    result["origin"] = {
        "file": os.path.basename(origin_frame.filename),
        "line": origin_frame.lineno,
        "func": origin_frame.name,
    }
    result["trigger"] = {
        "file": os.path.basename(trigger_frame.filename),
        "line": trigger_frame.lineno,
        "func": trigger_frame.name,
        "code": trigger_frame.line,
    }
    result["call_chain"] = [
        f"{os.path.basename(frame.filename)}:{frame.lineno} {frame.name}"
        for frame in frames
    ]
    return result


def _serialize_exception_chain(exc: BaseException) -> list[dict[str, object]]:
    chain: list[dict[str, object]] = []
    seen: set[int] = set()
    current: BaseException | None = exc

    while current is not None and id(current) not in seen:
        seen.add(id(current))
        chain.append(_serialize_exception(current))
        current = current.__cause__ or current.__context__

    return chain


def _caller() -> dict[str, object]:
    for frame_info in inspect.stack()[1:]:
        if os.path.abspath(frame_info.filename) == _LOGGER_FILE:
            continue
        return {
            "file": os.path.basename(frame_info.filename),
            "line": frame_info.lineno,
            "func": frame_info.function,
        }

    return {
        "file": os.path.basename(_LOGGER_FILE),
        "line": 0,
        "func": "unknown",
    }


def _base_record(topic: str, data: dict[str, Any]) -> dict[str, Any]:
    now = datetime.now().astimezone()
    return {
        "ts": now.isoformat(timespec="milliseconds"),
        "context_id": _context_id_var.get() or "-",
        "topic": topic,
        "data": data,
        "caller": _caller(),
    }


def _enrich_with_exception(
    data: dict[str, Any],
    exc: BaseException,
) -> dict[str, Any]:
    enriched = dict(data)
    enriched.update(_serialize_exception(exc))

    chain = _serialize_exception_chain(exc)
    if len(chain) > 1:
        enriched["exception_chain"] = chain
        root_cause = chain[-1]
        enriched["root_cause"] = {
            "error_type": root_cause["error_type"],
            "error": root_cause["error"],
        }

    return enriched


def _sanitize_for_log(value: Any) -> Any:
    if isinstance(value, str):
        if len(value) <= _MAX_LOG_STRING_LENGTH:
            return value
        budget = _MAX_LOG_STRING_LENGTH - len(_LOG_TRUNCATION_MARKER)
        prefix_length = budget // 2
        suffix_length = budget - prefix_length
        return (
            value[:prefix_length]
            + _LOG_TRUNCATION_MARKER
            + value[-suffix_length:]
        )

    if isinstance(value, bytes):
        return {
            "type": "bytes",
            "length": len(value),
        }

    if isinstance(value, dict):
        return {str(key): _sanitize_for_log(item) for key, item in value.items()}

    if isinstance(value, (list, tuple)):
        return [_sanitize_for_log(item) for item in value]

    return value


def _write(
    level: str,
    topic: str,
    data: dict[str, Any],
    *,
    exc: BaseException | None = None,
) -> None:
    if _LEVELS.get(level, 0) < _LEVELS.get(_config.level, 0):
        return

    _config.log_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now().astimezone()
    filepath = _config.log_dir / f"{now.strftime('%Y%m%d%H')}.{level}.log"
    record = _base_record(topic, data)
    record["ts"] = now.isoformat(timespec="milliseconds")

    active_exc = exc or sys.exc_info()[1]
    if active_exc is not None:
        record["data"] = _enrich_with_exception(data, active_exc)

    record["data"] = _sanitize_for_log(record["data"])

    try:
        with filepath.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError as write_err:
        sys.stderr.write(
            f"[LOGGER FALLBACK] Failed to write log ({write_err}): "
            f"{json.dumps(record, ensure_ascii=False)}\n"
        )


def debug(topic: str, data: dict[str, Any], *, exc: BaseException | None = None) -> None:
    _write("debug", topic, data, exc=exc)


def info(topic: str, data: dict[str, Any], *, exc: BaseException | None = None) -> None:
    _write("info", topic, data, exc=exc)


def warning(
    topic: str, data: dict[str, Any], *, exc: BaseException | None = None
) -> None:
    _write("warning", topic, data, exc=exc)


def error(topic: str, data: dict[str, Any], *, exc: BaseException | None = None) -> None:
    _write("error", topic, data, exc=exc)
