# file: src/web/external/api/trust.py
# description: GET /api/trust -> {identity, outgoing, incoming}: the trust the
# logged-in member has stated in others, and the trust others have stated in
# them. POST /api/trust {message, signature} records one trust statement,
# signed in the member's browser (see lib/edges.py for the message format).
# The server never holds the member's key: it only verifies, and records the
# statement if the signer is the logged-in identity.
#
# Reached only through the gate in lib/http_app.py (session + pod member).
# Errors are returned, not raised -- see the note in verify.py.

import time

from flask import current_app, jsonify, request

from lib.auth import session_identity
from lib.edges import verify_trust
from pod import edges as store

# A timestamp is the replay guard, so one far in the future would lock its own
# edge (nothing older could ever replace it). Allow only a little clock skew.
MAX_CLOCK_SKEW_MS = 10 * 60 * 1000


def handle():
    drive_root = current_app.config.get("BITU_DRIVE_ROOT")
    identity = session_identity(request.cookies.get("bitu_session"))
    if drive_root is None or identity is None:
        return jsonify(error="not authorized"), 401

    if request.method == "GET":
        return jsonify(identity=identity, **store.list_trust(drive_root, identity))
    if request.method != "POST":
        return jsonify(error="GET or POST only"), 405

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        data = {}
    statement = verify_trust(str(data.get("message", "")), str(data.get("signature", "")))
    if statement is None:
        return jsonify(error="not a valid signed trust statement"), 400
    if statement.issuer != identity:
        return jsonify(error="you can only state your own trust"), 403
    if statement.timestamp > time.time() * 1000 + MAX_CLOCK_SKEW_MS:
        return jsonify(error="timestamp is in the future (check your clock)"), 400

    try:
        store.store_trust(
            drive_root,
            statement.issuer,
            statement.subject,
            statement.trust,
            statement.timestamp,
            str(data["message"]),
            str(data["signature"]),
        )
    except store.EdgeStoreError as e:
        return jsonify(error=str(e)), 409
    return jsonify(ok=True)
