"""Identity is fixed by a key, not by a parameter."""

import pytest

from tkg.access import permit
from tkg.identity import IdentityError, mint, verify

KEYS = {"mara": b"m" * 64, "sanne": b"s" * 64}


def test_a_persona_proves_itself_with_its_own_key():
    assert verify(mint("sanne", KEYS["sanne"]), KEYS) == "sanne"


def test_one_persona_cannot_claim_another_with_its_own_key():
    forged = mint("mara", KEYS["sanne"])  # sanne's key, mara's name
    with pytest.raises(IdentityError, match="does not verify"):
        verify(forged, KEYS)


def test_an_unknown_persona_is_refused():
    with pytest.raises(IdentityError, match="unknown"):
        verify(mint("mallory", b"z" * 64), KEYS)


def test_an_expired_assertion_is_refused():
    with pytest.raises(IdentityError, match="expired"):
        verify(mint("sanne", KEYS["sanne"], now=1_000_000), KEYS)


def test_garbage_is_refused():
    with pytest.raises(IdentityError):
        verify("not-a-token", KEYS)


def test_a_permit_opens_only_for_the_person_it_was_issued_to():
    token, _ = permit.mint("sanne", "t-1", ["M-1"], [], b"k" * 64)
    assert permit.verify(token, b"k" * 64, "sanne")["matters"] == ["M-1"]
    with pytest.raises(permit.PermitError, match="someone else"):
        permit.verify(token, b"k" * 64, "mara")


def test_an_expired_permit_is_refused():
    token, _ = permit.mint("sanne", "t-1", [], [], b"k" * 64, now=1_000_000)
    with pytest.raises(permit.PermitError, match="expired"):
        permit.verify(token, b"k" * 64, "sanne")


def test_a_permit_signed_with_another_key_is_refused():
    token, _ = permit.mint("sanne", "t-1", [], [], b"x" * 64)
    with pytest.raises(permit.PermitError):
        permit.verify(token, b"k" * 64, "sanne")
