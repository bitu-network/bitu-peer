# file: src/web/external/api/contact.py
# description: GET /api/contact -> {email}. Public (allowlisted in the gate):
# it is the pod owner's contact address for membership requests, so use a
# dedicated address -- anyone with the pod's URL can read it.

from flask import current_app, jsonify


def handle():
    return jsonify(email=current_app.config.get("BITU_CONTACT_EMAIL", ""))
