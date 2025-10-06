FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

# Set working directory to isolate from GitHub workspace
WORKDIR /app

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies in isolation
RUN uv sync --frozen --no-dev

# Copy application
COPY generate-github-release-notes.py ./

# Use absolute paths to ensure we use our isolated environment
ENTRYPOINT ["uv", "run", "--project", "/app", "python3", "/app/generate-github-release-notes.py"]
