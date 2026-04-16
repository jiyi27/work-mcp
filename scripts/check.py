from __future__ import annotations

from work_mcp.check import has_check_errors, print_check_report, run_checks
from work_mcp.config import PROJECT_ROOT


def main() -> None:
    try:
        results = run_checks(PROJECT_ROOT)
    except KeyboardInterrupt:
        print("\n已取消。")
        raise SystemExit(1) from None
    print_check_report(results)
    if has_check_errors(results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
