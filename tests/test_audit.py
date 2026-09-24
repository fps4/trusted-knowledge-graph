"""The chain names the first record that was edited, removed or moved."""

import json

import pytest

from tkg.audit.chain import GENESIS, Hasher, Writer, verify


@pytest.fixture
def log(tmp_path):
    path = tmp_path / "decisions.jsonl"
    writer = Writer(path)
    for n in range(5):
        writer.append({"trace": f"t-{n}", "outcome": "answered"})
    return path


def lines(path):
    return path.read_text().splitlines()


def test_an_untouched_chain_verifies(log):
    result = verify(log)
    assert result.ok and result.records == 5
    assert json.loads(lines(log)[0])["prev_hash"] == GENESIS


def test_an_edited_record_is_named(log):
    ls = lines(log)
    ls[2] = ls[2].replace('"answered"', '"refused"')
    log.write_text("\n".join(ls) + "\n")
    result = verify(log)
    assert not result.ok and result.broken_at == 3 and "edited" in result.reason


def test_a_removed_record_is_named(log):
    ls = lines(log)
    del ls[1]
    log.write_text("\n".join(ls) + "\n")
    result = verify(log)
    assert not result.ok and result.broken_at == 2


def test_reordered_records_are_named(log):
    ls = lines(log)
    ls[1], ls[2] = ls[2], ls[1]
    log.write_text("\n".join(ls) + "\n")
    assert not verify(log).ok


def test_a_cut_tail_is_not_detectable_from_the_file_alone(log):
    """Said in ADR 0012 rather than implied away: hold the head hash elsewhere."""
    head = verify(log).head
    log.write_text("\n".join(lines(log)[:3]) + "\n")
    result = verify(log)
    assert result.ok and result.head != head


def test_hashes_are_salted_and_stable():
    a, b = Hasher(b"x" * 32), Hasher(b"y" * 32)
    assert a("matter", "M-2022-0117") == a("matter", "M-2022-0117")
    assert a("matter", "M-2022-0117") != b("matter", "M-2022-0117")
    assert "M-2022-0117" not in a("matter", "M-2022-0117")
    assert a.salt_id != b.salt_id


def test_a_short_salt_is_refused():
    with pytest.raises(ValueError):
        Hasher(b"short")
