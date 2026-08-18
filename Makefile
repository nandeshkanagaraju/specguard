.PHONY: help install demo demo-clean demo-drift check serve test test-fixture oracle clean

PY      ?= .venv/bin/python
SG      ?= .venv/bin/specguard
FIXTURE := samples/orderflow

help:
	@echo "  make install      create .venv and install SpecGuard"
	@echo "  make demo         demo-drift, then serve the dashboard"
	@echo "  make demo-clean   put the fixture on its clean commit"
	@echo "  make demo-drift   put the fixture on its drifted commit"
	@echo "  make check        run the CLI against the fixture"
	@echo "  make serve        dashboard on http://127.0.0.1:8000"
	@echo "  make test         SpecGuard's own suite"
	@echo "  make test-fixture the fixture's suite, on both commits"
	@echo "  make oracle       recompile the offline oracle"
	@echo "  make clean        drop reports and caches"

install:
	python3.11 -m venv .venv
	$(PY) -m pip install --quiet --upgrade pip
	$(PY) -m pip install --quiet -e ".[dev]"
	@./scripts/build_fixture.sh
	@echo "ready — try: make demo"

# The fixture is its own git repo, so it is built after clone rather than committed.
fixture:
	@./scripts/build_fixture.sh

demo-clean:
	@./scripts/demo.sh clean

demo-drift:
	@./scripts/demo.sh drift

demo: demo-drift serve

check:
	-@$(SG) check $(FIXTURE)

serve:
	@$(SG) serve $(FIXTURE)

test:
	@$(PY) -m pytest -q

# The load-bearing claim: the fixture's own suite is green on BOTH commits.
test-fixture:
	@./scripts/demo.sh drift >/dev/null
	@cd $(FIXTURE) && ../../$(PY) -m pytest -q
	@./scripts/demo.sh clean >/dev/null
	@cd $(FIXTURE) && ../../$(PY) -m pytest -q

oracle:
	@$(PY) scripts/seed_oracle.py

clean:
	@rm -rf $(FIXTURE)/.specguard .pytest_cache
	@find . -name __pycache__ -type d -prune -exec rm -rf {} +
	@echo "cleaned"
