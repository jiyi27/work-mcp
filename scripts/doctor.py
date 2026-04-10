from __future__ import annotations

from work_mcp.config import PROJECT_ROOT
from work_mcp.setup import connectivity_hint, diagnose, has_errors


def main() -> None:
    try:
        results = diagnose(PROJECT_ROOT)
    except KeyboardInterrupt:
        print("\n已取消。")
        raise SystemExit(1) from None
    for result in results:
        print(f"[{result.level}] {result.message}")
    if has_errors(results):
        hint = connectivity_hint(PROJECT_ROOT)
        if hint:
            print(hint)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
