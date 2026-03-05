.PHONY: lint test format

lint:
	cd server && uv run ruff check .
	cd team-api && uv run ruff check .

format:
	cd server && uv run ruff format .
	cd team-api && uv run ruff format .

test:
	cd server && uv run pytest
	cd team-api && uv run pytest
