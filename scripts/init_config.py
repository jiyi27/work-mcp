from __future__ import annotations

from pathlib import Path
import shutil
import subprocess

from work_mcp.check import has_check_errors, print_check_report, run_checks
from work_mcp.config import DB_TYPE_MYSQL, DB_TYPE_SQLSERVER, PROJECT_ROOT
from work_mcp.setup import (
    SetupAnswers,
    build_updated_yaml,
    current_value_label,
    default_driver_for_db,
    default_port_for_db,
    is_database_config_complete,
    is_jira_config_complete,
    is_log_search_config_complete,
    load_existing_yaml,
    normalize_text_value,
    validate_log_base_dir,
    validate_port,
    validate_positive_int,
    validate_required_text,
    validate_sqlserver_driver,
    write_yaml_file,
)

ENV_TYPE_REMOTE = "remote"
ENV_TYPE_LOCAL = "local"
DEFAULT_DATABASE_CHOICE = "1"
DATABASE_CHOICE_BY_NUMBER = {
    "1": DB_TYPE_MYSQL,
    "2": DB_TYPE_SQLSERVER,
}
ENVIRONMENT_TYPE_BY_NUMBER = {
    "1": ENV_TYPE_REMOTE,
    "2": ENV_TYPE_LOCAL,
}
UV_COMMAND = "uv"


def prompt_choice(prompt: str, choices: dict[str, object], default_choice: str) -> object:
    str_choices = {str(k): v for k, v in choices.items()}
    while True:
        raw_value = input(f"{prompt} [回车默认：{default_choice}]: ").strip()
        selected = raw_value or str(default_choice)
        if selected in str_choices:
            return str_choices[selected]
        print("输入无效，请输入给定选项编号。")


def prompt_keep_existing(label: str, current_value: str, *, secret_field: str = "") -> bool:
    shown_value = current_value_label(secret_field, current_value) if secret_field else current_value
    print()
    print(f"当前{label}: {shown_value}")
    choice = prompt_choice(
        "是否保留当前值？1. 保留（默认）  2. 重新输入\n请输入选项",
        {"1": True, "2": False},
        "1",
    )
    return bool(choice)


def prompt_text(
    label: str,
    *,
    existing_value: str = "",
    default_value: str = "",
    validator,
    allow_empty: bool = False,
    secret_field: str = "",
) -> object:
    if existing_value and prompt_keep_existing(label, existing_value, secret_field=secret_field):
        return validator(existing_value) if not allow_empty else existing_value

    print()
    while True:
        suffix = f" [回车默认：{default_value}]" if default_value else ""
        raw_value = input(f"{label}{suffix}: ")
        candidate = raw_value.strip()
        if not candidate and default_value:
            candidate = default_value
        if not candidate and allow_empty:
            return ""
        try:
            return validator(candidate)
        except RuntimeError as exc:
            print(f"输入不合法: {exc}")

def prompt_environment_type() -> str:
    print()
    print("当前是什么运行环境？")
    print("1. 远程服务器")
    print("2. 本地")
    selected = prompt_choice("请输入选项", ENVIRONMENT_TYPE_BY_NUMBER, "2")
    return str(selected)


def prompt_database_type(existing_yaml_db: dict) -> str:
    existing_db_type = normalize_text_value(existing_yaml_db.get("type")).lower()
    if existing_db_type in {DB_TYPE_MYSQL, DB_TYPE_SQLSERVER}:
        choice_number = "1" if existing_db_type == DB_TYPE_MYSQL else "2"
        if prompt_keep_existing("数据库类型", existing_db_type):
            return existing_db_type
    else:
        choice_number = DEFAULT_DATABASE_CHOICE

    print()
    print("请选择数据库类型：")
    print("1. mysql（默认）  2. sqlserver")
    selected = prompt_choice("请输入选项", DATABASE_CHOICE_BY_NUMBER, choice_number)
    return str(selected)


def ensure_uv_available() -> None:
    if shutil.which(UV_COMMAND):
        return
    raise RuntimeError("未检测到 uv，请先安装 uv 后再运行初始化。")


def sync_dependencies(project_root: Path) -> None:
    try:
        subprocess.run(
            [UV_COMMAND, "sync"],
            check=True,
            cwd=project_root,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("未检测到 uv，请先安装 uv 后再运行初始化。") from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            "执行 `uv sync` 失败，请先完成依赖安装后再重试。"
        ) from exc


def _yaml_db_to_answers(yaml_db: dict) -> dict[str, object]:
    """Convert yaml database section keys to the answers dict format."""
    db_type = normalize_text_value(yaml_db.get("type")).lower()
    return {
        "db_type": db_type,
        "host": normalize_text_value(yaml_db.get("host")),
        "port": int(yaml_db.get("port") or default_port_for_db(db_type)),
        "user": normalize_text_value(yaml_db.get("user")),
        "password": normalize_text_value(yaml_db.get("password")),
        "driver": normalize_text_value(yaml_db.get("driver", default_driver_for_db(db_type))),
        "trust_server_certificate": bool(yaml_db.get("trust_server_certificate", True)),
        "connect_timeout_seconds": int(yaml_db.get("connect_timeout_seconds", 5)),
    }


def collect_database_config(yaml_db: dict) -> dict[str, object]:
    """Skip prompts for complete config; otherwise prompt field by field."""
    if is_database_config_complete(yaml_db):
        return _yaml_db_to_answers(yaml_db)
    answers = collect_database_answers(yaml_db)
    answers.update(collect_sqlserver_answers(yaml_db, str(answers["db_type"])))
    return answers


def _collect_field_values(
    title: str,
    existing_section: dict,
    fields: tuple[tuple[str, str, object, str, bool, str], ...],
) -> dict[str, str]:
    print(f"\n[{title}]")
    collected: dict[str, str] = {}
    for output_key, prompt_label, validator, yaml_key, allow_empty, secret_field in fields:
        collected[output_key] = str(
            prompt_text(
                prompt_label,
                existing_value=normalize_text_value(existing_section.get(yaml_key)),
                validator=validator,
                allow_empty=allow_empty,
                secret_field=secret_field,
            )
        )
    return collected


def collect_jira_config(yaml_jira: dict) -> dict[str, str]:
    """Skip prompts for complete config; otherwise prompt field by field."""
    if is_jira_config_complete(yaml_jira):
        return {
            "jira_base_url": normalize_text_value(yaml_jira.get("base_url")),
            "jira_api_token": normalize_text_value(yaml_jira.get("api_token")),
            "jira_project_key": normalize_text_value(yaml_jira.get("project_key")),
        }
    return _collect_field_values(
        "Jira 配置",
        yaml_jira,
        (
            ("jira_base_url", "Jira 地址是什么", lambda value: validate_required_text(value, "base_url"), "base_url", False, ""),
            ("jira_api_token", "Jira API Token 是什么", lambda value: validate_required_text(value, "api_token"), "api_token", False, "api_token"),
            ("jira_project_key", "Jira 项目 Key 是什么", lambda value: validate_required_text(value, "project_key"), "project_key", False, ""),
        ),
    )


def collect_log_search_config(yaml_values: dict) -> dict[str, str]:
    """Skip prompts for complete config; otherwise prompt field by field."""
    log_search = yaml_values.get("log_search") or {}
    if not isinstance(log_search, dict):
        log_search = {}
    if is_log_search_config_complete(log_search):
        return {"log_base_dir": normalize_text_value(log_search.get("log_base_dir"))}
    return _collect_field_values(
        "日志搜索配置",
        log_search,
        (
            ("log_base_dir", "日志根目录的绝对路径是什么", validate_log_base_dir, "log_base_dir", False, ""),
        ),
    )


def collect_database_answers(existing_yaml_db: dict) -> dict[str, object]:
    print("\n[数据库配置]")
    db_type = prompt_database_type(existing_yaml_db)
    port_default = str(default_port_for_db(db_type))

    return {
        "db_type": db_type,
        "host": str(
            prompt_text(
                "数据库地址是什么",
                existing_value=normalize_text_value(existing_yaml_db.get("host")),
                validator=lambda value: validate_required_text(value, "host"),
            )
        ),
        "port": int(
            prompt_text(
                "数据库端口是多少",
                existing_value=normalize_text_value(existing_yaml_db.get("port")),
                default_value=port_default,
                validator=lambda value: validate_port(value, "port"),
            )
        ),
        "user": str(
            prompt_text(
                "数据库用户名是什么",
                existing_value=normalize_text_value(existing_yaml_db.get("user")),
                validator=lambda value: validate_required_text(value, "user"),
            )
        ),
        "password": str(
            prompt_text(
                "数据库密码是什么",
                existing_value=normalize_text_value(existing_yaml_db.get("password")),
                validator=lambda value: validate_required_text(value, "password"),
                secret_field="password",
            )
        ),
        "connect_timeout_seconds": int(
            prompt_text(
                "数据库连接超时时间（秒）是多少",
                existing_value=normalize_text_value(existing_yaml_db.get("connect_timeout_seconds")),
                default_value="5",
                validator=lambda value: validate_positive_int(value, "connect_timeout_seconds"),
            )
        ),
    }


def collect_sqlserver_answers(existing_yaml_db: dict, db_type: str) -> dict[str, object]:
    if db_type != DB_TYPE_SQLSERVER:
        return {
            "driver": "",
            "trust_server_certificate": True,
        }

    return {
        "driver": str(
            prompt_text(
                "SQL Server ODBC Driver 名称是什么",
                existing_value=normalize_text_value(existing_yaml_db.get("driver")),
                default_value=default_driver_for_db(db_type),
                validator=validate_sqlserver_driver,
            )
        ),
        "trust_server_certificate": True,
    }

def _default_database_answers() -> dict[str, object]:
    return {
        "db_type": DB_TYPE_MYSQL,
        "host": "",
        "port": default_port_for_db(DB_TYPE_MYSQL),
        "user": "",
        "password": "",
        "driver": "",
        "trust_server_certificate": True,
        "connect_timeout_seconds": 5,
    }


def collect_answers(
    env_type: str,
    project_root: Path = PROJECT_ROOT,
) -> SetupAnswers:
    yaml_values = load_existing_yaml(project_root / "config.yaml")

    existing_yaml_db = yaml_values.get("database") or {}
    if not isinstance(existing_yaml_db, dict):
        existing_yaml_db = {}

    existing_yaml_jira = yaml_values.get("jira") or {}
    if not isinstance(existing_yaml_jira, dict):
        existing_yaml_jira = {}

    print("开始初始化配置。")

    if env_type == ENV_TYPE_REMOTE:
        print("远程服务器模式：将启用 database 和 log_search。")
        enable_database = True
        enable_log_search = True
        enable_jira = False
    else:
        print("本地模式：将启用 jira。")
        enable_database = False
        enable_log_search = False
        enable_jira = True

    database_answers: dict[str, object] = _default_database_answers()
    if enable_database:
        database_answers.update(collect_database_config(existing_yaml_db))

    log_search_answers: dict[str, str] = {"log_base_dir": ""}
    if enable_log_search:
        log_search_answers.update(collect_log_search_config(yaml_values))

    jira_answers: dict[str, str] = {
        "jira_base_url": "",
        "jira_api_token": "",
        "jira_project_key": "",
    }
    if enable_jira:
        jira_answers.update(collect_jira_config(existing_yaml_jira))

    return SetupAnswers(
        enable_database=enable_database,
        db_type=str(database_answers["db_type"]),
        host=str(database_answers["host"]),
        port=int(database_answers["port"]),
        user=str(database_answers["user"]),
        password=str(database_answers["password"]),
        driver=str(database_answers["driver"]),
        trust_server_certificate=bool(database_answers["trust_server_certificate"]),
        connect_timeout_seconds=int(database_answers["connect_timeout_seconds"]),
        enable_log_search=enable_log_search,
        log_base_dir=log_search_answers["log_base_dir"],
        enable_dingtalk=False,
        dingtalk_webhook_url="",
        dingtalk_secret="",
        enable_jira=enable_jira,
        jira_base_url=str(jira_answers["jira_base_url"]),
        jira_api_token=str(jira_answers["jira_api_token"]),
        jira_project_key=str(jira_answers["jira_project_key"]),
    )
def main() -> None:
    project_root = PROJECT_ROOT
    yaml_path = project_root / "config.yaml"

    try:
        ensure_uv_available()
        sync_dependencies(project_root)
        env_type = prompt_environment_type()

        answers = collect_answers(env_type, project_root)
        existing_yaml = load_existing_yaml(yaml_path)
        write_yaml_file(yaml_path, build_updated_yaml(existing_yaml, answers))
        print("配置保存成功。")

        print("\n开始执行配置检查...")
        results = run_checks(project_root)
        print_check_report(results)

        if has_check_errors(results):
            raise SystemExit("配置校验未通过。请重新运行 `make init` 修正配置。")

        print("运行 `uv run work-mcp` 启动服务。")
    except RuntimeError as exc:
        raise SystemExit(f"错误: {exc}") from None
    except KeyboardInterrupt:
        print("\n已取消初始化。")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
