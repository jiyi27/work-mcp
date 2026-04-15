.PHONY: run run-http run-stdio test init doctor

UV ?= uv
HOST ?= 0.0.0.0
PORT ?= 8182

run:
	$(MAKE) run-http

run-http:
	$(UV) run work-mcp --transport streamable-http --host $(HOST) --port $(PORT)

run-stdio:
	$(UV) run work-mcp --transport stdio

test:
	$(UV) run --group dev python -m pytest

init:
	$(UV) run python scripts/init_config.py

doctor:
	$(UV) run python scripts/doctor.py
