FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies
RUN uv sync --frozen --no-dev

# Copy application
COPY generate-github-release-notes.py ./

# Use uv to run the application
ENTRYPOINT ["uv", "run", "python3", "generate-github-release-notes.py"]
