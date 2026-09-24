FROM python:3.12-slim

WORKDIR /app
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/*

# Dependencies first, against a stub package, so a source change does not
# reinstall them. The editable install then resolves to the real src/ below.
COPY pyproject.toml README.md ./
RUN mkdir -p src/tkg && echo '__version__ = "0"' > src/tkg/__init__.py \
 && pip install --no-cache-dir -e ".[dev]"

COPY src ./src
COPY ontology ./ontology
COPY mappings ./mappings
COPY vocab ./vocab
COPY config ./config
COPY tests ./tests

ENV PYTHONUNBUFFERED=1
