# file: src/service/backup.py
# description: global backup mirroring service (not per-drive). Each cycle,
# scans all currently mounted drives for ones whose volume label starts with
# "backup" (case-insensitive). Inside each backup drive, a top-level folder
# named after another drive's volume label is the sole trigger: its mere
# existence (even empty) means "mirror <drive-label>:\I\* here" -- deliberately
# opinionated, since I\ is already this system's one designated "what matters"
# folder, so there's nothing left to declare beyond which drives to back up.
# <backup_drive>\<drive_label>\ maps directly to <drive_label>:\I\*, with no
# repeated "I" segment and no marker files/folders.
#
# Uses robocopy /MIR for the actual transfer -- reliable, built into Windows,
# and handles deletions (files removed from source get removed from the
# mirror) without any hand-rolled diffing logic. After each mirror pass, runs
# the same lib/dedupe_core.full_scan() the dedupe service uses, but against
# the backup drive, so content duplicated across multiple archives' I\
# folders (or hardlinked within one) collapses into the backup drive's own
# CAS tree at <backup_drive>\o\ -- same-drive by the time this runs, so the
# existing hardlink-based dedupe logic (lib/cas.store_new_blob) applies
# unmodified, no cross-drive copy needed at this stage.
#
# No history, no bookkeeping file: every cycle, robocopy's own diff logic
# handles "what changed since last time", and dedupe_core's nlink check means
# a file already linked into the CAS tree by a prior cycle is never re-hashed.
#
# Auto-discovered and launched once globally by cli/start.py (any .py file
# directly under service/ -- as opposed to server/, which is per-drive; see
# server/file_server.py -- is spawned once with no arguments) -- it discovers
# its own targets each cycle, so plugging/unplugging a backup drive or a
# source drive is picked up automatically on the next cycle.

from __future__ import annotations

import subprocess
import time
from pathlib import Path

from lib.cas import cas_root
from lib.dedupe_core import full_scan
from pod.drives import enumerate_drive_roots, find_drive_by_label, get_volume_label

BACKUP_INTERVAL_SECONDS = 15 * 60
ROBOCOPY_TIMEOUT_SECONDS = 60 * 60


def _log(msg: str) -> None:
    print(f"[backup] {msg}", flush=True)


def _find_backup_drives() -> list[Path]:
    result = []
    # Letter-only, on purpose: pods nested inside a disk are mesh-simulation
    # test data -- never backed up, never used as a backup target.
    for root in enumerate_drive_roots(nested=False):
        label = get_volume_label(root)
        if label and label.strip().lower().startswith("backup"):
            result.append(root)
    return result


def _mirror(source_dir: Path, dest_dir: Path) -> bool:
    """Mirror source_dir onto dest_dir via robocopy /MIR (exact mirror,
    including deletions). Returns True on success.

    robocopy exit codes 0-7 all indicate some form of success (0 = nothing to
    copy, 1 = files copied, etc); 8+ indicates a real failure.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    try:
        result = subprocess.run(
            ["robocopy", str(source_dir), str(dest_dir), "/MIR", "/R:2", "/W:2"],
            capture_output=True,
            text=True,
            timeout=ROBOCOPY_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        _log(f"robocopy failed to run: {e}")
        return False

    if result.returncode >= 8:
        _log(f"robocopy reported an error (exit {result.returncode}): {result.stdout[-500:]}")
        return False
    return True


def _run_once() -> None:
    for backup_drive_root in _find_backup_drives():
        cas_dir = cas_root(backup_drive_root)
        cas_dir.mkdir(parents=True, exist_ok=True)

        for drive_label_dir in sorted(p for p in backup_drive_root.iterdir() if p.is_dir()):
            if drive_label_dir == cas_dir:
                continue  # don't treat our own CAS tree as a drive-label folder

            drive_label = drive_label_dir.name
            source_root = find_drive_by_label(drive_label, nested=False)
            if source_root is None:
                _log(f"source drive labeled {drive_label!r} not currently mounted; skipping.")
                continue

            source_dir = source_root / "I"
            if not source_dir.is_dir():
                _log(f"{source_dir} does not exist; nothing to back up for {drive_label!r}.")
                continue

            _log(f"mirroring {source_dir} -> {drive_label_dir} ...")
            if not _mirror(source_dir, drive_label_dir):
                continue
            _log("mirror complete.")

            _log(f"deduping {drive_label_dir} against {cas_dir} ...")
            count = full_scan(backup_drive_root, drive_label_dir, log=_log)
            _log(f"dedupe pass complete ({count} files processed).")


def main():
    _log(f"scanning for backup* drives every {BACKUP_INTERVAL_SECONDS}s.")
    while True:
        try:
            _run_once()
        except Exception as e:
            _log(f"backup cycle error: {e}")
        time.sleep(BACKUP_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
