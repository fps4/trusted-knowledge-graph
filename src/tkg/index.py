"""The index: passages and their embeddings — a partial copy, by necessity.

The graph holds no document content; the index does, because that is what
retrieval is. So the precise claim is: the graph holds none, the index holds
permission-trimmed passages, the document store holds the authoritative bytes.

Every query the resolver makes carries the permitted matters as a filter *inside*
the query — in the bool filter for BM25 and inside the kNN clause itself — so a
restricted passage is never scored, never ranked, never returned. The naive path
below does not, on purpose: it is the comparison. docs/decisions/0022.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

INDEX = "passages"
MODEL = "BAAI/bge-small-en-v1.5"
DIM = 384


@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    matter: str
    doc_type: str
    text: str


def chunk(doc_id: str, matter: str, doc_type: str, text: str) -> list[Chunk]:
    """Paragraphs, merged up to ~600 characters. The header stays with the first."""
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    out, buf = [], ""
    for p in paras:
        if buf and len(buf) + len(p) > 600:
            out.append(buf)
            buf = ""
        buf = f"{buf}\n\n{p}".strip()
    if buf:
        out.append(buf)
    return [Chunk(f"{doc_id}#{i}", doc_id, matter, doc_type, t) for i, t in enumerate(out)]


class Embedder:
    def __init__(self) -> None:
        from fastembed import TextEmbedding

        self.model = TextEmbedding(MODEL, cache_dir=os.environ.get("FASTEMBED_CACHE_PATH"))

    def __call__(self, texts: list[str]) -> list[list[float]]:
        return [list(map(float, v)) for v in self.model.embed(texts)]


def fingerprint(chunks: list[Chunk]) -> str:
    return hashlib.sha256(
        "\n".join(f"{c.chunk_id}\t{c.text}" for c in chunks).encode()
    ).hexdigest()


class Index:
    def __init__(self, url: str) -> None:
        from opensearchpy import OpenSearch

        self.client = OpenSearch(url, timeout=60)

    def ping(self) -> bool:
        try:
            return bool(self.client.ping())
        except Exception:  # noqa: BLE001
            return False

    def exists(self) -> bool:
        try:
            return bool(self.client.indices.exists(index=INDEX))
        except Exception:  # noqa: BLE001
            return False

    def rebuild(self, chunks: list[Chunk], vectors: list[list[float]]) -> int:
        from opensearchpy import helpers

        if self.client.indices.exists(index=INDEX):
            self.client.indices.delete(index=INDEX)
        self.client.indices.create(index=INDEX, body={
            "settings": {"index": {"knn": True, "number_of_shards": 1, "number_of_replicas": 0}},
            "mappings": {"properties": {
                "chunk_id": {"type": "keyword"}, "doc_id": {"type": "keyword"},
                "matter_id": {"type": "keyword"}, "doc_type": {"type": "keyword"},
                "text": {"type": "text"},
                "embedding": {"type": "knn_vector", "dimension": DIM,
                              "method": {"name": "hnsw", "engine": "lucene",
                                         "space_type": "cosinesimil"}},
            }},
        })
        actions = (
            {"_index": INDEX, "_id": c.chunk_id, "chunk_id": c.chunk_id, "doc_id": c.doc_id,
             "matter_id": c.matter, "doc_type": c.doc_type, "text": c.text, "embedding": v}
            for c, v in zip(chunks, vectors, strict=True)
        )
        ok, _ = helpers.bulk(self.client, actions, refresh=True)
        return ok

    def search(self, text: str, vector: list[float], matters: list[str] | None,
               k: int = 5) -> list[dict]:
        """matters=None is the naive path — no filter. Anything else is a pre-filter."""
        knn = {"vector": vector, "k": k}
        query: dict = {"bool": {"should": [
            {"match": {"text": text}},
            {"knn": {"embedding": knn}},
        ]}}
        if matters is not None:
            allowed = {"terms": {"matter_id": sorted(matters)}}
            knn["filter"] = allowed
            query["bool"]["filter"] = [allowed]
        hits = self.client.search(index=INDEX, body={"size": k, "query": query,
                                                     "_source": {"excludes": ["embedding"]}})
        return [
            {**h["_source"], "score": round(h["_score"], 4)} for h in hits["hits"]["hits"]
        ]


def write_chunks(chunks: list[Chunk], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(c.__dict__, sort_keys=True) for c in chunks) + "\n",
                    encoding="utf-8")
