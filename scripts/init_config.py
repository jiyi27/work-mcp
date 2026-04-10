from __future__ import annotations

from pathlib import Path
import shutil
import subprocess

from work_mcp.config import DB_TYPE_MYSQL, DB_TYPE_SQLSERVER, PROJECT_ROOT
from work_mcp.setup import (
    DATABASE_CHOICE_BY_NUMBER,
    SetupAnswers,
    build_updated_env,
    build_updated_yaml,
    current_value_label,
    default_driver_for_db,
    default_port_for_db,
    connectivity_hint,
    diagnose,
    env_file_path,
    has_errors,
    load_existing_yaml,
    parse_env_file,
    validate_log_base_dir,
    validate_port,
    validate_positive_int,
    validate_required_text,
    validate_sqlserver_driver,
    write_env_file,
    write_yaml_file,
)

PLUGIN_DATABASE = "database"
PLUGIN_LOG_SEARCH = "log_search"
PLUGIN_DINGTALK = "dingtalk"
PLUGIN_JIRA = "jira"
ENV_TYPE_REMOTE = "remote"
ENV_TYPE_LOCAL = "local"
YES_NO_CHOICES = {
    "1": False,
    "2": True,
}
DEFAULT_DISABLE_CHOICE = "1"
DEFAULT_DATABASE_CHOICE = "1"
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


def prompt_yes_no(label: str, *, current_enabled: bool | None = None) -> bool:
    if current_enabled is not None:
        print(f"当前{label}: {'已开启' if current_enabled else '未开启'}")
    print(f"是否开启{label}？")
    print("1. 不开启（默认）  2. 开启")
    selected = prompt_choice("请输入选项", YES_NO_CHOICES, DEFAULT_DISABLE_CHOICE)
    return bool(selected)


def prompt_environment_type() -> str:
    print()
    print("当前是什么运行环境？")
    print("1. 远程服务器")
    print("2. 本地")
    selected = prompt_choice("请输入选项", ENVIRONMENT_TYPE_BY_NUMBER, "2")
    return str(selected)


def prompt_should_modify_existing(env_path: Path, yaml_path: Path) -> bool:
    if not env_path.exists() and not yaml_path.exists():
        return True

    print("检测到已有配置文件。")
    selected = prompt_choice(
        "是否要修改现有配置？1. 不修改（默认）  2. 修改\n请输入选项",
        {"1": False, "2": True},
        "1",
    )
    return bool(selected)


def resolve_plugin_enabled(label: str, *, current_enabled: bool) -> bool:
    print()
    if current_enabled:
        print(f"{label} 已开启，继续进入配置。")
        return True
    return prompt_yes_no(label, current_enabled=False)


def prompt_database_type(existing_env: dict[str, str]) -> str:
    existing_db_type = existing_env.get("DB_TYPE", "").strip().lower()
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


def enabled_plugins_from_yaml(yaml_values: dict) -> set[str]:
    plugins = yaml_values.get("plugins", {})
    if not isinstance(plugins, dict):
        return set()
    raw_enabled = plugins.get("enabled", [])
    if not isinstance(raw_enabled, list):
        return set()
    return {str(item).strip() for item in raw_enabled if str(item).strip()}


def collect_database_answers(existing_env: dict[str, str]) -> dict[str, object]:
    print("\n[数据库配置]")
    db_type = prompt_database_type(existing_env)
    port_default = str(default_port_for_db(db_type))

    return {
        "db_type": db_type,
        "host": str(
            prompt_text(
                "数据库地址是什么",
                existing_value=existing_env.get("DB_HOST", ""),
                validator=lambda value: validate_required_text(value, "DB_HOST"),
            )
        ),
        "port": int(
            prompt_text(
                "数据库端口是多少",
                existing_value=existing_env.get("DB_PORT", ""),
                default_value=port_default,
                validator=lambda value: validate_port(value, "DB_PORT"),
            )
        ),
        "user": str(
            prompt_text(
                "数据库用户名是什么",
                existing_value=existing_env.get("DB_USER", ""),
                validator=lambda value: validate_required_text(value, "DB_USER"),
            )
        ),
        "password": str(
            prompt_text(
                "数据库密码是什么",
                existing_value=existing_env.get("DB_PASSWORD", ""),
                validator=lambda value: validate_required_text(value, "DB_PASSWORD"),
                secret_field="DB_PASSWORD",
            )
        ),
        "database_name": str(
            prompt_text(
                "默认连接的数据库名是什么",
                existing_value=existing_env.get("DB_NAME", ""),
                default_value="master",
                validator=lambda value: validate_required_text(value, "DB_NAME"),
            )
        ),
        "connect_timeout_seconds": int(
            prompt_text(
                "数据库连接超时时间（秒）是多少",
                existing_value=existing_env.get("DB_CONNECT_TIMEOUT_SECONDS", ""),
                default_value="5",
                validator=lambda value: validate_positive_int(
                    value, "DB_CONNECT_TIMEOUT_SECONDS"
                ),
            )
        ),
    }


def collect_sqlserver_answers(existing_env: dict[str, str], db_type: str) -> dict[str, object]:
    if db_type != DB_TYPE_SQLSERVER:
        return {
            "driver": "",
            "trust_server_certificate": True,
        }

    return {
        "driver": str(
            prompt_text(
                "SQL Server ODBC Driver 名称是什么",
                existing_value=existing_env.get("DB_DRIVER", ""),
                default_value=default_driver_for_db(db_type),
                validator=validate_sqlserver_driver,
            )
        ),
        "trust_server_certificate": True,
    }


def collect_jira_answers(existing_env: dict[str, str]) -> dict[str, str]:
    print("\n[Jira 配置]")
    return {
        "jira_base_url": str(
            prompt_text(
                "Jira 地址是什么",
                existing_value=existing_env.get("JIRA_BASE_URL", ""),
                validator=lambda value: validate_required_text(value, "JIRA_BASE_URL"),
            )
        ),
        "jira_api_token": str(
            prompt_text(
                "Jira API Token 是什么",
                existing_value=existing_env.get("JIRA_API_TOKEN", ""),
                validator=lambda value: validate_required_text(value, "JIRA_API_TOKEN"),
                secret_field="JIRA_API_TOKEN",
            )
        ),
        "jira_project_key": str(
            prompt_text(
                "Jira 项目 Key 是什么",
                existing_value=existing_env.get("JIRA_PROJECT_KEY", ""),
                validator=lambda value: validate_required_text(value, "JIRA_PROJECT_KEY"),
            )
        ),
    }


def collect_log_search_answers(yaml_values: dict) -> dict[str, str]:
    print("\n[日志搜索配置]")
    return {
        "log_base_dir": str(
            prompt_text(
                "日志根目录的绝对路径是什么",
                existing_value=_existing_log_base_dir(yaml_values),
                validator=validate_log_base_dir,
            )
        ),
    }


def collect_dingtalk_answers(existing_env: dict[str, str]) -> dict[str, str]:
    print("\n[钉钉配置]")
    return {
        "dingtalk_webhook_url": str(
            prompt_text(
                "钉钉 webhook 地址是什么",
                existing_value=existing_env.get("DINGTALK_WEBHOOK_URL", ""),
                validator=lambda value: validate_required_text(
                    value, "DINGTALK_WEBHOOK_URL"
                ),
            )
        ),
        "dingtalk_secret": str(
            prompt_text(
                "钉钉加签 secret 是什么（可留空）",
                existing_value=existing_env.get("DINGTALK_SECRET", ""),
                allow_empty=True,
                validator=lambda value: value,
                secret_field="DINGTALK_SECRET",
            )
        ),
    }


def _default_database_answers() -> dict[str, object]:
    return {
        "db_type": DB_TYPE_MYSQL,
        "host": "",
        "port": default_port_for_db(DB_TYPE_MYSQL),
        "user": "",
        "password": "",
        "database_name": "",
        "driver": "",
        "trust_server_certificate": True,
        "connect_timeout_seconds": 5,
    }


def collect_answers(
    env_type: str,
    project_root: Path = PROJECT_ROOT,
) -> SetupAnswers:
    env_values = parse_env_file(env_file_path(project_root))
    yaml_values = load_existing_yaml(project_root / "config.yaml")

    print("开始初始化配置。")

    if env_type == ENV_TYPE_REMOTE:
        print("远程服务器模式：将启用 database 和 log_search，并移除 jira、dingtalk。")
        enable_database = True
        enable_log_search = True
        enable_dingtalk = False
        enable_jira = False
    else:
        print("本地模式：将只启用 jira，并移除 database、log_search、dingtalk。")
        enable_database = False
        enable_log_search = False
        enable_dingtalk = False
        enable_jira = True

    database_answers: dict[str, object] = _default_database_answers()
    if enable_database:
        database_answers.update(collect_database_answers(env_values))
        database_answers.update(
            collect_sqlserver_answers(env_values, str(database_answers["db_type"]))
        )

    log_search_answers: dict[str, str] = {"log_base_dir": ""}
    if enable_log_search:
        log_search_answers.update(collect_log_search_answers(yaml_values))

    dingtalk_answers = {
        "dingtalk_webhook_url": "",
        "dingtalk_secret": "",
    }
    if enable_dingtalk:
        dingtalk_answers.update(collect_dingtalk_answers(env_values))

    jira_answers: dict[str, str] = {
        "jira_base_url": "",
        "jira_api_token": "",
        "jira_project_key": "",
    }
    if enable_jira:
        jira_answers.update(collect_jira_answers(env_values))

    return SetupAnswers(
        enable_database=enable_database,
        db_type=str(database_answers["db_type"]),
        host=str(database_answers["host"]),
        port=int(database_answers["port"]),
        user=str(database_answers["user"]),
        password=str(database_answers["password"]),
        database_name=str(database_answers["database_name"]),
        driver=str(database_answers["driver"]),
        trust_server_certificate=bool(database_answers["trust_server_certificate"]),
        connect_timeout_seconds=int(database_answers["connect_timeout_seconds"]),
        enable_log_search=enable_log_search,
        log_base_dir=log_search_answers["log_base_dir"],
        enable_dingtalk=enable_dingtalk,
        dingtalk_webhook_url=dingtalk_answers["dingtalk_webhook_url"],
        dingtalk_secret=dingtalk_answers["dingtalk_secret"],
        enable_jira=enable_jira,
        jira_base_url=str(jira_answers["jira_base_url"]),
        jira_api_token=str(jira_answers["jira_api_token"]),
        jira_project_key=str(jira_answers["jira_project_key"]),
    )


def _existing_log_base_dir(yaml_values: dict) -> str:
    log_search = yaml_values.get("log_search")
    if not isinstance(log_search, dict):
        return ""
    return str(log_search.get("log_base_dir", "")).strip()


def main() -> None:
    project_root = PROJECT_ROOT
    env_path = env_file_path(project_root)
    yaml_path = project_root / "config.yaml"

    try:
        ensure_uv_available()
        sync_dependencies(project_root)
        env_type = prompt_environment_type()

        should_modify_existing = True
        if env_type != ENV_TYPE_REMOTE:
            should_modify_existing = prompt_should_modify_existing(env_path, yaml_path)

        if should_modify_existing:
            answers = collect_answers(env_type, project_root)
            existing_env = parse_env_file(env_path)
            existing_yaml = load_existing_yaml(yaml_path)
            write_env_file(env_path, build_updated_env(existing_env, answers))
            write_yaml_file(yaml_path, build_updated_yaml(existing_yaml, answers))
            print("配置保存成功。")
        else:
            print("已跳过配置修改，直接进行检查。")

        print("\n开始执行配置检查...")
        results = diagnose(project_root)
        for result in results:
            print(f"[{result.level}] {result.message}")

        if has_errors(results):
            hint = connectivity_hint(project_root)
            msg = "配置校验未通过。请重新运行 `make init` 修正配置。"
            if hint:
                msg += f"\n{hint}"
            raise SystemExit(msg)

        print("运行 `uv run work-mcp` 启动服务。")
    except RuntimeError as exc:
        raise SystemExit(f"错误: {exc}") from None
    except KeyboardInterrupt:
        print("\n已取消初始化。")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
