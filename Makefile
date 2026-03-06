.PHONY: install lint format test coverage clean install-tool check-all publish-test publish

install:
	uv sync --all-extras

lint:
	uv run ruff check src tests
	uv run mypy src

format:
	uv run ruff format src tests
	uv run ruff check --fix src tests

test:
	uv run --all-extras pytest

coverage:
	uv run --all-extras pytest --cov=src --cov-report=html --cov-report=term

clean:
	rm -rf dist build *.egg-info
	rm -rf .pytest_cache .mypy_cache .ruff_cache
	rm -rf htmlcov .coverage coverage.xml
	find . -type d -name __pycache__ -exec rm -rf {} +

install-tool:
	uv tool install --reinstall .

publish-test:
	uv build
	uv publish --index testpypi --token $(TEST_PYPI_TOKEN)

publish:
	uv build
	uv publish --token $(PYPI_TOKEN)

check-all: install format lint test clean
	@echo "All checks passed!"
