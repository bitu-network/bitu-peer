# file: src/http/external/api/verify.py
# description: POST /api/verify {nonce, public_key, signature}. On a valid
# signature it sets the bitu_session cookie and answers {identity, member}.
# A valid signature from a non-member still gets a session, but the gate in
# lib/http_app.py keeps it out of everything except the login page.
#
# Note: return error responses instead of calling abort() here --
# http_app._execute_python_handler turns any exception (abort included) into a 500.

from flask import current_app, jsonify, request

from lib.auth import SESSION_TTL, new_session, verify_login
from pod.users import is_member


def handle():
    if request.method != "POST":
        return jsonify(error="POST only"), 405

    data = request.get_json(silent=True) or {}
    identity = verify_login(
        request.host,
        str(data.get("nonce", "")),
        str(data.get("public_key", "")),
        str(data.get("signature", "")),
    )
    if identity is None:
        return jsonify(error="invalid signature or expired challenge"), 401

    drive_root = current_app.config.get("BITU_DRIVE_ROOT")
    member = drive_root is not None and is_member(drive_root, identity)

    resp = jsonify(identity=identity, member=member)
    # Behind the cloudflare tunnel the request reaches Flask as plain http,
    # so trust the forwarded scheme when deciding on the Secure flag.
    https = request.headers.get("X-Forwarded-Proto", request.scheme) == "https"
    resp.set_cookie(
        "bitu_session",
        new_session(identity),
        max_age=SESSION_TTL,
        httponly=True,
        samesite="Lax",
        secure=https,
    )
    return resp
