# file: src/service/pod/external_http_server.py


from __future__ import annotations

from lib.http_app import create_app
from pod.bootstrap import load_pod_or_exit
from project import get_src_root

WEB_PUBLIC_ROOT = get_src_root() / "http" / "external"


def main():
    drive_root, _config, port = load_pod_or_exit("http_server")
    print(f"[http_server] {drive_root} -> 127.0.0.1:{port} serving {WEB_PUBLIC_ROOT}", flush=True)

    app = create_app(WEB_PUBLIC_ROOT)
    app.run(host="127.0.0.1", port=port)


if __name__ == "__main__":
    main()
