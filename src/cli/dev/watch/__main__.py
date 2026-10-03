# file: src/cli/dev/watch/__main__.py
# description: dev watch daemon, started by .vscode/tasks.json as
# `python -m cli.dev.watch`. Auto-discovers every watcher module directly in
# this folder and runs each in its own daemon thread. Adding a watcher means
# dropping a .py file here that exposes `run(project_root: Path) -> None`
# (blocking, runs forever); this file never needs to change for that.
#
# Same convention as cli/start.py (see lib/off_list.py): a file is skipped if
# its name starts with "_" or is listed in an "off.txt" in this folder
# (gitignored, per-machine, one name per line, "#" comments). Prefix a
# half-finished watcher with "_" while developing it. off.txt is read once at
# startup, so edits take effect on the next restart.
#
# One watcher crashing (or failing to import) is reported and does not stop
# the others. The process exits only when every watcher has stopped.

from __future__ import annotations

import importlib
import sys
import threading
import time
from pathlib import Path

from lib.off_list import discover_scripts
from project import get_project_root

PACKAGE = "cli.dev.watch"


def _guarded(name: str, run, project_root: Path) -> None:
    try:
        run(project_root)
    except Exception as e:
        print(f"[!] Watcher '{name}' crashed: {e!r}", file=sys.stderr, flush=True)


def main() -> None:
    project_root = get_project_root()
    threads: list[threading.Thread] = []

    for script in discover_scripts(Path(__file__).resolve().parent):
        name = script.stem
        try:
            module = importlib.import_module(f"{PACKAGE}.{name}")
        except Exception as e:
            print(f"[!] Could not import watcher '{name}': {e!r}", file=sys.stderr, flush=True)
            continue
        run = getattr(module, "run", None)
        if not callable(run):
            print(f"[!] Skipping '{name}': it has no run(project_root) function "
                  f"(prefix it with '_' if it is a helper module)", file=sys.stderr, flush=True)
            continue
        thread = threading.Thread(target=_guarded, args=(name, run, project_root),
                                  name=f"watch:{name}", daemon=True)
        thread.start()
        threads.append(thread)
        print(f"[+] Started watcher: {name}", flush=True)

    if not threads:
        print("[!] No watchers to run.", file=sys.stderr, flush=True)
        return

    try:
        while any(t.is_alive() for t in threads):
            time.sleep(1)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
