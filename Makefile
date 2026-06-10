# Nexus — Makefile
# Run `make help` to see all targets.

PYTHON      ?= python
PIP         ?= $(PYTHON) -m pip
PROJECT     := nexus
TEST_PATH   := tests
COV_MIN     ?= 65

.DEFAULT_GOAL := help

.PHONY: help
help:  ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

.PHONY: install
install:  ## Install package in editable mode with all extras
	$(PIP) install -e ".[all]"

.PHONY: install-dev
install-dev:  ## Install dev tools (ruff, mypy, pytest, pre-commit)
	$(PIP) install -e ".[all]" ruff mypy pytest pytest-cov pytest-mock pre-commit
	pre-commit install

.PHONY: test
test:  ## Run all tests
	$(PYTHON) -m pytest $(TEST_PATH)

.PHONY: test-fast
test-fast:  ## Run tests skipping slow ones
	$(PYTHON) -m pytest $(TEST_PATH) -m "not slow" -q

.PHONY: test-integration
test-integration:  ## Run integration tests (require API keys)
	$(PYTHON) -m pytest tests/integration/ -v

.PHONY: cov
cov:  ## Run tests with coverage and enforce minimum
	$(PYTHON) -m pytest $(TEST_PATH) --cov=$(PROJECT) --cov-report=term-missing --cov-fail-under=$(COV_MIN)

.PHONY: cov-html
cov-html: cov  ## Run tests with coverage and generate HTML report
	$(PYTHON) -m pytest $(TEST_PATH) --cov=$(PROJECT) --cov-report=html
	@echo "Open htmlcov/index.html in your browser"

.PHONY: lint
lint:  ## Run ruff linter
	ruff check .

.PHONY: format
format:  ## Auto-format code with ruff
	ruff format .

.PHONY: format-check
format-check:  ## Check formatting without changes
	ruff format --check .

.PHONY: typecheck
typecheck:  ## Run mypy static type checker
	mypy $(PROJECT)

.PHONY: security
security:  ## Run pip-audit vulnerability scan
	pip-audit || echo "::warning::vulnerabilities found"

.PHONY: clean
clean:  ## Remove build artifacts and caches
	rm -rf build/ dist/ *.egg-info .pytest_cache .mypy_cache .ruff_cache htmlcov
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type d -name ".benchmarks" -exec rm -rf {} + 2>/dev/null || true

.PHONY: build
build: clean  ## Build wheel and sdist
	$(PIP) install --upgrade build
	$(PYTHON) -m build

.PHONY: build-check
build-check: build  ## Build and verify with twine
	$(PIP) install twine
	twine check dist/*

.PHONY: release
release: lint format-check typecheck test build-check  ## Full release checklist (lint + test + build)

.PHONY: pre-commit
pre-commit:  ## Run pre-commit hooks on all files
	pre-commit run --all-files

.PHONY: debug
debug:  ## Run nexus debug for diagnostics
	$(PYTHON) -m nexus debug

.PHONY: all
all: lint format-check typecheck test  ## Run all checks (lint + typecheck + test)