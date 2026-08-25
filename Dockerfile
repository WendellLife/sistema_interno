FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends build-essential libpango-1.0-0 libpangoft2-1.0-0 && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir uv
WORKDIR /app
COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-install-project || uv sync --no-install-project
COPY . .
CMD ["sh", "-c", "uv run python manage.py collectstatic --noinput && uv run python manage.py migrate --noinput && exec uv run gunicorn config.asgi:application -k uvicorn.workers.UvicornWorker -b 0.0.0.0:${PORT:-8000}"]
