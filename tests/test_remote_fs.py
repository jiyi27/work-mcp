from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from work_mcp.config import AllowedRoot, RemoteFsSettings
from work_mcp.tools.remote_fs.path_guard import (
    PathNotAllowedError,
    resolve_allowed_path,
)
from work_mcp.tools.remote_fs.constants import MAX_FILE_SIZE_BYTES
from work_mcp.tools.remote_fs.service import RemoteFsService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def root_dirs(tmp_path: Path) -> tuple[Path, Path]:
    """Create two root directories with sample content."""
    root_a = tmp_path / "root_a"
    root_b = tmp_path / "root_b"
    root_a.mkdir()
    root_b.mkdir()
    return root_a, root_b


@pytest.fixture()
def sample_tree(root_dirs: tuple[Path, Path]) -> tuple[Path, Path]:
    """Populate root_a with a small file tree."""
    root_a, root_b = root_dirs

    # root_a structure
    (root_a / "app.py").write_text("import os\nDATABASE_URL = 'postgres://'\n")
    (root_a / "config").mkdir()
    (root_a / "config" / "settings.yaml").write_text("key: value\n")
    (root_a / "utils").mkdir()
    (root_a / "utils" / "helpers.py").write_text("def helper():\n    pass\n")

    # root_b structure — a log file
    log_lines = []
    for i in range(100):
        level = "ERROR" if i % 20 == 0 else "INFO"
        log_lines.append(f"{level} line {i}")
    (root_b / "server.log").write_text("\n".join(log_lines) + "\n")

    return root_a, root_b


def _make_settings(*roots: tuple[str, Path, str, str]) -> RemoteFsSettings:
    return RemoteFsSettings(
        roots=tuple(
            AllowedRoot(name=name, path=path.resolve(), kind=kind, description=desc)
            for name, path, kind, desc in roots
        )
    )


def _make_service(root_dirs: tuple[Path, Path]) -> RemoteFsService:
    root_a, root_b = root_dirs
    settings = _make_settings(
        ("app", root_a, "code", "Application source"),
        ("logs", root_b, "logs", "Log files"),
    )
    return RemoteFsService(settings)


def _run(coro: object) -> object:
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Path guard tests
# ---------------------------------------------------------------------------


class TestResolveAllowedPath:
    def test_path_inside_root(self, root_dirs: tuple[Path, Path]) -> None:
        root_a, _ = root_dirs
        (root_a / "file.txt").write_text("hello")
        result = resolve_allowed_path(str(root_a / "file.txt"), (root_a,))
        assert result == (root_a / "file.txt").resolve()

    def test_path_outside_all_roots(self, root_dirs: tuple[Path, Path]) -> None:
        root_a, root_b = root_dirs
        with pytest.raises(PathNotAllowedError):
            resolve_allowed_path("/etc/passwd", (root_a, root_b))

    def test_traversal_attack_rejected(self, root_dirs: tuple[Path, Path]) -> None:
        root_a, _ = root_dirs
        # Attempt to escape via ..
        with pytest.raises(PathNotAllowedError):
            resolve_allowed_path(str(root_a / ".." / ".."), (root_a,))

    def test_absolute_root_path_accepted(self, root_dirs: tuple[Path, Path]) -> None:
        root_a, _ = root_dirs
        result = resolve_allowed_path(str(root_a), (root_a,))
        assert result == root_a.resolve()

    def test_multiple_roots_matches_correct_one(self, root_dirs: tuple[Path, Path]) -> None:
        root_a, root_b = root_dirs
        (root_b / "log.txt").write_text("data")
        result = resolve_allowed_path(str(root_b / "log.txt"), (root_a, root_b))
        assert result == (root_b / "log.txt").resolve()


# ---------------------------------------------------------------------------
# Service tests
# ---------------------------------------------------------------------------


class TestGetAllowedRoots:
    def test_returns_configured_roots(self, root_dirs: tuple[Path, Path]) -> None:
        svc = _make_service(root_dirs)
        result = svc.get_allowed_roots()
        assert result["success"] is True
        assert len(result["roots"]) == 2
        assert result["roots"][0]["name"] == "app"
        assert result["roots"][1]["name"] == "logs"

    def test_empty_roots(self, tmp_path: Path) -> None:
        settings = RemoteFsSettings(roots=())
        svc = RemoteFsService(settings)
        result = svc.get_allowed_roots()
        assert result["success"] is True
        assert result["roots"] == []
        assert "no allowed roots" in result["hint"].lower()


class TestListTree:
    def test_list_root_depth_1(self, sample_tree: tuple[Path, Path]) -> None:
        root_a, root_b = sample_tree
        svc = _make_service((root_a, root_b))
        result = svc.list_tree(str(root_a), depth=1)
        assert result["success"] is True
        names = {Path(e["path"]).name for e in result["entries"]}
        assert "app.py" in names
        assert "config" in names
        assert "utils" in names
        assert result["truncated"] is False

    def test_list_deeper_depth(self, sample_tree: tuple[Path, Path]) -> None:
        root_a, root_b = sample_tree
        svc = _make_service((root_a, root_b))
        result = svc.list_tree(str(root_a), depth=2)
        assert result["success"] is True
        names = {Path(e["path"]).name for e in result["entries"]}
        # Should include nested files
        assert "settings.yaml" in names
        assert "helpers.py" in names

    def test_path_not_allowed(self, sample_tree: tuple[Path, Path]) -> None:
        root_a, root_b = sample_tree
        svc = _make_service((root_a, root_b))
        result = svc.list_tree("/etc", depth=1)
        assert result["success"] is False
        assert result["error_type"] == "path_not_allowed"

    def test_path_not_found(self, sample_tree: tuple[Path, Path]) -> None:
        root_a, root_b = sample_tree
        svc = _make_service((root_a, root_b))
        result = svc.list_tree(str(root_a / "nonexistent"), depth=1)
        assert result["success"] is False
        assert result["error_type"] == "path_not_found"

    def test_not_a_directory(self, sample_tree: tuple[Path, Path]) -> None:
        root_a, root_b = sample_tree
        svc = _make_service((root_a, root_b))
        result = svc.list_tree(str(root_a / "app.py"), depth=1)
        assert result["success"] is False
        assert result["error_type"] == "not_a_directory"


class TestSearchFiles:
    def test_content_search(self, sample_tree: tuple[Path, Path]) -> None:
        root_a, root_b = sample_tree
        svc = _make_service((root_a, root_b))
        result = _run(svc.search_files("DATABASE_URL", "", "", False, 50))
        assert result["success"] is True
        assert result["match_count"] >= 1
        paths = [m["path"] for m in result["matches"]]
        assert any("app.py" in p for p in paths)

    def test_content_search_is_case_insensitive(
        self, sample_tree: tuple[Path, Path]
    ) -> None:
        root_a, root_b = sample_tree
        svc = _make_service((root_a, root_b))
        result = _run(svc.search_files("database_url", "", "", False, 50))
        assert result["success"] is True
        assert result["match_count"] >= 1

    def test_glob_only_search(self, sample_tree: tuple[Path, Path]) -> None:
        root_a, root_b = sample_tree
        svc = _make_service((root_a, root_b))
        result = _run(svc.search_files("", "", "**/*.py", False, 50))
        assert result["success"] is True
        matched_names = {Path(match["path"]).name for match in result["matches"]}
        assert matched_names == {"app.py", "helpers.py"}

    def test_no_query_no_glob_rejected(self, sample_tree: tuple[Path, Path]) -> None:
        root_a, root_b = sample_tree
        svc = _make_service((root_a, root_b))
        result = _run(svc.search_files("", "", "", False, 50))
        assert result["success"] is False
        assert result["error_type"] == "invalid_argument"

    def test_invalid_regex(self, sample_tree: tuple[Path, Path]) -> None:
        root_a, root_b = sample_tree
        svc = _make_service((root_a, root_b))
        result = _run(svc.search_files("[invalid", "", "", True, 50))
        assert result["success"] is False
        assert result["error_type"] == "invalid_regex"

    def test_scoped_to_root(self, sample_tree: tuple[Path, Path]) -> None:
        root_a, root_b = sample_tree
        svc = _make_service((root_a, root_b))
        result = _run(svc.search_files("ERROR", "logs", "", False, 50))
        assert result["success"] is True
        for m in result["matches"]:
            assert str(root_b) in m["path"]

    def test_root_path_not_found_returns_path_not_found(
        self, sample_tree: tuple[Path, Path]
    ) -> None:
        root_a, root_b = sample_tree
        svc = _make_service((root_a, root_b))
        result = _run(
            svc.search_files("DATABASE_URL", str(root_a / "missing"), "", False, 50)
        )
        assert result["success"] is False
        assert result["error_type"] == "path_not_found"

    def test_root_file_returns_not_a_directory(self, sample_tree: tuple[Path, Path]) -> None:
        root_a, root_b = sample_tree
        svc = _make_service((root_a, root_b))
        result = _run(
            svc.search_files("DATABASE_URL", str(root_a / "app.py"), "", False, 50)
        )
        assert result["success"] is False
        assert result["error_type"] == "not_a_directory"


class TestReadFile:
    def test_read_from_start(self, sample_tree: tuple[Path, Path]) -> None:
        root_a, root_b = sample_tree
        svc = _make_service((root_a, root_b))
        result = _run(svc.read_file(str(root_a / "app.py"), 1, 200, 0))
        assert result["success"] is True
        assert result["start_line"] == 1
        assert result["total_lines"] == 2
        assert "import os" in result["content"]

    def test_tail_read(self, sample_tree: tuple[Path, Path]) -> None:
        root_a, root_b = sample_tree
        svc = _make_service((root_a, root_b))
        result = _run(svc.read_file(str(root_b / "server.log"), 1, 200, 5))
        assert result["success"] is True
        assert result["tail"] == 5
        assert result["end_line"] == result["total_lines"]

    def test_path_not_allowed(self, sample_tree: tuple[Path, Path]) -> None:
        root_a, root_b = sample_tree
        svc = _make_service((root_a, root_b))
        result = _run(svc.read_file("/etc/passwd", 1, 200, 0))
        assert result["success"] is False
        assert result["error_type"] == "path_not_allowed"

    def test_not_a_file(self, sample_tree: tuple[Path, Path]) -> None:
        root_a, root_b = sample_tree
        svc = _make_service((root_a, root_b))
        result = _run(svc.read_file(str(root_a / "config"), 1, 200, 0))
        assert result["success"] is False
        assert result["error_type"] == "not_a_file"

    def test_binary_file_rejected(self, sample_tree: tuple[Path, Path]) -> None:
        root_a, root_b = sample_tree
        binary_file = root_a / "image.bin"
        binary_file.write_bytes(b"\x00\x01\x02\x03")
        svc = _make_service((root_a, root_b))
        result = _run(svc.read_file(str(binary_file), 1, 200, 0))
        assert result["success"] is False
        assert result["error_type"] == "binary_file_not_supported"

    def test_start_line_out_of_range_is_rejected(
        self, sample_tree: tuple[Path, Path]
    ) -> None:
        root_a, root_b = sample_tree
        svc = _make_service((root_a, root_b))
        result = _run(svc.read_file(str(root_a / "app.py"), 99, 20, 0))
        assert result["success"] is False
        assert result["error_type"] == "line_out_of_range"

    def test_large_file_is_rejected(self, sample_tree: tuple[Path, Path]) -> None:
        root_a, root_b = sample_tree
        large_file = root_a / "large.log"
        large_file.write_bytes(b"a" * (MAX_FILE_SIZE_BYTES + 1))
        svc = _make_service((root_a, root_b))
        result = _run(svc.read_file(str(large_file), 1, 20, 0))
        assert result["success"] is False
        assert result["error_type"] == "file_too_large"


class TestSearchFileReverse:
    def test_finds_newest_matches(self, sample_tree: tuple[Path, Path]) -> None:
        root_a, root_b = sample_tree
        svc = _make_service((root_a, root_b))
        result = _run(
            svc.search_file_reverse(str(root_b / "server.log"), "ERROR", 5, 1, 1, False)
        )
        assert result["success"] is True
        assert result["order"] == "newest_first"
        assert result["match_count"] >= 1
        lines = [m["line"] for m in result["matches"]]
        assert lines == sorted(lines, reverse=True)

    def test_no_matches(self, sample_tree: tuple[Path, Path]) -> None:
        root_a, root_b = sample_tree
        svc = _make_service((root_a, root_b))
        result = _run(
            svc.search_file_reverse(
                str(root_b / "server.log"), "NONEXISTENT", 5, 1, 1, False,
            )
        )
        assert result["success"] is True
        assert result["match_count"] == 0

    def test_empty_query_rejected(self, sample_tree: tuple[Path, Path]) -> None:
        root_a, root_b = sample_tree
        svc = _make_service((root_a, root_b))
        result = _run(svc.search_file_reverse(str(root_b / "server.log"), "  ", 5, 1, 1, False))
        assert result["success"] is False
        assert result["error_type"] == "invalid_argument"

    def test_context_lines(self, sample_tree: tuple[Path, Path]) -> None:
        root_a, root_b = sample_tree
        svc = _make_service((root_a, root_b))
        result = _run(svc.search_file_reverse(str(root_b / "server.log"), "ERROR", 1, 2, 2, False))
        assert result["success"] is True
        match = result["matches"][0]
        assert isinstance(match["before"], list)
        assert isinstance(match["after"], list)
        assert len(match["before"]) <= 2
        assert len(match["after"]) <= 2

    def test_regex_search(self, sample_tree: tuple[Path, Path]) -> None:
        root_a, root_b = sample_tree
        svc = _make_service((root_a, root_b))
        result = _run(
            svc.search_file_reverse(
                str(root_b / "server.log"), r"ERROR.*line \d+", 5, 0, 0, True,
            )
        )
        assert result["success"] is True
        assert result["match_count"] >= 1

    def test_plain_search_is_case_insensitive(self, sample_tree: tuple[Path, Path]) -> None:
        root_a, root_b = sample_tree
        svc = _make_service((root_a, root_b))
        result = _run(
            svc.search_file_reverse(str(root_b / "server.log"), "error", 5, 0, 0, False)
        )
        assert result["success"] is True
        assert result["match_count"] >= 1

    def test_regex_search_is_case_insensitive(
        self, sample_tree: tuple[Path, Path]
    ) -> None:
        root_a, root_b = sample_tree
        svc = _make_service((root_a, root_b))
        result = _run(
            svc.search_file_reverse(
                str(root_b / "server.log"), r"error.*line \d+", 5, 0, 0, True,
            )
        )
        assert result["success"] is True
        assert result["match_count"] >= 1

    def test_invalid_regex(self, sample_tree: tuple[Path, Path]) -> None:
        root_a, root_b = sample_tree
        svc = _make_service((root_a, root_b))
        result = _run(
            svc.search_file_reverse(str(root_b / "server.log"), "[invalid", 5, 0, 0, True)
        )
        assert result["success"] is False
        assert result["error_type"] == "invalid_regex"

    def test_large_file_is_rejected(self, sample_tree: tuple[Path, Path]) -> None:
        root_a, root_b = sample_tree
        large_file = root_b / "huge.log"
        large_file.write_bytes(b"a" * (MAX_FILE_SIZE_BYTES + 1))
        svc = _make_service((root_a, root_b))
        result = _run(
            svc.search_file_reverse(str(large_file), "ERROR", 5, 0, 0, False)
        )
        assert result["success"] is False
        assert result["error_type"] == "file_too_large"
