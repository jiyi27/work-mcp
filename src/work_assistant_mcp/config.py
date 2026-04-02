from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


ENV_FILE_NAME = ".env"
PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    dingtalk_webhook_url: str


def load_env_file(env_path: Path | None = None) -> None:
    """Load key/value pairs from a local .env file without extra dependencies."""
    path = env_path or PROJECT_ROOT / ENV_FILE_NAME
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()

        if not key or key in os.environ:
            continue

        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]

        os.environ[key] = value


def get_settings() -> Settings:
    load_env_file()

    webhook_url = os.getenv("DINGTALK_WEBHOOK_URL", "").strip()
    if not webhook_url:
        raise RuntimeError(
            "Missing DINGTALK_WEBHOOK_URL. Configure it in the environment or .env."
        )

    return Settings(dingtalk_webhook_url=webhook_url)
