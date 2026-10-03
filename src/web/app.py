# file: src/web/app.py


from __future__ import annotations

import importlib.util
from pathlib import Path

from flask import Flask, abort, jsonify, redirect, request, send_from_directory

from web.session import session_identity
from pod.users import is_member
from project import get_src_root

ASSETS_ROOT = get_src_root() / "http" / "assets"

# Reachable without a session when the gate is on (i.e. when drive_root is given).
# /assets/ is allowed as a prefix in the gate below.
_PUBLIC_PATHS = {
    "/login", "/login.html", "/style.css", "/favicon.ico",
    "/api/challenge", "/api/verify", "/api/contact",
}


def create_app(
    target_dir: Path,
    drive_root: Path | None = None,
    contact_email: str | None = None,
) -> Flask:
    """With drive_root, every route except the public ones requires a session
    whose identity is a member of that pod (see pod/users.py). Without it
    (e.g. the internal server) there is no gate."""
    app = Flask(__name__)
    app.config["BITU_DRIVE_ROOT"] = drive_root
    app.config["BITU_CONTACT_EMAIL"] = contact_email or ""

    @app.before_request
    def gate():
        if drive_root is None:
            return None
        path = request.path
        if path in _PUBLIC_PATHS or path.startswith("/assets/"):
            return None
        identity = session_identity(request.cookies.get("bitu_session"))
        if identity and is_member(drive_root, identity):
            return None
        if path.startswith("/api/"):
            return jsonify(error="not authorized"), 401
        return redirect("/login")

    # Shared static assets (CSS, JS, fonts) -- same for every server instance.
    @app.route("/assets/<path:filename>")
    def serve_assets(filename: str):
        asset_path = ASSETS_ROOT / filename
        if asset_path.is_file():
            return send_from_directory(ASSETS_ROOT, filename)
        abort(404)

    @app.route("/favicon.ico")
    def serve_favicon():
        favicon_path = ASSETS_ROOT / "favicon" / "favicon.ico"
        if favicon_path.is_file():
            return send_from_directory(favicon_path.parent, favicon_path.name)
        abort(404)

    @app.route("/", defaults={"req_path": ""}, methods=["GET", "POST"])
    @app.route("/<path:req_path>", methods=["GET", "POST"])
    def serve(req_path: str):
        target_path = target_dir / req_path

        if not request.path.endswith("/") and target_path.is_dir():
            return redirect(request.path + "/")

        # 0. Direct Python file execution (e.g., api.py)
        if target_path.is_file() and target_path.suffix == ".py":
            return _execute_python_handler(target_path)

        # 1. Exact static file match (e.g., /about.html, /index.js)
        if target_path.is_file():
            return send_from_directory(target_path.parent, target_path.name)

        # 2. Directory index.py match (prioritized dynamic page generator)
        index_py_path = target_path / "index.py"
        if index_py_path.is_file():
            return _execute_python_handler(index_py_path)

        # 3. Directory index.html match (static layout fallback)
        index_path = target_path / "index.html"
        if index_path.is_file():
            return send_from_directory(index_path.parent, index_path.name)

        # 4. Extension-less Python handler fallback (e.g., /foo/api -> /foo/api.py)
        py_path = target_dir / f"{req_path}.py"
        if py_path.is_file():
            return _execute_python_handler(py_path)

        # 5. Extension-less HTML file fallback (e.g., /about -> /about.html)
        html_path = target_dir / f"{req_path}.html"
        if html_path.is_file():
            return send_from_directory(html_path.parent, html_path.name)

        abort(404)

    def _execute_python_handler(py_path: Path):
        """Safely load and execute a dynamic python handler module."""
        try:
            spec = importlib.util.spec_from_file_location("dynamic_route", py_path)
            if spec is not None and spec.loader is not None:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                if hasattr(mod, "handle"):
                    return mod.handle()
                elif hasattr(mod, "main"):
                    return mod.main()
                else:
                    abort(500, description="Handler module missing handle() or main()")
            else:
                abort(500, description="Could not load dynamic module specification")
        except Exception as e:
            abort(500, description=str(e))

    return app
