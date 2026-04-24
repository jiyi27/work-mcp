from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

from work_mcp.config import AllowedRoot, RemoteFsSettings
from work_mcp.tools.remote_fs.path_guard import (
    PathNotAllowedError,
    resolve_allowed_path,
)
from work_mcp.tools.remote_fs.constants import (
    DEFAULT_CONTEXT_LINES,
    MAX_FILE_SIZE_BYTES,
    MAX_TREE_ENTRIES,
)
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


def _make_settings(*roots: tuple[str, Path, str]) -> RemoteFsSettings:
    return RemoteFsSettings(
        roots=tuple(
            AllowedRoot(name=name, path=path.resolve(), description=desc)
            for name, path, desc in roots
        )
    )


def _make_service(root_dirs: tuple[Path, Path]) -> RemoteFsService:
    root_a, root_b = root_dirs
    settings = _make_settings(
        ("app", root_a, "Application source"),
        ("logs", root_b, "Log files"),
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
    def test_list_root_returns_direct_children_only(self, sample_tree: tuple[Path, Path]) -> None:
        root_a, root_b = sample_tree
        svc = _make_service((root_a, root_b))
        result = svc.list_tree(str(root_a), offset=0)
        assert result["success"] is True
        names = {Path(e["path"]).name for e in result["entries"]}
        assert "app.py" in names
        assert "config" in names
        assert "utils" in names
        assert result["truncated"] is False
        assert result["offset"] == 0
        assert result["returned_count"] == 3
        assert result["next_offset"] == 3

    def test_list_tree_does_not_expand_nested_entries(self, sample_tree: tuple[Path, Path]) -> None:
        root_a, root_b = sample_tree
        svc = _make_service((root_a, root_b))
        result = svc.list_tree(str(root_a), offset=0)
        assert result["success"] is True
        returned_paths = {Path(e["path"]).relative_to(root_a).as_posix() for e in result["entries"]}
        assert "config" in returned_paths
        assert "utils" in returned_paths
        assert "config/settings.yaml" not in returned_paths
        assert "utils/helpers.py" not in returned_paths

    def test_path_not_allowed(self, sample_tree: tuple[Path, Path]) -> None:
        root_a, root_b = sample_tree
        svc = _make_service((root_a, root_b))
        result = svc.list_tree("/etc", offset=0)
        assert result["success"] is False
        assert result["error_type"] == "path_not_allowed"

    def test_path_not_found(self, sample_tree: tuple[Path, Path]) -> None:
        root_a, root_b = sample_tree
        svc = _make_service((root_a, root_b))
        result = svc.list_tree(str(root_a / "nonexistent"), offset=0)
        assert result["success"] is False
        assert result["error_type"] == "path_not_found"

    def test_not_a_directory(self, sample_tree: tuple[Path, Path]) -> None:
        root_a, root_b = sample_tree
        svc = _make_service((root_a, root_b))
        result = svc.list_tree(str(root_a / "app.py"), offset=0)
        assert result["success"] is False
        assert result["error_type"] == "not_a_directory"

    def test_negative_offset_is_rejected(self, sample_tree: tuple[Path, Path]) -> None:
        root_a, root_b = sample_tree
        svc = _make_service((root_a, root_b))
        result = svc.list_tree(str(root_a), offset=-1)
        assert result["success"] is False
        assert result["error_type"] == "invalid_argument"

    def test_offset_pages_through_stable_directory_first_newest_listing(
        self, root_dirs: tuple[Path, Path]
    ) -> None:
        root_a, root_b = root_dirs
        for index in range(MAX_TREE_ENTRIES + 5):
            path = root_a / f"file_{index:03d}.txt"
            path.write_text(f"{index}\n")
            timestamp = 1_700_000_000 + index
            os.utime(path, (timestamp, timestamp))

        svc = _make_service((root_a, root_b))

        first_page = svc.list_tree(str(root_a), offset=0)
        second_page = svc.list_tree(str(root_a), offset=MAX_TREE_ENTRIES)

        assert first_page["success"] is True
        assert first_page["truncated"] is True
        assert first_page["offset"] == 0
        assert first_page["returned_count"] == MAX_TREE_ENTRIES
        assert first_page["next_offset"] == MAX_TREE_ENTRIES
        assert str(MAX_TREE_ENTRIES) in first_page["hint"]
        assert f"offset={MAX_TREE_ENTRIES}" in first_page["hint"]

        first_names = [Path(entry["path"]).name for entry in first_page["entries"]]
        assert first_names == [
            f"file_{index:03d}.txt"
            for index in range(MAX_TREE_ENTRIES + 4, 4, -1)
        ]
        assert "mtime" in first_page["entries"][0]

        assert second_page["success"] is True
        assert second_page["truncated"] is False
        assert second_page["offset"] == MAX_TREE_ENTRIES
        assert second_page["returned_count"] == 5
        assert second_page["next_offset"] == MAX_TREE_ENTRIES + 5
        second_names = [Path(entry["path"]).name for entry in second_page["entries"]]
        assert second_names == [f"file_{index:03d}.txt" for index in range(4, -1, -1)]

    def test_directories_are_sorted_before_files_then_by_mtime_desc_and_name(
        self, root_dirs: tuple[Path, Path]
    ) -> None:
        root_a, root_b = root_dirs
        (root_a / "b.txt").write_text("b\n")
        (root_a / "a.txt").write_text("a\n")
        (root_a / "z_dir").mkdir()
        (root_a / "m_dir").mkdir()
        os.utime(root_a / "b.txt", (1_700_000_004, 1_700_000_004))
        os.utime(root_a / "a.txt", (1_700_000_003, 1_700_000_003))
        os.utime(root_a / "z_dir", (1_700_000_001, 1_700_000_001))
        os.utime(root_a / "m_dir", (1_700_000_002, 1_700_000_002))

        svc = _make_service((root_a, root_b))

        result = svc.list_tree(str(root_a), offset=0)

        assert result["success"] is True
        assert [Path(entry["path"]).name for entry in result["entries"]] == [
            "m_dir",
            "z_dir",
            "b.txt",
            "a.txt",
        ]

    def test_skips_root_hidden_entries_and_known_noise_directories(
        self, root_dirs: tuple[Path, Path]
    ) -> None:
        root_a, root_b = root_dirs
        (root_a / ".env").write_text("SECRET=1\n")
        (root_a / ".git").mkdir()
        (root_a / ".git" / "objects").mkdir()
        (root_a / ".git" / "config").write_text("[core]\n")
        (root_a / "node_modules").mkdir()
        (root_a / "node_modules" / "left-pad").mkdir()
        (root_a / "node_modules" / "left-pad" / "index.js").write_text("module.exports = 1;\n")
        (root_a / "vendor").mkdir()
        (root_a / "vendor" / "autoload.php").write_text("<?php\n")
        (root_a / "bootstrap").mkdir()
        (root_a / "bootstrap" / "cache").mkdir()
        (root_a / "bootstrap" / "cache" / "services.php").write_text("<?php return [];\n")
        (root_a / "target").mkdir()
        (root_a / "target" / "app").write_text("binary\n")
        (root_a / "__pycache__").mkdir()
        (root_a / "__pycache__" / "mod.pyc").write_bytes(b"pyc")
        (root_a / "src").mkdir()
        (root_a / "src" / "main.py").write_text("print('ok')\n")

        svc = _make_service((root_a, root_b))

        result = svc.list_tree(str(root_a), offset=0)

        assert result["success"] is True
        returned_paths = {Path(entry["path"]).relative_to(root_a).as_posix() for entry in result["entries"]}
        assert "src" in returned_paths
        assert "src/main.py" not in returned_paths
        assert ".env" not in returned_paths
        assert ".git" not in returned_paths
        assert "node_modules" not in returned_paths
        assert "vendor" not in returned_paths
        assert "target" not in returned_paths
        assert "__pycache__" not in returned_paths


class TestSearchFiles:
    def test_content_search(self, sample_tree: tuple[Path, Path]) -> None:
        root_a, root_b = sample_tree
        svc = _make_service((root_a, root_b))
        result = _run(svc.search_files("DATABASE_URL", "", "", False, 50))
        assert result["success"] is True
        assert len(result["matches"]) >= 1
        paths = [m["path"] for m in result["matches"]]
        assert any("app.py" in p for p in paths)

    def test_content_search_is_case_insensitive(
        self, sample_tree: tuple[Path, Path]
    ) -> None:
        root_a, root_b = sample_tree
        svc = _make_service((root_a, root_b))
        result = _run(svc.search_files("database_url", "", "", False, 50))
        assert result["success"] is True
        assert len(result["matches"]) >= 1

    def test_content_search_returns_one_match_per_file(self, root_dirs: tuple[Path, Path]) -> None:
        root_a, root_b = root_dirs
        target = root_a / "repeated.txt"
        target.write_text("nginx\nnope\nnginx\nnginx\n")
        svc = _make_service((root_a, root_b))

        result = _run(svc.search_files("nginx", "app", "", False, 50))

        assert result["success"] is True
        repeated = [match for match in result["matches"] if match["path"] == str(target)]
        assert len(repeated) == 1
        assert repeated[0]["line"] == 1
        assert repeated[0]["match_count"] == 3
        assert repeated[0]["preview"] == "nginx"

    def test_glob_only_search(self, sample_tree: tuple[Path, Path]) -> None:
        root_a, root_b = sample_tree
        svc = _make_service((root_a, root_b))
        result = _run(svc.search_files("", "", "**/*.py", False, 50))
        assert result["success"] is True
        matched_names = {Path(match["path"]).name for match in result["matches"]}
        assert matched_names == {"app.py", "helpers.py"}
        assert all(match["match_count"] == 0 for match in result["matches"])

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

    def test_search_skips_hidden_root_entries_and_noise_directories(
        self, root_dirs: tuple[Path, Path]
    ) -> None:
        root_a, root_b = root_dirs
        (root_a / ".env").write_text("nginx\n")
        (root_a / "vendor").mkdir()
        (root_a / "vendor" / "sample.txt").write_text("nginx\n")
        (root_a / "visible.txt").write_text("nginx\n")
        svc = _make_service((root_a, root_b))

        result = _run(svc.search_files("nginx", "app", "", False, 50))

        assert result["success"] is True
        returned = {Path(match["path"]).relative_to(root_a).as_posix() for match in result["matches"]}
        assert "visible.txt" in returned
        assert ".env" not in returned
        assert "vendor/sample.txt" not in returned


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
        assert result["start_line"] == result["total_lines"] - 4
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
            svc.search_file(str(root_b / "server.log"), "ERROR", False, True)
        )
        assert result["success"] is True
        assert len(result["matches"]) >= 1
        lines = [m["line"] for m in result["matches"]]
        assert lines == sorted(lines, reverse=True)
        assert "from the end of the file" in result["hint"]

    def test_forward_search_follows_file_order(self, sample_tree: tuple[Path, Path]) -> None:
        root_a, root_b = sample_tree
        svc = _make_service((root_a, root_b))
        result = _run(
            svc.search_file(str(root_b / "server.log"), "ERROR", False, False)
        )
        assert result["success"] is True
        lines = [m["line"] for m in result["matches"]]
        assert lines == sorted(lines)
        assert "from the beginning of the file" in result["hint"]

    def test_no_matches(self, sample_tree: tuple[Path, Path]) -> None:
        root_a, root_b = sample_tree
        svc = _make_service((root_a, root_b))
        result = _run(
            svc.search_file(
                str(root_b / "server.log"), "NONEXISTENT", False, True,
            )
        )
        assert result["success"] is True
        assert result["matches"] == []
        assert "scanning from the end" in result["hint"]

    def test_empty_query_rejected(self, sample_tree: tuple[Path, Path]) -> None:
        root_a, root_b = sample_tree
        svc = _make_service((root_a, root_b))
        result = _run(svc.search_file(str(root_b / "server.log"), "  ", False, True))
        assert result["success"] is False
        assert result["error_type"] == "invalid_argument"

    def test_context_lines_use_default_window(self, sample_tree: tuple[Path, Path]) -> None:
        root_a, root_b = sample_tree
        svc = _make_service((root_a, root_b))
        result = _run(svc.search_file(str(root_b / "server.log"), "ERROR", False, True))
        assert result["success"] is True
        match = result["matches"][0]
        assert isinstance(match["before"], list)
        assert isinstance(match["after"], list)
        assert len(match["before"]) <= DEFAULT_CONTEXT_LINES
        assert len(match["after"]) <= DEFAULT_CONTEXT_LINES

    def test_regex_search(self, sample_tree: tuple[Path, Path]) -> None:
        root_a, root_b = sample_tree
        svc = _make_service((root_a, root_b))
        result = _run(
            svc.search_file(
                str(root_b / "server.log"), r"ERROR.*line \d+", True, True,
            )
        )
        assert result["success"] is True
        assert len(result["matches"]) >= 1

    def test_plain_search_is_case_insensitive(self, sample_tree: tuple[Path, Path]) -> None:
        root_a, root_b = sample_tree
        svc = _make_service((root_a, root_b))
        result = _run(
            svc.search_file(str(root_b / "server.log"), "error", False, True)
        )
        assert result["success"] is True
        assert len(result["matches"]) >= 1

    def test_regex_search_is_case_insensitive(
        self, sample_tree: tuple[Path, Path]
    ) -> None:
        root_a, root_b = sample_tree
        svc = _make_service((root_a, root_b))
        result = _run(
            svc.search_file(
                str(root_b / "server.log"), r"error.*line \d+", True, True,
            )
        )
        assert result["success"] is True
        assert len(result["matches"]) >= 1

    def test_invalid_regex(self, sample_tree: tuple[Path, Path]) -> None:
        root_a, root_b = sample_tree
        svc = _make_service((root_a, root_b))
        result = _run(
            svc.search_file(str(root_b / "server.log"), "[invalid", True, True)
        )
        assert result["success"] is False
        assert result["error_type"] == "invalid_regex"

    def test_large_file_is_rejected(self, sample_tree: tuple[Path, Path]) -> None:
        root_a, root_b = sample_tree
        large_file = root_b / "huge.log"
        large_file.write_bytes(b"a" * (MAX_FILE_SIZE_BYTES + 1))
        svc = _make_service((root_a, root_b))
        result = _run(
            svc.search_file(str(large_file), "ERROR", False, True)
        )
        assert result["success"] is False
        assert result["error_type"] == "file_too_large"
