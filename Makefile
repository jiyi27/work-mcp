.PHONY: run run-http run-stdio test

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
	$(UV) run pytest
