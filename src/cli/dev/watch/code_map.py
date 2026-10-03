# file: src/cli/dev/watch/code_map.py
# description: keeps docs/PROJECT_MAP.js up to date -- a single file holding a
# JSON map of every tracked file, what each one imports (and who imports it),
# and the signatures of its functions/classes without their bodies, so the
# project's structure and wiring can be read at once by an LLM or loaded
# directly by docs/PROJECT_MAP.html. Replaces tree_snapshot.py (the folder tree
# is just the "files" keys split on "/").
#
# Why .js and not .json: a page opened straight from disk (file://) cannot
# fetch() a sibling .json, but it can load a sibling <script src>. So the one
# generated file is the JSON assigned to `window.PROJECT_MAP`, laid out as
#     line 1:        window.PROJECT_MAP =
#     lines 2..n-1:  the JSON document, verbatim
#     last line:     ;
# i.e. the JSON is exactly the lines in between -- a script that wants plain
# JSON drops the first and last line, no JS evaluation needed. (A one-shot run
# to any other suffix, or to stdout, writes the plain JSON.)
#
# All the analysis lives in lib/project_graph.py; this module is only the
# poll loop. Like the other watchers it polls instead of using filesystem
# events (simple, dependency-free) and only rewrites the output when its
# content actually changed. Unchanged files are not re-parsed (mtime cache).
#
# Started automatically by cli.dev.watch.__main__ via run(); also usable
# standalone: `python -m cli.dev.watch.code_map [--out FILE] [--watch] [--private] [--detail]`.

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from lib.project_graph import build_map, dumps
from project import get_project_root

DEFAULT_OUT_DIR = "docs"
DEFAULT_OUT_NAME = "PROJECT_MAP.js"
DEFAULT_INTERVAL = 2.0  # seconds between polls


def _serialize(document: str, out_path: Path) -> str:
    """The JSON document as the file content: wrapped for .js, raw otherwise."""
    if out_path.suffix == ".js":
        return f"window.PROJECT_MAP =\n{document.rstrip()}\n;\n"
    return document


def _render(project_root: Path, out_path: Path, cache: dict, include_private: bool, detail: bool) -> str:
    try:
        exclude = {out_path.relative_to(project_root).as_posix()}
    except ValueError:
        exclude = set()
    return dumps(build_map(project_root, cache, include_private, exclude, detail))


def run(project_root: Path, out_path: Path | None = None,
        interval: float = DEFAULT_INTERVAL, include_private: bool = False,
        detail: bool = False) -> None:
    """Watcher entry point: regenerate the map every `interval` seconds,
    forever. Blocks; cli.dev.watch.__main__ runs it in a daemon thread."""
    out_path = out_path or (project_root / DEFAULT_OUT_DIR / DEFAULT_OUT_NAME)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"[*] Code map daemon started, writing to: {out_path}", flush=True)
    cache: dict = {}
    last_output = None
    while True:
        try:
            output = _render(project_root, out_path, cache, include_private, detail)
            if output != last_output:
                out_path.write_text(_serialize(output, out_path), encoding="utf-8")
                print(f"[+] Updated {out_path.name}", flush=True)
                last_output = output
        except Exception as e:
            print(f"[!] Error updating code map: {e}", file=sys.stderr, flush=True)
        time.sleep(interval)


def main() -> None:
    parser = argparse.ArgumentParser(description="Map the project's files, imports and signatures as JSON.")
    parser.add_argument("--out", type=Path, default=None, help="Write to this file instead of stdout.")
    parser.add_argument("--watch", action="store_true",
                        help="Keep running and update the file continuously (default file: docs/PROJECT_MAP.js).")
    parser.add_argument("--private", action="store_true", help="Include private (_underscore) symbols.")
    parser.add_argument("--detail", action="store_true",
                        help="Also emit structured params/returns/bases (redundant with sig).")
    args = parser.parse_args()

    project_root = get_project_root()
    if args.watch:
        run(project_root, args.out, include_private=args.private, detail=args.detail)
        return

    out_path = args.out or (project_root / DEFAULT_OUT_DIR / DEFAULT_OUT_NAME)  # excluded from the map
    output = _render(project_root, out_path, {}, args.private, args.detail)
    if args.out:
        args.out.write_text(_serialize(output, args.out), encoding="utf-8")
        print(f"[+] Wrote code map to {args.out}", file=sys.stderr)
    else:
        sys.stdout.write(output)


if __name__ == "__main__":
    main()
