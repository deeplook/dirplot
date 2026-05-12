FROM python:3.12.13-slim

WORKDIR /app

# Install build tools needed by some optional deps
RUN pip install --no-cache-dir uv==0.11.3

# Copy project metadata first for layer caching
COPY pyproject.toml README.md ./

# Copy source
COPY src/ src/

# Install dirplot with all extras (no dev tools in the runtime image)
RUN uv pip install --system --no-cache ".[ssh,s3]"

# Copy the rest (tests, docs, etc.) so the container is a useful scan target
COPY . .

# Run as non-root
RUN useradd -m app && chown -R app /app
USER app

# Keep the container running so docker:// scanning works
CMD ["python", "-c", "import time; time.sleep(1e9)"]
