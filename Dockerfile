FROM python:3.12-slim

WORKDIR /app

# Install build tools needed by some optional deps
RUN pip install --no-cache-dir uv

# Copy project metadata first for layer caching
COPY pyproject.toml README.md ./

# Copy source
COPY src/ src/

# Install dirplot with all extras
RUN uv pip install --system --no-cache ".[ssh,s3,docker,dev]"

# Copy the rest (tests, docs, etc.) so the container is a useful scan target
COPY . .

# Keep the container running so docker:// scanning works
CMD ["sleep", "infinity"]
