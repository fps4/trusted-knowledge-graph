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

# The embedding model, baked in: the index is built and queried offline.
ENV FASTEMBED_CACHE_PATH=/opt/fastembed
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5', cache_dir='/opt/fastembed')" \
 && chmod -R a+rX /opt/fastembed

COPY src ./src
COPY ontology ./ontology
COPY mappings ./mappings
COPY vocab ./vocab
COPY config ./config
COPY tests ./tests

ENV PYTHONUNBUFFERED=1
