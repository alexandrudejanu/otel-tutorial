FROM python:3.14-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_DEV=1 \
    PATH="/app/.venv/bin:$PATH"

# Install locked dependencies before the app so this layer stays cached.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

COPY app.py ./

EXPOSE 8080

# OTEL_* variables are set at run time, not baked into the image.
CMD ["opentelemetry-instrument", "python", "app.py"]
