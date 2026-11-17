PYTHON ?= python
.PHONY: test lint run app check

test:
	$(PYTHON) -m pytest -q --cov=invest_engine --cov-report=term-missing

lint:
	$(PYTHON) -m ruff check .

run:
	$(PYTHON) scripts/run_case.py cases/dhl_supply_chain

app:
	$(PYTHON) -m streamlit run app.py

check: lint test run
