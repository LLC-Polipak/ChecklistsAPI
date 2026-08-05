.PHONY: format lint fix

format:
	ruff format .
	djlint . --reformat

lint:
	ruff check . --fix
	djlint .

check:
	ruff format --check .
	ruff check .
	djlint . --check

fix:
	djlint . --reformat
	ruff format .
	ruff check . --fix