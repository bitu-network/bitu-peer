# file: src/web/external/api/challenge.py
# description: GET /api/challenge -> {nonce, message}. The client signs `message`.

from flask import jsonify, request

from lib.auth import new_challenge


def handle():
    nonce, message = new_challenge(request.host)
    return jsonify(nonce=nonce, message=message)
