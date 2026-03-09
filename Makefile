.PHONY: install lint format test coverage clean install-tool check-all publish-test publish help

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*##' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "  %-14s %s\n", $$1, $$2}'

install:  ## Install all dependencies (including extras)
	uv sync --all-extras

format:  ## Auto-format and fix lint issues
	uv run ruff format src tests
	uv run ruff check --fix src tests

lint:  ## Run ruff and mypy
	uv run ruff check src tests
	uv run --all-extras mypy src

test:  ## Run the test suite
	uv run --all-extras pytest

coverage:  ## Run tests with HTML + terminal coverage report
	uv run --all-extras pytest --cov=src --cov-report=html --cov-report=term

check-all: install format lint test clean  ## Run format, lint, test, and clean
	@echo "All checks passed!"

install-tool:  ## Install dirplot as a uv tool (reinstall)
	uv tool install --reinstall .

clean:  ## Remove build artifacts and caches
	rm -rf dist build *.egg-info
	rm -rf .pytest_cache .mypy_cache .ruff_cache
	rm -rf htmlcov .coverage coverage.xml
	find . -type d -name __pycache__ -exec rm -rf {} +

publish-test:  ## Build and publish to TestPyPI
	uv build
	uv publish --index testpypi --token $(TEST_PYPI_TOKEN)

publish:  ## Build and publish to PyPI
	uv build
	uv publish --token $(PYPI_TOKEN)
