"""The document store: PDFs, keyed by matter, behind their own access control.

MinIO stands in for the firm's DMS. It holds the authoritative bytes and is never
queried for knowledge. Each persona is a MinIO user with a policy compiled from
the same rules OPA evaluates, so the store refuses the bytes on its own — with no
knowledge of the graph — when the graph would refuse the fact. Two enforcement
points, one policy file. docs/decisions/0021.

Objects are keyed doc/<matter>/<docId>.pdf so a rule about a matter is a rule
about a prefix. Citations carry a presigned URL minted with the asking persona's
credentials, valid for minutes; there is no tool that turns an identifier into
bytes.
"""

from __future__ import annotations

import io
import json
from datetime import timedelta
from pathlib import Path

from minio import Minio
from minio.commonconfig import Tags
from minio.credentials import StaticProvider
from minio.minioadmin import MinioAdmin

from .ingest.documents import FOOTER, Document, render_text

BUCKET = "dms"
REGION = "us-east-1"  # set explicitly, so presigning needs no network call
URL_TTL = timedelta(minutes=5)


def key(doc: Document) -> str:
    return f"doc/{doc.matter}/{doc.doc_id}.pdf"


def render_pdf(doc: Document) -> bytes:
    """Deterministic: the same document renders to the same bytes, every time."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4, invariant=1, pageCompression=0)
    pdf.setTitle(f"{doc.doc_id} — {doc.title}")
    pdf.setAuthor("Lab Firm LLP (synthetic)")
    width, height = A4
    y = height - 25 * mm
    for raw in render_text(doc).splitlines():
        line = raw.rstrip()
        chunks = [line[i : i + 95] for i in range(0, len(line), 95)] or [""]
        for chunk in chunks:
            if y < 25 * mm:
                pdf.showPage()
                y = height - 25 * mm
            bold = chunk in (doc.title, "MEMORANDUM") or chunk.startswith("STRICTLY")
            pdf.setFont("Helvetica-Bold" if bold else "Helvetica", 10)
            if chunk == FOOTER:
                pdf.setFont("Helvetica-Oblique", 7)
            pdf.drawString(20 * mm, y, chunk)
            y -= 5 * mm
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def pdf_text(data: bytes) -> str:
    """PDF → text: the step a firm actually pays for, done here rather than skipped."""
    from pypdf import PdfReader

    return "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(data)).pages)


class Store:
    def __init__(self, endpoint: str, access: str, secret: str) -> None:
        host = endpoint.replace("http://", "").replace("https://", "")
        self.client = Minio(host, access_key=access, secret_key=secret, secure=False,
                            region=REGION)

    def ensure_bucket(self) -> None:
        if not self.client.bucket_exists(BUCKET):
            self.client.make_bucket(BUCKET)

    def put(self, doc: Document, data: bytes) -> None:
        tags = Tags.new_object_tags()
        tags["matter_id"] = doc.matter
        tags["doc_type"] = doc.doc_type
        restricted = doc.confidentiality.startswith("STRICT")
        tags["confidentiality"] = "restricted" if restricted else "standard"
        self.client.put_object(BUCKET, key(doc), io.BytesIO(data), len(data),
                               content_type="application/pdf", tags=tags)

    def get(self, object_key: str) -> bytes:
        response = self.client.get_object(BUCKET, object_key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    def presign(self, object_key: str) -> str:
        return self.client.presigned_get_object(BUCKET, object_key, expires=URL_TTL)


# ── per-persona users and policies, compiled from the same rules as OPA ──────
def persona_policy(denied: set[str] | None) -> dict:
    if denied is None:  # sees nothing
        statements = [{"Effect": "Deny", "Action": ["s3:GetObject"],
                       "Resource": [f"arn:aws:s3:::{BUCKET}/*"]}]
    else:
        statements = [{"Effect": "Allow", "Action": ["s3:GetObject"],
                       "Resource": [f"arn:aws:s3:::{BUCKET}/doc/*"]}]
        if denied:
            statements.append({
                "Effect": "Deny", "Action": ["s3:GetObject"],
                "Resource": [f"arn:aws:s3:::{BUCKET}/doc/{m}/*" for m in sorted(denied)],
            })
    return {"Version": "2012-10-17", "Statement": statements}


def compile_policies(policy_data: dict, personas: list[dict]) -> dict[str, dict]:
    from .access.compile import denied_for

    return {
        p["id"]: persona_policy(denied_for(policy_data, p["principal"]))
        for p in personas
    }


def write_policies(policies: dict[str, dict], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for persona, policy in policies.items():
        (out_dir / f"{persona}.json").write_text(
            json.dumps(policy, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )


def apply_policies(endpoint: str, root: str, root_secret: str,
                   policies: dict[str, dict], secrets: dict[str, str]) -> None:
    host = endpoint.replace("http://", "").replace("https://", "")
    admin = MinioAdmin(endpoint=host, credentials=StaticProvider(root, root_secret),
                       secure=False)
    for persona, policy in policies.items():
        name = f"tkg-{persona}"
        admin.policy_add(name, policy=policy)
        admin.user_add(persona, secrets[persona])
        try:
            admin.attach_policy([name], user=persona)
        except Exception as exc:  # noqa: BLE001 - already attached is not an error
            if "already" not in str(exc).lower():
                raise
