.PHONY: install validate test ci reference-build reference-query clean

install:
	python3 -m venv .venv
	. .venv/bin/activate && python -m pip install --upgrade pip && python -m pip install -r requirements-dev.txt

validate:
	python scripts/validate_contracts.py

test:
	python -m pytest -q

reference-build:
	python reference/knowledge_engine.py build --bundle examples/okf-bundle --output .artifacts

reference-query: reference-build
	python reference/knowledge_engine.py query --store .artifacts --channel staging --query "knowledge compiler"

ci: validate test
	python -m compileall -q scripts tests reference

clean:
	rm -rf .venv .pytest_cache .artifacts
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type f -name '*.py[co]' -delete
