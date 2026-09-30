# file: src/lib/bootstrap.py
# description: shared startup plumbing for anything that takes "a pod" as a
# command-line argument -- the per-pod services under service/pod/ (spawned by
# cli/start.py with the pod's root path as their sole argument) and CLI tools
# such as cli/dedupe.py. Keeps "how a pod argument is parsed and validated" in
# exactly one place, so a new server is a few lines instead of a copy of the
# same boilerplate.

from __future__ import annotations

import re
import sys
from pathlib import Path

from .config import load_drive_config
from .paths import pod_root

_BARE_DRIVE = re.compile(r"^[A-Za-z]:?$")


def parse_pod_arg(arg: str) -> Path:
    """A pod given on the command line -> its root.

    Accepts a bare drive letter ("D", "D:") for convenience, or any path on the
    pod: "D:\\" , "D:\\pod_1", even "D:\\pod_1\\I\\-" -- the root is whatever
    volume that path lives on (see pod.paths.pod_root).
    """
    text = arg.strip().strip('"')
    if _BARE_DRIVE.match(text):
        # "D:" alone means "the current directory on D:" to Windows; here it
        # means the drive root.
        return Path(f"{text[0].upper()}:\\")
    return pod_root(Path(text))


def load_pod_or_exit(name: str, argv: list[str] | None = None) -> tuple[Path, dict, int]:
    """Common startup for a per-pod service: parse the pod argument, load its
    config, and return (pod_root, config, port) -- the port being the pod's
    single configured `port`.

    Exits instead of returning if the argument is missing (exit code 1) or the
    pod has no valid config (exit code 0: the pod's config disappeared or
    became invalid between start.py's check and now, e.g. it was unplugged --
    that isn't an error).
    """
    argv = sys.argv if argv is None else argv
    if len(argv) < 2:
        print(f"[{name}] Usage: {Path(argv[0]).name} <pod, e.g. D: or D:\\pod_1>", file=sys.stderr)
        sys.exit(1)

    root = parse_pod_arg(argv[1])
    config = load_drive_config(root)
    if not config:
        print(f"[{name}] No valid config for {root}; exiting.", flush=True)
        sys.exit(0)

    return root, config, config["port"]
