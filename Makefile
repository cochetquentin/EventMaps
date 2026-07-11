.PHONY: run renew-fixture test test-frontend lint format fix security ci

run:
	uv run uvicorn api.app:app --reload --host 0.0.0.0 --port 8000

renew-fixture:
	uv run python -m tools.renew_fixtures \
		--source $(SOURCE) \
		--url "$(URL)" \
		--output "$(OUTPUT)" \
		$(if $(USER_AGENT),--user-agent "$(USER_AGENT)",) \
		$(if $(DELAY),--delay $(DELAY),)

lint:
	uv run ruff check .

format:
	uv run ruff format --check .

fix:
	uv run ruff check --fix .
	uv run ruff format .

test:
	uv run python -m pytest --cov=. --cov-fail-under=80 tests/ -v

test-frontend:
	npm test

security:
	uv run pip-audit

ci: lint format test test-frontend security
