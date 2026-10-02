# file: src/biou/credge.py
# description: the signed messages behind BITU edges, as plain readable text
# (the same style as the login message in lib/auth.py), plus their
# verification. Pure logic: no database, no network, no clock. Storage and
# timestamp/replay checks against stored state belong to the callers.
#
# Two message types:
#
#   Trust statement -- signed by its issuer ALONE. "I trust <subject> up to
#   2^n bits", or n = null to withdraw trust. Unilateral on purpose: anyone can
#   state trust in any key, and lowering your own exposure never needs the
#   other side's cooperation.
#
#       bitu-trust
#       issuer: ed25519:<64 hex>
#       subject: ed25519:<64 hex>
#       trust: <0..255 | null>
#       timestamp: <unix ms>
#
#   Debt state -- signed by BOTH parties. The two keys are always sorted
#   (low < high) so one edge has exactly one encoding; debt is a signed
#   integer in bits, positive meaning "low owes high". A debt of 0 is a valid
#   (settled) state.
#
#       bitu-debt
#       low: ed25519:<64 hex>
#       high: ed25519:<64 hex>
#       debt: <integer>
#       timestamp: <unix ms>
#
# A message is accepted only if it is byte-for-byte canonical: parsing it and
# rebuilding it must give back the exact same text. That removes every
# "same meaning, different bytes" ambiguity (case, spacing, leading zeros,
# trailing newline) from what gets signed.

from __future__ import annotations

import re
from dataclasses import dataclass

from nacl.signing import VerifyKey

from pod.users import parse_identity

TRUST_HEADER = "bitu-trust"
DEBT_HEADER = "bitu-debt"

TRUST_MAX = 255            # trust is one byte: n means 2^n bits
DEBT_MAX = 2**63 - 1       # debt fits a signed 64-bit integer, either direction
TIMESTAMP_MAX = 2**63 - 1

_UINT = re.compile(r"0|[1-9][0-9]*")
_INT = re.compile(r"0|-?[1-9][0-9]*")


class EdgeError(ValueError):
    """A message is malformed, non-canonical, or out of range."""


# -----------------------
# Helpers
# -----------------------
def _identity(text: str) -> str:
    parsed = parse_identity(text)
    if parsed is None:
        raise EdgeError(f"invalid identity '{text}'")
    return f"{parsed[0]}:{parsed[1]}"


def _check_int(name: str, value: object, low: int, high: int) -> int:
    # bool is an int subclass; True/False must not pass as 1/0.
    if isinstance(value, bool) or not isinstance(value, int) or not (low <= value <= high):
        raise EdgeError(f"{name} must be an integer in {low}..{high}")
    return value


def _fields(text: str, header: str, names: tuple[str, ...]) -> list[str]:
    """Split a message into its field values, requiring the exact header and
    field order. Canonical-form enforcement happens afterwards by rebuilding."""
    lines = text.split("\n")
    if len(lines) != len(names) + 1 or lines[0] != header:
        raise EdgeError("malformed message")
    values = []
    for line, name in zip(lines[1:], names):
        prefix = name + ": "
        if not line.startswith(prefix):
            raise EdgeError("malformed message")
        values.append(line[len(prefix):])
    return values


def _parse_uint(name: str, text: str) -> int:
    if not _UINT.fullmatch(text):
        raise EdgeError(f"{name} is not a canonical non-negative integer")
    return int(text)


def _parse_int(name: str, text: str) -> int:
    if not _INT.fullmatch(text):
        raise EdgeError(f"{name} is not a canonical integer")
    return int(text)


def trust_limit_bits(trust: int | None) -> int | None:
    """The cap in bits that a trust value stands for: 2^n, or None if withdrawn."""
    return None if trust is None else 1 << trust


# -----------------------
# Trust statement
# -----------------------
@dataclass(frozen=True)
class TrustStatement:
    issuer: str
    subject: str
    trust: int | None      # n meaning 2^n bits; None = trust withdrawn
    timestamp: int         # unix milliseconds


def trust_message(issuer: str, subject: str, trust: int | None, timestamp: int) -> str:
    """The exact text an issuer signs. Raises EdgeError on invalid input."""
    issuer, subject = _identity(issuer), _identity(subject)
    if issuer == subject:
        raise EdgeError("cannot state trust in yourself")
    if trust is not None:
        _check_int("trust", trust, 0, TRUST_MAX)
    _check_int("timestamp", timestamp, 0, TIMESTAMP_MAX)
    return "\n".join((
        TRUST_HEADER,
        f"issuer: {issuer}",
        f"subject: {subject}",
        f"trust: {'null' if trust is None else trust}",
        f"timestamp: {timestamp}",
    ))


def parse_trust_message(text: str) -> TrustStatement:
    """Parse a trust message, rejecting anything that is not canonical."""
    issuer, subject, trust, timestamp = _fields(
        text, TRUST_HEADER, ("issuer", "subject", "trust", "timestamp"))
    statement = TrustStatement(
        issuer=issuer,
        subject=subject,
        trust=None if trust == "null" else _parse_uint("trust", trust),
        timestamp=_parse_uint("timestamp", timestamp),
    )
    if trust_message(statement.issuer, statement.subject, statement.trust, statement.timestamp) != text:
        raise EdgeError("message is not in canonical form")
    return statement


# -----------------------
# Debt state
# -----------------------
@dataclass(frozen=True)
class DebtState:
    low: str               # the lexicographically smaller identity
    high: str
    debt: int              # bits; positive: low owes high, negative: high owes low
    timestamp: int         # unix milliseconds

    def debtor_creditor(self) -> tuple[str, str, int]:
        """(debtor, creditor, amount >= 0). A settled edge (0) returns (low, high, 0)."""
        if self.debt >= 0:
            return self.low, self.high, self.debt
        return self.high, self.low, -self.debt


def debt_message(low: str, high: str, debt: int, timestamp: int) -> str:
    """The exact text both parties sign, from already-sorted keys."""
    low, high = _identity(low), _identity(high)
    if not low < high:
        raise EdgeError("keys must be sorted: low < high")
    _check_int("debt", debt, -DEBT_MAX, DEBT_MAX)
    _check_int("timestamp", timestamp, 0, TIMESTAMP_MAX)
    return "\n".join((
        DEBT_HEADER,
        f"low: {low}",
        f"high: {high}",
        f"debt: {debt}",
        f"timestamp: {timestamp}",
    ))


def new_debt_message(debtor: str, creditor: str, amount: int, timestamp: int) -> str:
    """Build a debt message from the human view ("debtor owes creditor
    amount"), doing the sorting and sign convention in one place."""
    debtor, creditor = _identity(debtor), _identity(creditor)
    if debtor == creditor:
        raise EdgeError("a key cannot owe itself")
    _check_int("amount", amount, 0, DEBT_MAX)
    if debtor < creditor:
        return debt_message(debtor, creditor, amount, timestamp)
    return debt_message(creditor, debtor, -amount, timestamp)


def parse_debt_message(text: str) -> DebtState:
    """Parse a debt message, rejecting anything that is not canonical."""
    low, high, debt, timestamp = _fields(
        text, DEBT_HEADER, ("low", "high", "debt", "timestamp"))
    state = DebtState(
        low=low,
        high=high,
        debt=_parse_int("debt", debt),
        timestamp=_parse_uint("timestamp", timestamp),
    )
    if debt_message(state.low, state.high, state.debt, state.timestamp) != text:
        raise EdgeError("message is not in canonical form")
    return state


# -----------------------
# Signatures
# -----------------------
def verify_signature(identity: str, message: str, signature_hex: str) -> bool:
    """True if `signature_hex` is a valid Ed25519 signature of `message`
    (UTF-8) by `identity`. Never raises: bad input is simply invalid."""
    parsed = parse_identity(identity)
    if parsed is None:
        return False
    try:
        VerifyKey(bytes.fromhex(parsed[1])).verify(
            message.encode("utf-8"), bytes.fromhex(signature_hex))
    except Exception:  # bad hex, wrong length, or bad signature
        return False
    return True


def verify_trust(message: str, signature_hex: str) -> TrustStatement | None:
    """The statement if `message` is canonical and signed by its own issuer, else None."""
    try:
        statement = parse_trust_message(message)
    except EdgeError:
        return None
    return statement if verify_signature(statement.issuer, message, signature_hex) else None


def verify_debt(message: str, signature_low: str, signature_high: str) -> DebtState | None:
    """The state if `message` is canonical and signed by BOTH of its keys, else None."""
    try:
        state = parse_debt_message(message)
    except EdgeError:
        return None
    if verify_signature(state.low, message, signature_low) and verify_signature(state.high, message, signature_high):
        return state
    return None
