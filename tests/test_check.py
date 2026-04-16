from __future__ import annotations

from pathlib import Path

from work_mcp.check import has_check_errors, print_check_report, run_checks


def test_run_checks_reports_missing_plugin_config(tmp_path: Path) -> None:
    (tmp_path / "config.yaml").write_text(
        """
plugins:
  enabled:
    - jira
jira:
  base_url: https://jira.example.invalid
  latest_assigned_statuses:
    - 待处理
  start_target_status: 已接收
  resolve_target_status: 已解决
""".strip(),
        encoding="utf-8",
    )

    results = run_checks(tmp_path)

    assert has_check_errors(results) is True
    assert len(results) == 1
    assert results[0].module == "jira"
    assert [line.message for line in results[0].lines] == [
        "missing jira.api_token in config.yaml",
        "missing jira.project_key in config.yaml",
    ]


def test_run_checks_reports_connectivity_failure_with_summary(
    monkeypatch,
    tmp_path: Path,
) -> None:
    (tmp_path / "config.yaml").write_text(
        """
plugins:
  enabled:
    - jira
jira:
  base_url: https://jira.example.invalid
  api_token: secret-token
  project_key: IOS
  latest_assigned_statuses:
    - 待处理
  start_target_status: 已接收
  resolve_target_status: 已解决
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "work_mcp.check.check_jira_connectivity",
        lambda settings, timeout_seconds: (_ for _ in ()).throw(
            RuntimeError("connectivity check failed: request timed out")
        ),
    )

    results = run_checks(tmp_path)

    assert has_check_errors(results) is True
    assert len(results) == 1
    assert results[0].module == "jira"
    assert [line.message for line in results[0].lines] == [
        "current config:",
        "- base_url=https://jira.example.invalid",
        "- project_key=IOS",
        "connectivity check failed: request timed out",
        "please check the current module config or network access",
    ]


def test_run_checks_reports_success_for_enabled_plugins(monkeypatch, tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (tmp_path / "config.yaml").write_text(
        f"""
plugins:
  enabled:
    - database
    - log_search
log_search:
  log_base_dir: {log_dir}
database:
  type: mysql
  host: db.example.internal
  port: 3306
  user: readonly_user
  password: secret
  connect_timeout_seconds: 5
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "work_mcp.check.check_database_connectivity",
        lambda settings, timeout_seconds: {"database_name": "app_db"},
    )

    results = run_checks(tmp_path)

    assert has_check_errors(results) is False
    assert [(result.module, [line.message for line in result.lines]) for result in results] == [
        ("database", ["config is valid", "connectivity passed"]),
        ("log_search", ["config is valid", f"log_base_dir={log_dir}"]),
    ]


def test_print_check_report_prints_final_success_message(capsys) -> None:
    print_check_report([])

    captured = capsys.readouterr()

    assert captured.out == "all checks passed\n"
