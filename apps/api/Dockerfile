FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app
WORKDIR /app
COPY apps/api/requirements.txt apps/api/requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock && useradd --uid 10001 --create-home appuser
COPY apps/api/ .
COPY tests/ ./tests/
COPY database/migrations/ ./migrations/
USER appuser
EXPOSE 8000
CMD ["sh", "-c", "python migrate.py && exec uvicorn main:app --host 0.0.0.0 --port 8000 --no-proxy-headers --no-access-log"]
