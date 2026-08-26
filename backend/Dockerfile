# Base image pinned to 3.8.20 (via the `python:3.8-slim` tag) to match the
# `lalitenv` conda environment this project has been developed and tested
# against. A different minor version risks subtle stdlib/typing behavior
# differences, so this is deliberately not "3-slim" or "3.12-slim".
FROM python:3.8-slim

WORKDIR /app

# System packages needed at *runtime*, not just build time:
#
# - poppler-utils: provides the `pdftoppm`/`pdftocairo` binaries `pdf2image`
#   shells out to. Only exercised by the OCR fallback path
#   (app/ingestion/ocr_fallback.py), which is gated behind
#   `Settings.enable_ocr_fallback` (default False) -- but installed here so
#   that flipping `ENABLE_OCR_FALLBACK=true` at runtime actually works
#   in-container instead of failing on a missing binary.
# - tesseract-ocr: the OCR engine `pytesseract` shells out to, needed for the
#   same optional fallback path.
#
# Deliberately NOT installing build-essential/gcc/libpq-dev: every pinned
# dependency in requirements.txt (psycopg2-binary, pandas, Pillow, reportlab,
# rapidfuzz, ...) ships manylinux wheels for cp38 on linux/amd64 and
# linux/arm64, so pip installs them without compiling anything.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        poppler-utils \
        tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-dev.txt ./

# Production images (`docker build backend/` with no --build-arg) install
# only runtime dependencies -- requirements-dev.txt's pytest/httpx are never
# part of the default image. The local docker-compose.yml in this repo opts
# into the dev deps via `--build-arg INSTALL_DEV=true` specifically so that
# `docker compose exec backend pytest` (a local development convenience) has
# a test runner available; that is a decision made in docker-compose.yml, not
# a default of this Dockerfile.
ARG INSTALL_DEV=false
RUN pip install --no-cache-dir -r requirements.txt \
    && if [ "$INSTALL_DEV" = "true" ]; then pip install --no-cache-dir -r requirements-dev.txt; fi

COPY . .

RUN chmod +x /app/docker-entrypoint.sh

# Documentation only (matches .env.example's BACKEND_PORT default); the
# actual bound port is whatever $BACKEND_PORT resolves to at container start
# (see docker-entrypoint.sh) and whatever docker-compose.yml publishes.
EXPOSE 8000

ENTRYPOINT ["/app/docker-entrypoint.sh"]
