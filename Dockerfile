# Stage 1: Install dependencies with uv using lockfile
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy dependency files (lockfile ensures exact versions)
COPY pyproject.toml uv.lock ./

# Create venv and install with locked versions
RUN uv sync --frozen --no-dev

# Stage 2: Runtime image
FROM python:3.12-slim

WORKDIR /app

# Copy venv from builder
COPY --from=builder /app/.venv /app/.venv

# Put venv on PATH
ENV PATH="/app/.venv/bin:$PATH"

# Copy application code
COPY src/ ./src/
COPY main.py backtest.py ./

# Create persistent directories
RUN mkdir -p cache logs

CMD ["python", "main.py"]
