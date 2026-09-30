# file: src/cli/start.py
# description: master startup routine. Auto-discovers and launches every
# service under src/service/ (global services, spawned once with no
# arguments -- e.g. hotkey_engine.py, backup.py, dedupe.py: none of these
# need per-drive process isolation) and src/server/ (per-drive services,
# spawned once per pod found by pod/drives.find_bitu_drives() -- a drive or a
# volume nested inside one, e.g. D:\pod_1 -- with that pod's root path as the
# sole argument, e.g. external_http_server.py, which
# needs real process/socket isolation per drive for the mesh-network
# simulation and sensitive-data isolation goals). Adding a new service means
# dropping a .py file in the right folder; this file never needs to change
# for that.
#
# A file is skipped if its name starts with "_" (helper modules, not meant to
# be run directly), if it's not directly a .py file, or if its name (with or
# without ".py") is listed in an "off.txt" in the same folder. off.txt is
# gitignored and per-machine: one name per line, "#" starts a comment. It's a
# denylist, so a newly dropped .py file still starts automatically. It is read
# once at startup, so edits take effect on the next restart.
#
# A drive with no valid <drive>:\I\-\bitu\config.json (see lib/drives.py)
# gets none of the per-drive (server/) services -- that's the intended way to
# opt a drive in/out, no separate GUI/TUI toggle needed.
#
# Public URLs: a service that publishes a pod (e.g. the cloudflare quick
# tunnel) can write its URL to "<name>.url" inside the folder named by the
# BITU_URL_DIR environment variable (%TEMP%\bitu_urls: emptied at every start
# and removed on clean shutdown, so nothing accumulates). While running, this
# file polls that folder and prints a summary block whenever a URL appears or
# changes.

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from lib.ensures_single_instance import ensure_single_instance
from pod.drives import find_bitu_drives
from project import get_project_root, get_src_root


def _read_off_list(folder: Path) -> set[str]:
    """Names listed in <folder>/off.txt (gitignored, per-machine denylist)."""
    off_file = folder / "off.txt"
    if not off_file.is_file():
        return set()
    names = set()
    for line in off_file.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            names.add(line.removesuffix(".py"))
    return names


def _discover_services(folder: Path) -> list[Path]:
    if not folder.is_dir():
        return []
    off = _read_off_list(folder)
    skipped = sorted(p.name for p in folder.glob("*.py") if p.stem in off)
    for name in skipped:
        print(f"[-] Skipping {folder.name}/{name} (listed in off.txt)", flush=True)
    return sorted(
        p for p in folder.glob("*.py")
        if p.is_file() and not p.name.startswith("_") and p.stem not in off
    )


def _poll_urls(url_dir: Path, urls: dict[str, str]) -> bool:
    """Merge any new/changed "<name>.url" files into `urls`. True if changed."""
    changed = False
    for f in sorted(url_dir.glob("*.url")):
        try:
            url = f.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if url and urls.get(f.stem) != url:
            urls[f.stem] = url
            changed = True
    return changed


def _print_urls(urls: dict[str, str]) -> None:
    print("\n=== PUBLIC URLS ===", flush=True)
    for name, url in sorted(urls.items()):
        print(f"  {name:<10} {url}", flush=True)
    print("===================\n", flush=True)


def main():
    project_root = get_project_root()
    src_dir = get_src_root()

    if not ensure_single_instance("bitu_main_runner"):
        print("[!] Bitu is already running.", flush=True)
        sys.exit(0)

    # Fixed location, emptied on every start: no leftovers accumulate, and
    # ensure_single_instance above guarantees no other run is using it.
    url_dir = Path(tempfile.gettempdir()) / "bitu_urls"
    shutil.rmtree(url_dir, ignore_errors=True)
    url_dir.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["PYTHONPATH"] = str(src_dir)
    env["PYTHONUNBUFFERED"] = "1"
    env["BITU_URL_DIR"] = str(url_dir)

    global_scripts = _discover_services(src_dir / "service")
    drive_scripts = _discover_services(src_dir / "server")

    print("=== Launching BITU Background Services (Console Output Active) ===", flush=True)
    procs: list[subprocess.Popen] = []

    try:
        for script in global_scripts:
            print(f"[+] Starting global service: {script.name}", flush=True)
            proc = subprocess.Popen(
                [sys.executable, str(script)],
                cwd=str(project_root),
                env=env,
                stdout=None,
                stderr=None,
            )
            procs.append(proc)

        drives = find_bitu_drives()
        if drives:
            print(f"[+] Found {len(drives)} drive(s) with a BITU config:", flush=True)
        for drive_root, config in drives:
            print(f"    {drive_root} -> port {config.get('port')}", flush=True)
            for script in drive_scripts:
                print(f"    [+] Starting {script.name} for {drive_root}", flush=True)
                proc = subprocess.Popen(
                    [sys.executable, str(script), str(drive_root)],
                    cwd=str(project_root),
                    env=env,
                    stdout=None,
                    stderr=None,
                )
                procs.append(proc)

        urls: dict[str, str] = {}
        while True:
            time.sleep(1)
            if _poll_urls(url_dir, urls):
                _print_urls(urls)
    except KeyboardInterrupt:
        print("\n[!] Terminal closed or interrupted. Shutting down services...", flush=True)
    except Exception as e:
        print(f"[ERROR] Engine orchestration failure: {e}", file=sys.stderr, flush=True)
        sys.exit(1)
    finally:
        for proc in procs:
            if proc and proc.poll() is None:
                proc.terminate()
        shutil.rmtree(url_dir, ignore_errors=True)
        print("[+] All services terminated cleanly.", flush=True)


if __name__ == "__main__":
    main()
