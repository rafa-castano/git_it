# Stage 1: builder — install production dependencies into a venv
FROM python:3.12-slim AS builder

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy dependency manifests first for layer caching
COPY pyproject.toml uv.lock ./

# Install production deps only (no dev group)
RUN uv sync --frozen --no-dev

# Stage 2: runner — lean production image
FROM python:3.12-slim AS runner

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Copy the virtualenv created by uv in the builder stage
COPY --from=builder /app/.venv /app/.venv

# Make the venv available on PATH
ENV PATH="/app/.venv/bin:$PATH"

# Copy application source
COPY src/ ./src/

EXPOSE 8000

CMD ["uvicorn", "git_it.api.app:app", "--host", "0.0.0.0", "--port", "8000", "--app-dir", "src"]
