# file: src/service/dedupe.py
# description: global content-addressable dedupe service (the "librarian behind
# the scenes"). Unlike file_server.py (per-drive, under service/pod/ -- needs real
# process/socket isolation for network simulation), dedupe has no networking
# concern, so one process manages every opted-in pod: periodically rescans
# for pods with a valid <pod>\I\-\bitu\config.json (see pod/drives.py) -- a
# drive letter or a volume nested in a folder of another volume, e.g.
# D:\pod_1 --, runs a startup/reconciliation scan on any newly seen pod, and
# maintains one watchdog observer schedule per pod for live incremental
# updates -- unscheduling a pod's watch if it's unplugged or its config
# becomes invalid, and picking up newly plugged-in pods on the next check.
#
# Duplicates are replaced with a hardlink to the existing CAS blob
# automatically (lib/dedupe_core.apply_dedupe) -- safe unconditionally, since
# the hash match already confirms the content is byte-for-byte identical.
#
# Auto-discovered and launched once by cli/start.py (any .py file directly
# under service/ is spawned once with no arguments). Use cli/dedupe.py for an
# on-demand manual reconciliation of a specific pod without waiting for
# this service's own periodic checks.

from __future__ import annotations

import os
import time
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer
from watchdog.observers.api import BaseObserver, ObservedWatch

from lib.dedupe_core import process_file, scan_pod, scan_root_for
from pod.drives import find_bitu_drives

DRIVE_RESCAN_INTERVAL_SECONDS = 60


def _log(msg: str) -> None:
    print(f"[dedupe] {msg}", flush=True)


class _NewFileHandler(FileSystemEventHandler):
    def __init__(self, drive_root: Path):
        self.drive_root = drive_root

    def on_created(self, event):
        if event.is_directory:
            return
        process_file(self.drive_root, Path(os.fsdecode(event.src_path)), log=_log)

    def on_moved(self, event):
        # A move/rename introduces a "new" path that also needs indexing.
        if event.is_directory:
            return
        process_file(self.drive_root, Path(os.fsdecode(event.dest_path)), log=_log)


def _start_watching(observer: BaseObserver, drive_root: Path) -> ObservedWatch | None:
    """Run the startup/reconciliation scan for a newly seen pod and register a
    live watch on it. Returns the watchdog watch handle (for later
    unschedule()), or None if there's nothing to watch.
    """
    if scan_pod(drive_root, log=_log) is None:
        _log(f"not watching {drive_root}.")
        return None

    scan_root = scan_root_for(drive_root)
    watch = observer.schedule(_NewFileHandler(drive_root), str(scan_root), recursive=True)
    _log(f"watching {scan_root} for new files.")
    return watch


def main():
    observer = Observer()
    observer.start()

    watched: dict[Path, ObservedWatch] = {}  # pod root (e.g. D:\ or D:\pod_1) -> watchdog watch handle

    _log(f"scanning for BITU pods every {DRIVE_RESCAN_INTERVAL_SECONDS}s.")
    try:
        while True:
            current = {root for root, _config in find_bitu_drives()}

            # Stop watching pods that disappeared or lost a valid config.
            for root in list(watched):
                if root not in current:
                    try:
                        observer.unschedule(watched[root])
                    except Exception as e:  # noqa: BLE001 - a dead drive must not kill the service loop
                        _log(f"unschedule failed for {root}: {e}")
                    del watched[root]
                    _log(f"stopped watching {root} (unplugged or config no longer valid).")

            # Start watching newly seen pods.
            for root in sorted(current, key=str):
                if root not in watched:
                    watch = _start_watching(observer, root)
                    if watch is not None:
                        watched[root] = watch

            time.sleep(DRIVE_RESCAN_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        pass
    finally:
        observer.stop()
        observer.join()


if __name__ == "__main__":
    main()
