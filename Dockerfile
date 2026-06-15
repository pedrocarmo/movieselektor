FROM python:3.12-slim

WORKDIR /app

# curl is used by the compose healthcheck.
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY seed/ ./seed/

ENV DATABASE_PATH=/data/db.sqlite3 \
    POSTER_DIR=/data/posters \
    SEED_PATH=/app/seed/tspdt-1000.seed.json

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
