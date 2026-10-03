# file: src/service/internal_http_server.py


from __future__ import annotations

from web.app import create_app
from project import get_src_root

BIND_HOST = "127.0.0.1"
PORT = 80

WEB_LOCAL_ROOT = get_src_root() / "web" / "internal"


def main():
    print(f"[internal_http_server] {BIND_HOST}:{PORT} serving {WEB_LOCAL_ROOT}", flush=True)
    app = create_app(WEB_LOCAL_ROOT)
    app.run(host=BIND_HOST, port=PORT)


if __name__ == "__main__":
    main()
