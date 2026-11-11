# One definition of green: `make check`. CI runs exactly `make ci` (= locked sync + check).
# Stage order is fail-fast: lint -> types -> tests -> security -> wheel -> guard self-test.

UV ?= uv
RUN := $(UV) run --locked
AUDIT_REQS := .cache/audit-requirements.txt
# Permissive licences only, plus MPL-2.0 (file-level copyleft, dev tooling only). The last entry
# is numpy's exact compound expression: every part is permissive (DECISIONS #33).
LICENSE_ALLOW := MIT License;MIT;BSD License;BSD-2-Clause;BSD-3-Clause;Apache Software License;Apache-2.0;Apache-2.0 OR BSD-2-Clause;Python Software Foundation License;PSF-2.0;ISC License (ISCL);MPL-2.0;Mozilla Public License 2.0 (MPL 2.0);The Unlicense (Unlicense);BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0

.PHONY: help sync hooks lint typecheck test security audit licenses secrets build guards check ci clean

help:
	@grep -E '^[a-z]+:.*##' $(MAKEFILE_LIST) | sed 's/:.*## /\t/'

sync: ## install the locked environment
	$(UV) sync --locked

hooks: ## install git hooks (pre-commit + Conventional Commits check)
	$(RUN) pre-commit install --install-hooks -t pre-commit -t commit-msg

lint: ## ruff lint + format check (includes complexity, size-of-function, args rules)
	$(RUN) ruff check .
	$(RUN) ruff format --check .

typecheck: ## mypy --strict
	$(RUN) mypy

test: ## unit + architecture + integration tests with coverage gate
	$(RUN) pytest tests/unit tests/architecture tests/integration

security: audit licenses secrets ## bandit, pip-audit, licence allowlist, gitleaks
	$(RUN) bandit -q -r src scripts -c pyproject.toml

audit:
	mkdir -p .cache
	$(UV) export --locked --no-emit-project --format requirements-txt -o $(AUDIT_REQS) >/dev/null
	$(RUN) pip-audit --require-hashes --disable-pip -r $(AUDIT_REQS)

licenses:
	$(RUN) pip-licenses --allow-only="$(LICENSE_ALLOW)" --format=plain >/dev/null

secrets:
	gitleaks dir . --no-banner --redact -v

build: ## build the wheel
	$(UV) build --wheel --out-dir dist

guards: ## prove every guard fails on a deliberate violation
	$(RUN) python scripts/guard_selftest.py

check: lint typecheck test security build guards ## the build: must be green to close a phase

ci: ## what CI runs
	$(UV) sync --locked
	$(MAKE) check

clean:
	rm -rf dist build .cache .coverage .mypy_cache .ruff_cache .pytest_cache .hypothesis
