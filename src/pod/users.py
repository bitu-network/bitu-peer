# file: src/pod/users.py
# description: web members of a pod, stored in <pod>\I\-\bitu\bitu.db (SQLite).
# `identities` gives every public key a local integer id (scheme + pubkey are
# UNIQUE together); `users` marks which identities may use this pod's web app.
# The integer id is local to this database and is never sent over the network:
# on the wire an identity is always "scheme:pubkey". All database access lives
# in this module, so the storage can be swapped without touching callers.

from __future__ import annotations

import re
import sqlite3
import time
from contextlib import closing
from pathlib import Path

from .config import load_drive_config
from .paths import BITU_DIR, PERSONAL_CONCEPTS_DIR, pod_root

_DB_NAME = "bitu.db"
_HEX = re.compile(r"[0-9a-fA-F]{64}")
_SCHEMES = ("ed25519",)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS identities (
    id     INTEGER PRIMARY KEY,
    scheme TEXT NOT NULL,
    pubkey TEXT NOT NULL,
    UNIQUE (scheme, pubkey)
);
CREATE TABLE IF NOT EXISTS users (
    identity_id INTEGER PRIMARY KEY REFERENCES identities(id),
    alias       TEXT NOT NULL UNIQUE,
    added_at    INTEGER NOT NULL
);
"""


class UserError(Exception):
    """A user command couldn't be completed. str(e) is a user-facing reason."""


class NoPodConfig(UserError):
    def __init__(self, root: Path):
        super().__init__(f"no pod config at {root} (run 'bitu pod init' first)")


class InvalidIdentity(UserError):
    def __init__(self, text: str):
        super().__init__(f"invalid identity '{text}' (expected 64 hex chars, optionally 'ed25519:' first)")


class AliasTaken(UserError):
    def __init__(self, alias: str):
        super().__init__(f"alias '{alias}' already exists")


class AlreadyMember(UserError):
    def __init__(self, identity: str):
        super().__init__(f"'{identity}' is already a member")


class UserNotFound(UserError):
    def __init__(self, ref: str):
        super().__init__(f"no user matching '{ref}' (alias, or at least 4 chars of the key)")


def parse_identity(text: str) -> tuple[str, str] | None:
    """'scheme:hex' (or bare hex, taken as ed25519) -> (scheme, lowercase hex), or None."""
    scheme, sep, key = text.strip().rpartition(":")
    if not sep:
        scheme = "ed25519"
    if scheme not in _SCHEMES or not _HEX.fullmatch(key):
        return None
    return scheme, key.lower()


def db_path(root: Path) -> Path:
    return root / PERSONAL_CONCEPTS_DIR / BITU_DIR / _DB_NAME


def current_pod(cwd: Path | None = None) -> Path:
    """The pod the current directory is on; raises NoPodConfig if it has no config."""
    root = pod_root(cwd if cwd is not None else Path.cwd())
    if load_drive_config(root) is None:
        raise NoPodConfig(root)
    return root


def _connect(root: Path) -> sqlite3.Connection:
    path = db_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(_SCHEMA)
    return conn


def is_member(root: Path, identity: str) -> bool:
    parsed = parse_identity(identity)
    if parsed is None:
        return False
    with closing(_connect(root)) as conn:
        row = conn.execute(
            "SELECT 1 FROM users u JOIN identities i ON i.id = u.identity_id "
            "WHERE i.scheme = ? AND i.pubkey = ?",
            parsed,
        ).fetchone()
    return row is not None


def list_users(root: Path) -> list[dict]:
    with closing(_connect(root)) as conn:
        rows = conn.execute(
            "SELECT i.id, u.alias, i.scheme, i.pubkey, u.added_at "
            "FROM users u JOIN identities i ON i.id = u.identity_id ORDER BY u.added_at, i.id"
        ).fetchall()
    return [dict(zip(("id", "alias", "scheme", "pubkey", "added_at"), r)) for r in rows]


def add_user(root: Path, identity: str, alias: str) -> tuple[str, str]:
    """Authorize an identity. Returns (scheme, pubkey). Raises InvalidIdentity,
    AlreadyMember or AliasTaken."""
    parsed = parse_identity(identity)
    if parsed is None:
        raise InvalidIdentity(identity)
    with closing(_connect(root)) as conn, conn:  # `with conn` = one transaction
        conn.execute("INSERT OR IGNORE INTO identities (scheme, pubkey) VALUES (?, ?)", parsed)
        (iid,) = conn.execute(
            "SELECT id FROM identities WHERE scheme = ? AND pubkey = ?", parsed
        ).fetchone()
        if conn.execute("SELECT 1 FROM users WHERE identity_id = ?", (iid,)).fetchone():
            raise AlreadyMember(identity)
        try:
            conn.execute(
                "INSERT INTO users (identity_id, alias, added_at) VALUES (?, ?, ?)",
                (iid, alias, int(time.time())),
            )
        except sqlite3.IntegrityError:
            raise AliasTaken(alias) from None
    return parsed


def remove_user(root: Path, ref: str) -> None:
    """Revoke membership (matched by alias or key prefix). The identity row is
    kept, since other tables may later refer to it. Raises UserNotFound."""
    key = ref.rsplit(":", 1)[-1].lower()
    for u in list_users(root):
        if u["alias"] == ref or (len(key) >= 4 and u["pubkey"].startswith(key)):
            with closing(_connect(root)) as conn, conn:
                conn.execute("DELETE FROM users WHERE identity_id = ?", (u["id"],))
            return
    raise UserNotFound(ref)
