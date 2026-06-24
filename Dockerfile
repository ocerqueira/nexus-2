FROM python:3.14-slim

# WeasyPrint system deps (cairo, pango, gdk-pixbuf)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libffi8 \
    shared-mime-info \
    fonts-liberation \
    libfbclient2 \
    && rm -rf /var/lib/apt/lists/*

# uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# deps layer separado (cache)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .

EXPOSE 8099

CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8099"]
