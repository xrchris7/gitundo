.PHONY: install dev test lint demo clean

install:            ## install into the active environment
	python -m pip install .

dev:                ## editable install with dev extras
	python -m pip install -e ".[dev]"

test:               ## run the test-suite against real throwaway git repos
	python -m pytest

lint:               ## ruff lint + formatting check
	ruff check src tests
	ruff format --check src tests

demo:               ## run the terminal demo (in a throwaway repo)
	bash scripts/demo.sh

wheel:              ## build wheel + sdist
	python -m pip install build
	python -m build

clean:              ## remove build artifacts
	rm -rf build dist *.egg-info .pytest_cache .ruff_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
