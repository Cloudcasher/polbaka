# Один образ на два сервиса: api и bot запускаются из него с разными командами.
FROM python:3.13-slim

# Не писать .pyc, не буферизовать логи (важно, чтобы логи сразу шли в docker logs)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Зависимости — отдельным слоем: пересобираются только при смене requirements.txt
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Код и статика
COPY app ./app
COPY bot ./bot
COPY web ./web
COPY scripts ./scripts

# По умолчанию поднимается API; бот в docker-compose переопределяет command.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
