.PHONY: run renew-fixture

run:
	uv run uvicorn api.app:app --reload --host 0.0.0.0 --port 8000

renew-fixture:
	uv run python -m tools.renew_fixtures \
		--source $(SOURCE) \
		--url "$(URL)" \
		--output "$(OUTPUT)" \
		$(if $(USER_AGENT),--user-agent "$(USER_AGENT)",) \
		$(if $(DELAY),--delay $(DELAY),)
