# file: src/lib/auth.py
# description: signature-based web login. The server issues a one-time nonce,
# the client signs a message containing it, the server verifies the signature
# and opens a session. Identity is "<scheme>:<public key hex>"; only ed25519
# is implemented, but the scheme prefix leaves room for others (e.g. a wallet
# scheme) without changing the protocol.
#
# State is in memory (this is a normal importable module, so it survives the
# per-request re-import of handler files in http_app.py). A server restart
# drops pending nonces and sessions: users just log in again.

from __future__ import annotations

import secrets
import time

from nacl.signing import VerifyKey

NONCE_TTL = 120                 # seconds a challenge stays valid
SESSION_TTL = 7 * 24 * 3600     # seconds a session stays valid

_nonces: dict[str, float] = {}                    # nonce -> expiry
_sessions: dict[str, tuple[str, float]] = {}      # token -> (identity, expiry)


def _purge() -> None:
    now = time.time()
    for n in [n for n, exp in _nonces.items() if exp <= now]:
        del _nonces[n]
    for t in [t for t, (_, exp) in _sessions.items() if exp <= now]:
        del _sessions[t]


def login_message(host: str, nonce: str) -> str:
    """The exact text the client signs. Binding the host stops a signature
    collected by another site from being replayed here."""
    return f"bitu-login\nhost: {host}\nnonce: {nonce}"


def new_challenge(host: str) -> tuple[str, str]:
    _purge()
    nonce = secrets.token_urlsafe(24)
    _nonces[nonce] = time.time() + NONCE_TTL
    return nonce, login_message(host, nonce)


def verify_login(host: str, nonce: str, public_key_hex: str, signature_hex: str) -> str | None:
    """Return the identity ("ed25519:<hex>") if the signature is valid, else
    None. The nonce is burned either way, so each challenge is single-use."""
    expiry = _nonces.pop(nonce, None)
    if expiry is None or expiry <= time.time():
        return None
    try:
        VerifyKey(bytes.fromhex(public_key_hex)).verify(
            login_message(host, nonce).encode("utf-8"),
            bytes.fromhex(signature_hex),
        )
    except Exception:  # bad hex, wrong length, or bad signature
        return None
    return f"ed25519:{public_key_hex.lower()}"


def new_session(identity: str) -> str:
    _purge()
    token = secrets.token_urlsafe(32)
    _sessions[token] = (identity, time.time() + SESSION_TTL)
    return token


def session_identity(token: str | None) -> str | None:
    if not token:
        return None
    entry = _sessions.get(token)
    if entry is None or entry[1] <= time.time():
        return None
    return entry[0]
