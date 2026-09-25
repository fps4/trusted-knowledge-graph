"""The document half of `make load`: render, store, extract-into-graph, index.

Kept apart from the spine so each half can be read on its own. Everything here is
idempotent and rebuilt from the repository: the stores are disposable.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .. import dms
from ..index import Chunk, Embedder, Index, chunk, fingerprint, write_chunks
from . import documents as documents_mod


class StaleFixture(RuntimeError):
    pass


def _digest(docs: list[documents_mod.Document]) -> str:
    body = "\n".join(json.dumps(d.__dict__, sort_keys=True) for d in docs)
    return hashlib.sha256(body.encode()).hexdigest()


def check_documents(est, cfg: dict, seed: int, path: Path) -> list[documents_mod.Document]:
    """The committed documents must be what the estate generates today."""
    fresh = documents_mod.build(est, cfg, seed)
    committed = documents_mod.read(path) if path.exists() else []
    if _digest(fresh) != _digest(committed):
        raise StaleFixture(
            f"{path.name} is not what the estate generates — run `make documents` and "
            "re-run extraction, or the gold set and the documents disagree"
        )
    return committed


def render(docs: list[documents_mod.Document], cache: Path) -> tuple[dict, dict]:
    """PDF bytes, and the text extracted back out of them — the text a firm has."""
    pdfs, texts = {}, {}
    cached = {}
    if cache.exists():
        cached = {r["doc_id"]: r for r in map(json.loads, cache.read_text().splitlines())}
    rows = []
    for d in docs:
        data = dms.render_pdf(d)
        sha = hashlib.sha256(data).hexdigest()
        text = cached[d.doc_id]["text"] if cached.get(d.doc_id, {}).get("sha") == sha \
            else dms.pdf_text(data)
        pdfs[d.doc_id], texts[d.doc_id] = data, text
        rows.append({"doc_id": d.doc_id, "sha": sha, "text": text})
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    return pdfs, texts


def upload(store: dms.Store, docs: list[documents_mod.Document], pdfs: dict) -> int:
    store.ensure_bucket()
    for d in docs:
        store.put(d, pdfs[d.doc_id])
    return len(docs)


def index(index_url: str, docs: list[documents_mod.Document], texts: dict,
          cache_dir: Path, cites: dict[str, list[str]] | None = None) -> tuple[int, int]:
    """`cites`: doc id -> the matters it cites, from the *linked extraction* — what the
    graph knows, not the manifest. A citation extraction missed is not in the filter."""
    chunks: list[Chunk] = []
    for d in docs:
        chunks += chunk(d.doc_id, d.matter, d.doc_type, texts[d.doc_id],
                        (cites or {}).get(d.doc_id, ()))
    write_chunks(chunks, cache_dir / "chunks.jsonl")
    vectors_path = cache_dir / f"vectors-{fingerprint(chunks)[:16]}.json"
    if vectors_path.exists():
        vectors = json.loads(vectors_path.read_text())
    else:
        vectors = Embedder()([c.text for c in chunks])
        for old in cache_dir.glob("vectors-*.json"):
            old.unlink()
        vectors_path.write_text(json.dumps(vectors))
    return Index(index_url).rebuild(chunks, vectors), len(docs)
