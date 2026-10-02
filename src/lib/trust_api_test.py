# file: src/lib/trust_api_test.py
# description: end-to-end tests of /api/trust through the real app: the
# signature login, the membership gate, the handler and the SQLite storage.
# Every test runs twice, once with alice's key sorting below bob's and once
# above, because the two halves of a pair's row are stored differently.
# Run from the project root: python -m pytest src/lib/trust_api_test.py

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from nacl.signing import SigningKey

from lib.edges import trust_message
from lib.http_app import create_app
from pod.users import add_user, db_path

WEB_PUBLIC_ROOT = Path(__file__).resolve().parents[1] / "http" / "external"


def identity(key: SigningKey) -> str:
    return "ed25519:" + key.verify_key.encode().hex()


def sign(key: SigningKey, text: str) -> str:
    return key.sign(text.encode("utf-8")).signature.hex()


def now_ms() -> int:
    return int(time.time() * 1000)


class Member:
    """A browser: a key, a cookie jar, and the ability to sign statements."""

    def __init__(self, app, key: SigningKey):
        self.key = key
        self.identity = identity(key)
        self.client = app.test_client()

    def login(self) -> "Member":
        challenge = self.client.get("/api/challenge").get_json()
        res = self.client.post("/api/verify", json={
            "nonce": challenge["nonce"],
            "public_key": self.key.verify_key.encode().hex(),
            "signature": sign(self.key, challenge["message"]),
        })
        assert res.status_code == 200
        return self

    def state(self) -> dict:
        res = self.client.get("/api/trust")
        assert res.status_code == 200
        return res.get_json()

    def post(self, message: str, signature: str):
        return self.client.post("/api/trust", json={"message": message, "signature": signature})

    def say(self, subject: str, trust: int | None, timestamp: int):
        """State trust in `subject`, signed by this member."""
        message = trust_message(self.identity, subject, trust, timestamp)
        return self.post(message, sign(self.key, message))


@pytest.fixture(params=[True, False], ids=["alice-low", "alice-high"])
def world(request, tmp_path):
    low, high = sorted((SigningKey.generate(), SigningKey.generate()), key=identity)
    alice_key, bob_key = (low, high) if request.param else (high, low)
    app = create_app(WEB_PUBLIC_ROOT, drive_root=tmp_path)
    add_user(tmp_path, identity(alice_key), "alice")
    add_user(tmp_path, identity(bob_key), "bob")
    return SimpleNamespace(
        app=app,
        root=tmp_path,
        alice=Member(app, alice_key).login(),
        bob=Member(app, bob_key).login(),
        t=now_ms() - 60_000,    # a base timestamp; tests add 1, 2, ... to it
    )


# ---------- who may use it ----------

def test_requires_a_session(world):
    anonymous = world.app.test_client()
    assert anonymous.get("/api/trust").status_code == 401
    assert anonymous.post("/api/trust", json={}).status_code == 401


def test_non_member_is_refused(world):
    outsider = Member(world.app, SigningKey.generate()).login()
    assert outsider.client.get("/api/trust").status_code == 401
    assert outsider.say(world.bob.identity, 5, world.t).status_code == 401


def test_trust_page_is_for_members_only(world):
    anonymous = world.app.test_client()
    res = anonymous.get("/trust")
    assert res.status_code == 302 and res.headers["Location"].endswith("/login")
    page = world.alice.client.get("/trust")
    assert page.status_code == 200 and b"<table" in page.data


# ---------- stating and listing trust ----------

def test_state_and_list(world):
    assert world.alice.say(world.bob.identity, 20, world.t).status_code == 200

    mine = world.alice.state()
    assert mine["identity"] == world.alice.identity
    assert [(e["subject"], e["alias"], e["trust"]) for e in mine["outgoing"]] == [(world.bob.identity, "bob", 20)]
    assert mine["incoming"] == []

    theirs = world.bob.state()
    assert [(e["issuer"], e["alias"], e["trust"]) for e in theirs["incoming"]] == [(world.alice.identity, "alice", 20)]
    assert theirs["outgoing"] == []


def test_both_directions_share_one_row(world):
    assert world.alice.say(world.bob.identity, 10, world.t).status_code == 200
    assert world.bob.say(world.alice.identity, 20, world.t + 1).status_code == 200

    a, b = world.alice.state(), world.bob.state()
    assert (a["outgoing"][0]["trust"], a["incoming"][0]["trust"]) == (10, 20)
    assert (b["outgoing"][0]["trust"], b["incoming"][0]["trust"]) == (20, 10)

    with sqlite3.connect(db_path(world.root)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0] == 1


def test_trust_in_a_non_member_key(world):
    stranger = identity(SigningKey.generate())
    assert world.alice.say(stranger, 7, world.t).status_code == 200
    (edge,) = world.alice.state()["outgoing"]
    assert (edge["subject"], edge["alias"], edge["trust"]) == (stranger, None, 7)


# ---------- what is refused ----------

def test_only_your_own_trust(world):
    message = trust_message(world.bob.identity, world.alice.identity, 5, world.t)
    # a perfectly valid statement by bob, submitted in alice's session
    assert world.alice.post(message, sign(world.bob.key, message)).status_code == 403


def test_bad_signatures_and_garbage(world):
    message = trust_message(world.alice.identity, world.bob.identity, 5, world.t)
    assert world.alice.post(message, sign(world.bob.key, message)).status_code == 400   # wrong signer
    assert world.alice.post(message, "").status_code == 400
    assert world.alice.post("garbage", "00").status_code == 400
    res = world.alice.client.post("/api/trust", data="not json", content_type="text/plain")
    assert res.status_code == 400
    assert world.alice.state()["outgoing"] == []


def test_future_timestamp_refused(world):
    assert world.alice.say(world.bob.identity, 5, now_ms() + 3_600_000).status_code == 400
    assert world.alice.state()["outgoing"] == []


def test_replay_and_stale_timestamps(world):
    message = trust_message(world.alice.identity, world.bob.identity, 10, world.t)
    signature = sign(world.alice.key, message)
    assert world.alice.post(message, signature).status_code == 200
    assert world.alice.post(message, signature).status_code == 409      # same statement again
    assert world.alice.say(world.bob.identity, 12, world.t + 1).status_code == 200
    assert world.alice.post(message, signature).status_code == 409      # an older one, replayed
    assert world.alice.say(world.bob.identity, 14, world.t).status_code == 409   # new value, old timestamp
    assert world.alice.state()["outgoing"][0]["trust"] == 12


def test_unchanged_trust_refused(world):
    assert world.alice.say(world.bob.identity, 10, world.t).status_code == 200
    assert world.alice.say(world.bob.identity, 10, world.t + 1).status_code == 409


def test_withdraw_and_replay_after_withdrawal(world):
    assert world.alice.say(world.bob.identity, None, world.t).status_code == 409        # nothing to withdraw
    assert world.alice.say(world.bob.identity, 10, world.t + 1).status_code == 200
    assert world.alice.say(world.bob.identity, None, world.t + 2).status_code == 200
    assert world.alice.state()["outgoing"] == []
    assert world.alice.say(world.bob.identity, 10, world.t + 1).status_code == 409      # old statement can't return
    assert world.alice.say(world.bob.identity, 10, world.t + 3).status_code == 200      # a fresh one can
    assert world.alice.state()["outgoing"][0]["trust"] == 10
