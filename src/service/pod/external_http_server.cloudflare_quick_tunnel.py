# file: src/service/pod/external_http_server.cloudflare_quick_tunnel.py
# description: per-pod sibling of external_http_server.py. Runs a Cloudflare
# quick tunnel (no account, no domain) that exposes the pod's http server at a
# random https://<words>.trycloudflare.com URL, which changes on every run.
# The URL is printed to the console as soon as cloudflared announces it, and,
# when started by cli/start.py (BITU_URL_DIR is set), also written to
# "<pod>.url" in that folder so start.py can list every pod's URL in one block.

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from pod.bootstrap import load_pod_or_exit

_URL = re.compile(r"https://(?!api\.)[a-z0-9-]+\.trycloudflare\.com")


def _enable_ansi() -> bool:
    """True if stdout is a terminal that can show colors/hyperlinks."""
    if not sys.stdout.isatty():
        return False
    if os.name == "nt":
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_uint()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        # ENABLE_VIRTUAL_TERMINAL_PROCESSING
        return bool(kernel32.SetConsoleMode(handle, mode.value | 0x0004))
    return True


_ANSI = _enable_ansi()


def _link(url: str) -> str:
    if not _ANSI:
        return url  # redirected to a file/pipe: keep the log clean
    # OSC 8 hyperlink + bold, underlined, bright cyan
    return f"\x1b]8;;{url}\x1b\\\x1b[1;4;96m{url}\x1b[0m\x1b]8;;\x1b\\"


def _publish_url(drive_root: Path, url: str) -> None:
    """Hand the URL to cli/start.py, if it started us."""
    url_dir = os.environ.get("BITU_URL_DIR")
    if not url_dir:
        return
    name = re.sub(r"[^A-Za-z0-9]+", "_", str(drive_root)).strip("_")  # C:\ -> C, D:\pod_1 -> D_pod_1
    try:
        (Path(url_dir) / f"{name}.url").write_text(url, encoding="utf-8")
    except OSError:
        pass  # the summary is a convenience; never fail the tunnel over it


def main():
    drive_root, _config, port = load_pod_or_exit("cloudflare_quick_tunnel")

    exe = shutil.which("cloudflared")
    if not exe:
        print("[cloudflare_quick_tunnel] cloudflared not found on PATH.", file=sys.stderr, flush=True)
        sys.exit(1)

    target = f"http://127.0.0.1:{port}"
    print(f"[cloudflare_quick_tunnel] {drive_root} -> starting tunnel to {target}", flush=True)

    # cloudflared logs to stderr, and that's where it announces the URL.
    proc = subprocess.Popen(
        [exe, "tunnel", "--no-autoupdate", "--url", target],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )

    announced = False
    try:
        for line in proc.stderr:
            match = _URL.search(line)
            if match and not announced:
                announced = True
                url = match.group(0)
                print(f"[cloudflare_quick_tunnel] {drive_root} PUBLIC URL: {_link(url)}", flush=True)
                _publish_url(drive_root, url)
            elif not announced or "ERR" in line:
                # Show startup chatter until the URL appears, and any errors after it.
                print(f"[cloudflare_quick_tunnel] {line.rstrip()}", flush=True)
        sys.exit(proc.wait())
    except KeyboardInterrupt:
        pass
    finally:
        if proc.poll() is None:
            proc.terminate()


if __name__ == "__main__":
    main()
