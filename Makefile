.PHONY: compile unit integration test clean

PYTHON ?= python

compile:
	$(PYTHON) -m compileall -q oss_remediation_agent

unit:
	$(PYTHON) -m unittest discover -s tests/unit -p "test_*.py" -v

integration:
	$(PYTHON) -m unittest discover -s tests/integration -p "test_*.py" -v

test:
	$(PYTHON) run_tests.py

clean:
	find . -type d -name "__pycache__" -prune -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
