FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev

COPY . .

# Créer le répertoire de données et l'utilisateur non-root
RUN mkdir -p /app/data \
    && useradd --create-home --no-log-init --uid 1001 appuser \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000
ENV EVENTMAPS_PORT=8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["sh", "-c", "uv run --no-sync uvicorn api.app:app --host 0.0.0.0 --port ${EVENTMAPS_PORT}"]
