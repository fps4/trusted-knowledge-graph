FROM python:3.12-slim

WORKDIR /app
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir -e ".[dev]"

COPY ontology ./ontology
COPY mappings ./mappings
COPY config ./config
COPY tests ./tests

ENV PYTHONUNBUFFERED=1
