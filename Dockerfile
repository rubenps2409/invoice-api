# syntax=docker/dockerfile:1

# ---- build: uv installs the locked dependencies and the package into a venv ----
FROM python:3.13-slim AS build

COPY --from=ghcr.io/astral-sh/uv:0.12.23 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Dependencies first: this layer is rebuilt only when pyproject.toml or uv.lock change.
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# Then the package itself, installed (not editable) so the final image needs no sources.
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable


# ---- runtime: Python and the venv, nothing else ----
FROM python:3.13-slim AS runtime

# No uv, no compilers, no tests: only what runs the API and its migrations.
RUN useradd --system --create-home --uid 10001 app

WORKDIR /app
COPY --from=build /app/.venv ./.venv
COPY alembic.ini ./
COPY migrations ./migrations

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER app
EXPOSE 8000

# python:slim has no curl. A 503 (database down) makes urlopen raise, so it fails too.
HEALTHCHECK --interval=15s --timeout=4s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)"]

# --proxy-headers only trusts forwarded headers from FORWARDED_ALLOW_IPS (127.0.0.1 by
# default): set it to the reverse proxy's address, or every client shares one IP limit.
CMD ["uvicorn", "invoice_api.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
