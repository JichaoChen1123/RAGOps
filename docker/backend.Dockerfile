FROM python:3.11-slim-bookworm

ARG UV_VERSION=0.12.1

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

RUN pip install --no-cache-dir "uv==${UV_VERSION}"

COPY backend/pyproject.toml backend/uv.lock backend/README.md ./
COPY backend/app ./app
RUN uv sync --frozen --no-dev

RUN addgroup --system ragops \
    && adduser --system --ingroup ragops --home /app ragops \
    && mkdir -p /data \
    && chown -R ragops:ragops /app /data

USER ragops

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
