from __future__ import annotations

import json
from pathlib import Path

from work_assistant_mcp import logger


def _read_single_record(log_dir: Path, level: str) -> dict[str, object]:
    files = list(log_dir.glob(f"*.{level}.log"))
    assert len(files) == 1
    lines = files[0].read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    return json.loads(lines[0])


def test_info_writes_json_log_record(tmp_path: Path) -> None:
    logger.configure(log_dir=tmp_path, level="info")
    logger.set_context_id("ctx-123")

    logger.info("tool.completed", {"tool": "demo"})

    record = _read_single_record(tmp_path, "info")
    assert record["context_id"] == "ctx-123"
    assert record["topic"] == "tool.completed"
    assert record["data"] == {"tool": "demo"}
    assert record["caller"]["func"] == "test_info_writes_json_log_record"

    logger.clear_context_id()


def test_error_includes_exception_details(tmp_path: Path) -> None:
    logger.configure(log_dir=tmp_path, level="debug")

    try:
        try:
            raise ValueError("root cause")
        except ValueError as exc:
            raise RuntimeError("wrapped") from exc
    except RuntimeError as exc:
        logger.error("tool.failed", {"tool": "demo"}, exc=exc)

    record = _read_single_record(tmp_path, "error")
    data = record["data"]
    assert data["tool"] == "demo"
    assert data["error_type"] == "RuntimeError"
    assert data["root_cause"] == {
        "error_type": "ValueError",
        "error": "root cause",
    }


def test_configure_rejects_unknown_level(tmp_path: Path) -> None:
    try:
        logger.configure(log_dir=tmp_path, level="trace")
    except ValueError as exc:
        assert "Unknown log level" in str(exc)
    else:
        raise AssertionError("Expected ValueError for invalid log level")


def test_info_truncates_long_string_fields(tmp_path: Path) -> None:
    logger.configure(log_dir=tmp_path, level="info")

    logger.info("tool.completed", {"result": {"base64": "a" * 600}})

    record = _read_single_record(tmp_path, "info")
    assert record["data"]["result"]["base64"] == "a" * 600


def test_info_preserves_prefix_and_suffix_when_truncating_long_string_fields(tmp_path: Path) -> None:
    logger.configure(log_dir=tmp_path, level="info")
    long_value = ("prefix-" * 120) + ("middle-" * 120) + ("-suffix" * 120)

    logger.info("tool.completed", {"result": {"base64": long_value}})

    record = _read_single_record(tmp_path, "info")
    base64_field = record["data"]["result"]["base64"]
    assert isinstance(base64_field, str)
    assert len(base64_field) == 1000
    assert "...<truncated>..." in base64_field
    assert base64_field.startswith(long_value[:100])
    assert base64_field.endswith(long_value[-100:])
