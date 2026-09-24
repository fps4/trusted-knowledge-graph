"""One append-only, hash-chained record per request. See docs/decisions/0012.

Each record carries the hash of the one before it, so a record cannot be altered,
removed or moved without breaking every hash after it. `verify()` recomputes the
chain and names the first record that fails.

What a chain cannot show is a missing tail: a file cut after record 40 is a
valid chain of 40. verify() returns the head hash so it can be held somewhere
else; in the programme, immutable retention does that job.
"""

from __future__ import annotations

import fcntl
import hashlib
import hmac
import json
from dataclasses import dataclass
from pathlib import Path

GENESIS = "0" * 64


def canonical(record: dict) -> bytes:
    return json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def digest(record: dict) -> str:
    body = {k: v for k, v in record.items() if k != "hash"}
    return hashlib.sha256(canonical(body)).hexdigest()


class Hasher:
    """Denied identifiers, as salted hashes. See docs/decisions/0013.

    HMAC rather than a bare hash: without the salt, a hash of "matter:M-2022-0117"
    could be recomputed by anyone who can guess matter numbers — and matter numbers
    are easy to guess.
    """

    def __init__(self, salt: bytes) -> None:
        if len(salt) < 16:
            raise ValueError("audit salt too short — run `make init`")
        self._salt = salt
        self.salt_id = hashlib.sha256(salt).hexdigest()[:8]

    def __call__(self, kind: str, ident: str) -> str:
        mac = hmac.new(self._salt, f"{kind}:{ident}".encode(), hashlib.sha256)
        return "h:" + mac.hexdigest()[:20]


def _last(handle) -> dict | None:
    handle.seek(0)
    last = None
    for line in handle:
        if line.strip():
            last = line
    return json.loads(last) if last else None


class Writer:
    """The only thing that appends. It locks, so a second process cannot fork the chain."""

    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, record: dict) -> dict:
        with self.path.open("a+", encoding="utf-8") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                prev = _last(handle)
                record = dict(record)
                record["seq"] = (prev["seq"] + 1) if prev else 1
                record["prev_hash"] = prev["hash"] if prev else GENESIS
                record["hash"] = digest(record)
                handle.seek(0, 2)
                handle.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")
                handle.flush()
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)
        return record


def read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


@dataclass
class Verification:
    ok: bool
    records: int
    head: str
    broken_at: int | None = None  # line number, 1-based
    reason: str = ""


def verify(path: Path) -> Verification:
    prev_hash, expected_seq, count = GENESIS, 1, 0
    if not path.exists():
        return Verification(ok=True, records=0, head=GENESIS)
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            return Verification(False, count, prev_hash, number, "not valid JSON")
        if record.get("prev_hash") != prev_hash:
            return Verification(
                False, count, prev_hash, number,
                "prev_hash does not match the record before it — removed or reordered",
            )
        if record.get("seq") != expected_seq:
            return Verification(False, count, prev_hash, number, "sequence number out of order")
        if digest(record) != record.get("hash"):
            return Verification(
                False, count, prev_hash, number, "contents do not match the hash — edited"
            )
        prev_hash, expected_seq, count = record["hash"], expected_seq + 1, count + 1
    return Verification(ok=True, records=count, head=prev_hash)
