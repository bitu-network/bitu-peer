# file: src/biou/credge_test.py
# description: tests for lib/edges.py. Run from the project root with
#   python -m pytest src/lib/edges_test.py   (with src/ on PYTHONPATH)

from __future__ import annotations

import pytest
from nacl.signing import SigningKey

from lib.edges import (
    DEBT_MAX,
    EdgeError,
    debt_message,
    new_debt_message,
    parse_debt_message,
    parse_trust_message,
    trust_limit_bits,
    trust_message,
    verify_debt,
    verify_signature,
    verify_trust,
)


def make_key() -> tuple[SigningKey, str]:
    key = SigningKey.generate()
    return key, "ed25519:" + key.verify_key.encode().hex()


def sign(key: SigningKey, message: str) -> str:
    return key.sign(message.encode("utf-8")).signature.hex()


def sorted_keys():
    """Two keypairs, ordered so that a < b as identities."""
    (ka, a), (kb, b) = make_key(), make_key()
    return ((ka, a), (kb, b)) if a < b else ((kb, b), (ka, a))


# ---------- trust statements ----------

def test_trust_roundtrip():
    _, a = make_key()
    _, b = make_key()
    msg = trust_message(a, b, 20, 1_700_000_000_000)
    st = parse_trust_message(msg)
    assert (st.issuer, st.subject, st.trust, st.timestamp) == (a, b, 20, 1_700_000_000_000)


def test_trust_null_means_withdrawn():
    _, a = make_key()
    _, b = make_key()
    st = parse_trust_message(trust_message(a, b, None, 5))
    assert st.trust is None
    assert trust_limit_bits(st.trust) is None


def test_trust_zero_is_one_bit():
    _, a = make_key()
    _, b = make_key()
    st = parse_trust_message(trust_message(a, b, 0, 5))
    assert st.trust == 0
    assert trust_limit_bits(0) == 1
    assert trust_limit_bits(20) == 1_048_576


@pytest.mark.parametrize("bad", [-1, 256, True, 1.5, "3"])
def test_trust_range_rejected(bad):
    _, a = make_key()
    _, b = make_key()
    with pytest.raises(EdgeError):
        trust_message(a, b, bad, 5)


def test_trust_self_rejected():
    _, a = make_key()
    with pytest.raises(EdgeError):
        trust_message(a, a, 3, 5)


def test_trust_noncanonical_rejected():
    _, a = make_key()
    _, b = make_key()
    good = trust_message(a, b, 7, 100)
    assert parse_trust_message(good)  # sanity
    variants = [
        good + "\n",                                   # trailing newline
        good.replace("trust: 7", "trust: 07"),         # leading zero
        good.replace("trust: 7", "trust:  7"),         # extra space
        good.replace("trust: 7", "trust: +7"),         # sign
        good.replace(a, a.upper().replace("ED25519", "ed25519")),  # uppercase hex
        good.replace("ed25519:", "", 1),               # bare hex identity
        good.replace("bitu-trust", "bitu-debt"),       # wrong header
        good.replace("trust: 7", "trust: \u0667"),     # non-ASCII digit
        "\n".join(good.split("\n")[:-1]),              # missing field
    ]
    for text in variants:
        with pytest.raises(EdgeError):
            parse_trust_message(text)


# ---------- signatures ----------

def test_verify_trust_ok_and_tampered():
    ka, a = make_key()
    _, b = make_key()
    msg = trust_message(a, b, 10, 1)
    sig = sign(ka, msg)
    assert verify_trust(msg, sig) is not None
    # changing the trust value invalidates the signature
    assert verify_trust(trust_message(a, b, 11, 1), sig) is None


def test_verify_trust_rejects_wrong_signer_and_garbage():
    ka, a = make_key()
    kb, b = make_key()
    msg = trust_message(a, b, 10, 1)
    assert verify_trust(msg, sign(kb, msg)) is None    # subject signed for issuer
    assert verify_trust(msg, "zz") is None             # not hex
    assert verify_trust(msg, "ab" * 10) is None        # wrong length
    assert verify_trust(msg, "") is None
    assert verify_trust("garbage", sign(ka, msg)) is None


def test_verify_signature_bad_identity():
    ka, a = make_key()
    msg = "hello"
    assert verify_signature(a, msg, sign(ka, msg))
    assert not verify_signature("not-an-identity", msg, sign(ka, msg))


# ---------- debt states ----------

def test_debt_sign_convention_and_roundtrip():
    (_, lo), (_, hi) = sorted_keys()
    # low owes high 5 -> +5
    st = parse_debt_message(new_debt_message(lo, hi, 5, 10))
    assert (st.low, st.high, st.debt) == (lo, hi, 5)
    assert st.debtor_creditor() == (lo, hi, 5)
    # high owes low 5 -> -5, same sorted key order
    st = parse_debt_message(new_debt_message(hi, lo, 5, 10))
    assert (st.low, st.high, st.debt) == (lo, hi, -5)
    assert st.debtor_creditor() == (hi, lo, 5)


def test_debt_zero_is_valid():
    (_, lo), (_, hi) = sorted_keys()
    st = parse_debt_message(new_debt_message(hi, lo, 0, 10))
    assert st.debt == 0
    assert st.debtor_creditor() == (lo, hi, 0)


def test_debt_requires_sorted_keys():
    (_, lo), (_, hi) = sorted_keys()
    with pytest.raises(EdgeError):
        debt_message(hi, lo, 1, 1)
    with pytest.raises(EdgeError):
        debt_message(lo, lo, 1, 1)


def test_debt_range():
    (_, lo), (_, hi) = sorted_keys()
    assert parse_debt_message(debt_message(lo, hi, DEBT_MAX, 1)).debt == DEBT_MAX
    assert parse_debt_message(debt_message(lo, hi, -DEBT_MAX, 1)).debt == -DEBT_MAX
    with pytest.raises(EdgeError):
        debt_message(lo, hi, DEBT_MAX + 1, 1)
    with pytest.raises(EdgeError):
        new_debt_message(lo, hi, -1, 1)          # amount must be non-negative
    with pytest.raises(EdgeError):
        new_debt_message(lo, lo, 1, 1)           # cannot owe itself


def test_debt_noncanonical_rejected():
    (_, lo), (_, hi) = sorted_keys()
    good = debt_message(lo, hi, 5, 10)
    for text in (good + "\n", good.replace("debt: 5", "debt: 05"),
                 good.replace("debt: 5", "debt: +5"), good.replace("debt: 5", "debt: -0")):
        with pytest.raises(EdgeError):
            parse_debt_message(text)


def test_verify_debt_needs_both_signatures():
    (klo, lo), (khi, hi) = sorted_keys()
    msg = new_debt_message(lo, hi, 20, 99)
    sig_lo, sig_hi = sign(klo, msg), sign(khi, msg)
    assert verify_debt(msg, sig_lo, sig_hi) is not None
    assert verify_debt(msg, sig_lo, sig_lo) is None        # low signed twice
    assert verify_debt(msg, sig_hi, sig_lo) is None        # signatures swapped
    assert verify_debt(msg, sig_lo, "") is None            # missing one
    other = new_debt_message(lo, hi, 21, 99)
    assert verify_debt(other, sig_lo, sig_hi) is None      # signatures of a different state
