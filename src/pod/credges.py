# file: src/pod/credges.py
# description: storage for BITU edges in <pod>\I\-\bitu\bitu.db -- the same
# SQLite file as pod/users.py, sharing its `identities` table. One row per
# pair of identities, with the two keys sorted (low < high, the same
# convention as lib/edges.py). That row holds everything about the pair: the
# debt state (co-signed; the columns are reserved here and written by a later
# step) and the trust each side has stated in the other, so trust needs no
# table of its own.
#
# Trust is stored with the exact signed message and signature, so it can be
# re-verified later or handed to a peer. A withdrawn trust is a NULL value
# that keeps its timestamp: that timestamp is the replay guard, so an old
# signed statement can't be brought back after a withdrawal.
#
# This module trusts its callers to have verified the signature (see
# lib/edges.py); it only enforces the rules that need the stored state:
# timestamps must strictly increase, and a statement must change something.

from __future__ import annotations

from contextlib import closing
from pathlib import Path

from .users import _connect, parse_identity

_SCHEMA = """
CREATE TABLE IF NOT EXISTS edges (
    low_id  INTEGER NOT NULL REFERENCES identities(id),
    high_id INTEGER NOT NULL REFERENCES identities(id),
    -- debt state, signed by both keys (written by a later step)
    debt        INTEGER,
    debt_ts     INTEGER,
    debt_msg    TEXT,
    debt_sig_lo TEXT,
    debt_sig_hi TEXT,
    -- trust the low key states in the high key ("lo"), and the reverse ("hi").
    -- NULL trust with a timestamp means "withdrawn".
    trust_lo     INTEGER,
    trust_lo_ts  INTEGER,
    trust_lo_msg TEXT,
    trust_lo_sig TEXT,
    trust_hi     INTEGER,
    trust_hi_ts  INTEGER,
    trust_hi_msg TEXT,
    trust_hi_sig TEXT,
    PRIMARY KEY (low_id, high_id),
    CHECK (low_id <> high_id)
);
"""

_LIST_SQL = """
SELECT lo.scheme, lo.pubkey, lou.alias,
       hi.scheme, hi.pubkey, hiu.alias,
       e.trust_lo, e.trust_lo_ts, e.trust_hi, e.trust_hi_ts
FROM edges e
JOIN identities lo ON lo.id = e.low_id
JOIN identities hi ON hi.id = e.high_id
LEFT JOIN users lou ON lou.identity_id = lo.id
LEFT JOIN users hiu ON hiu.identity_id = hi.id
WHERE (lo.scheme = ? AND lo.pubkey = ?) OR (hi.scheme = ? AND hi.pubkey = ?)
"""


class EdgeStoreError(Exception):
    """A statement was refused. str(e) is a user-facing reason."""


class StaleStatement(EdgeStoreError):
    def __init__(self, stored_timestamp: int):
        super().__init__("a newer statement for this key is already recorded")
        self.stored_timestamp = stored_timestamp


class UnchangedTrust(EdgeStoreError):
    def __init__(self, trust: int | None):
        super().__init__(
            "there is no trust in that key to withdraw" if trust is None
            else "trust in that key is already set to that value"
        )


def _connect_edges(root: Path):
    conn = _connect(root)
    conn.executescript(_SCHEMA)
    return conn


def _identity_id(conn, identity: str) -> int:
    parsed = parse_identity(identity)
    if parsed is None:
        raise ValueError(f"invalid identity '{identity}'")
    conn.execute("INSERT OR IGNORE INTO identities (scheme, pubkey) VALUES (?, ?)", parsed)
    (iid,) = conn.execute(
        "SELECT id FROM identities WHERE scheme = ? AND pubkey = ?", parsed
    ).fetchone()
    return iid


def store_trust(
    root: Path,
    issuer: str,
    subject: str,
    trust: int | None,
    timestamp: int,
    message: str,
    signature: str,
) -> None:
    """Record `issuer`'s trust in `subject` (n meaning 2^n bits, None = withdrawn).
    The signature must already be verified. Raises StaleStatement if
    `timestamp` is not newer than the stored one, or UnchangedTrust if the
    value is already what is stored."""
    side = "lo" if issuer < subject else "hi"   # which half of the pair's row is the issuer's
    with closing(_connect_edges(root)) as conn, conn:   # `with conn` = one transaction
        conn.execute("BEGIN IMMEDIATE")                 # check + write must not interleave
        issuer_id = _identity_id(conn, issuer)
        subject_id = _identity_id(conn, subject)
        low_id, high_id = (issuer_id, subject_id) if side == "lo" else (subject_id, issuer_id)

        row = conn.execute(
            f"SELECT trust_{side}, trust_{side}_ts FROM edges WHERE low_id = ? AND high_id = ?",
            (low_id, high_id),
        ).fetchone()
        stored_trust, stored_ts = row if row else (None, None)

        if stored_ts is not None and timestamp <= stored_ts:
            raise StaleStatement(stored_ts)
        if trust == stored_trust:
            raise UnchangedTrust(trust)

        conn.execute("INSERT OR IGNORE INTO edges (low_id, high_id) VALUES (?, ?)", (low_id, high_id))
        conn.execute(
            f"UPDATE edges SET trust_{side} = ?, trust_{side}_ts = ?, "
            f"trust_{side}_msg = ?, trust_{side}_sig = ? WHERE low_id = ? AND high_id = ?",
            (trust, timestamp, message, signature, low_id, high_id),
        )


def list_trust(root: Path, identity: str) -> dict:
    """The trust `identity` has stated in others ("outgoing") and the trust
    others have stated in it ("incoming"), withdrawn edges left out, newest
    first. Each entry: the other key, its alias if it is a member of this pod,
    the trust value n and the statement's timestamp."""
    parsed = parse_identity(identity)
    if parsed is None:
        return {"outgoing": [], "incoming": []}
    me = f"{parsed[0]}:{parsed[1]}"
    with closing(_connect_edges(root)) as conn:
        rows = conn.execute(_LIST_SQL, parsed + parsed).fetchall()

    outgoing, incoming = [], []
    for lo_scheme, lo_key, lo_alias, hi_scheme, hi_key, hi_alias, t_lo, ts_lo, t_hi, ts_hi in rows:
        low, high = f"{lo_scheme}:{lo_key}", f"{hi_scheme}:{hi_key}"
        if low == me:
            other, alias, mine, theirs = high, hi_alias, (t_lo, ts_lo), (t_hi, ts_hi)
        else:
            other, alias, mine, theirs = low, lo_alias, (t_hi, ts_hi), (t_lo, ts_lo)
        if mine[0] is not None:
            outgoing.append({"subject": other, "alias": alias, "trust": mine[0], "timestamp": mine[1]})
        if theirs[0] is not None:
            incoming.append({"issuer": other, "alias": alias, "trust": theirs[0], "timestamp": theirs[1]})

    outgoing.sort(key=lambda e: -e["timestamp"])
    incoming.sort(key=lambda e: -e["timestamp"])
    return {"outgoing": outgoing, "incoming": incoming}
