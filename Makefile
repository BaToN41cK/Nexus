# Nexus — Makefile
# Run `make help` to see all targets.

PYTHON      ?= python
PIP         ?= $(PYTHON) -m pip
PROJECT     := nexus
TEST_PATH   := tests
COV_MIN     ?= 70

.DEFAULT_GOAL := help

.PHONY: help
help:  ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

.PHONY: install
install:  ## Install package in editable mode with all extras
	$(PIP) install -e ".[all]"

.PHONY: install-dev
install-dev:  ## Install dev tools (ruff, mypy, pytest plugins)
	$(PIP) install -e ".[all]" ruff mypy pytest pytest-cov pytest-mock

.PHONY: test
test:  ## Run tests
	$(PYTHON) -m pytest $(TEST_PATH)

.PHONY: test-fast
test-fast:  ## Run tests skipping slow ones
	$(PYTHON) -m pytest $(TEST_PATH) -m "not slow" -q

.PHONY: cov
cov:  ## Run tests with coverage and enforce minimum
	$(PYTHON) -m pytest $(TEST_PATH) --cov=$(PROJECT) --cov-report=term-missing --cov-fail-under=$(COV_MIN)

.PHONY: lint
lint:  ## Run ruff linter
	ruff check .

.PHONY: format
format:  ## Auto-format code with ruff
	ruff format .

.PHONY: typecheck
typecheck:  ## Run mypy
	mypy $(PROJECT)

.PHONY: clean
clean:  ## Remove build artifacts and caches
	rm -rf build/ dist/ *.egg-info .pytest_cache .mypy_cache .ruff_cache htmlcov
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete

.PHONY: build
build:  ## Build wheel and sdist
	$(PIP) install --upgrade build
	$(PYTHON) -m build

.PHONY: debug
debug:  ## Run nexus debug for diagnostics
	$(PYTHON) -m nexus debug

.PHONY: pre-commit
pre-commit:  ## Run pre-commit hooks on all files
	pre-commit run --all-files
