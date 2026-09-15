.PHONY: format lint fix

format:
	ruff format .

lint:
	ruff check . --fix

check:
	ruff format --check .
	ruff check .

fix:
	djlint . --reformat
	ruff format .
