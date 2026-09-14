.PHONY: install run demo lint test check format

install:
	poetry install --no-interaction

run:
	poetry run python flask_app.py

demo:
	poetry run python -m imdb_extractor.demo --output-dir var/demo

lint:
	poetry run ruff check .
	poetry run ruff format --check .

test:
	poetry run pytest

check:
	poetry check --lock
	$(MAKE) lint
	$(MAKE) test

format:
	poetry run ruff check --fix .
	poetry run ruff format .
