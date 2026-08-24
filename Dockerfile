FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
WORKDIR /app

RUN useradd --create-home --uid 10001 appuser
COPY requirements-detector.txt pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir -r requirements-detector.txt

COPY config.json official_sources.json ./
ENV PYTHONPATH=/app/src
USER appuser
CMD ["python", "-m", "eew", "--config", "/app/config.json"]
