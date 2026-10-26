FROM python:3.13.5-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UPLOAD_DIR=/app/uploads

WORKDIR /app

RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --home-dir /app --shell /usr/sbin/nologin app

COPY requirements.txt ./
RUN pip install -r requirements.txt

# app/ and project files (see .dockerignore for exclusions)
COPY . .

# Test image (pytest, httpx): docker build --target test -t jobportal-test .
FROM base AS test
COPY requirements-dev.txt ./
RUN pip install -r requirements-dev.txt \
    && chown -R app:app /app

# Runtime image (default target, last stage): runtime dependencies only
FROM base AS runtime

RUN mkdir -p /app/uploads && chown -R app:app /app

USER app

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=5 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=4).status == 200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
