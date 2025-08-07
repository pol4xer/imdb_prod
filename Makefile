.PHONY: all

fix:
	poetry run ruff check --fix
	poetry run ruff format