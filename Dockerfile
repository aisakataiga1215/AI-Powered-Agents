FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    ENABLE_DEMO_FIXTURES=true

WORKDIR /app

COPY backend/pyproject.toml backend/pyproject.toml
COPY backend/app backend/app
COPY scripts scripts

WORKDIR /app/backend
RUN pip install --no-cache-dir -e .
RUN python -m playwright install --with-deps chromium

WORKDIR /app
EXPOSE 7860

CMD ["uvicorn", "app.main:app", "--app-dir", "backend", "--host", "0.0.0.0", "--port", "7860"]
