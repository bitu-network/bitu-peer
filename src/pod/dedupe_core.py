# file: src/pod/dedupe_core.py
# description: shared "walk a drive and feed files into the CAS tree" logic, used
# by both service/dedupe.py (startup reconciliation + live watchdog handler) and
# cli/dedupe.py (on-demand manual reconciliation). Keeping this here means both
# callers process a file exactly the same way -- there's only one definition of
# what "new content" vs "duplicate" means, and of what happens to a duplicate.

from __future__ import annotations

import os
import time
import uuid
from pathlib import Path
from typing import Callable

from lib.cas import cas_root, find_existing_blob, hash_file, store_new_blob
from pod.paths import BITU_DIR, CONCEPTS_DIR, PERSONAL_CONCEPTS_DIR

DEDUPE_LOG_REL = Path(PERSONAL_CONCEPTS_DIR) / BITU_DIR / "dedupe.log"

LogFn = Callable[[str], None]


def _default_log(msg: str) -> None:
    print(f"[dedupe] {msg}", flush=True)


def _record(drive_root: Path, line: str) -> None:
    log_path = drive_root / DEDUPE_LOG_REL
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def apply_dedupe(drive_root: Path, path: Path, existing_blob: Path, digest: str,
                  log: LogFn = _default_log) -> bool:
    """Replace a genuine duplicate at `path` with a hardlink to the existing CAS
    blob for its content. Safe to do unconditionally: the hash match already
    confirms the two are byte-for-byte identical, so nothing is lost.

    Uses link-into-temp-then-atomic-rename rather than unlink-then-link, so a
    failure partway through never leaves `path` missing -- either the swap
    fully succeeds, or `path` is left exactly as it was.

    Returns True if the swap succeeded.
    """
    tmp_path = path.parent / f".{path.name}.dedupe-{uuid.uuid4().hex[:8]}.tmp"
    try:
        os.link(existing_blob, tmp_path)
        os.replace(tmp_path, path)
        success = True
    except OSError as e:
        success = False
        log(f"dedupe swap failed for {path}: {e}")
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass

    outcome = "replaced" if success else "failed"
    _record(drive_root, f"{time.time()}\t{outcome}\t{digest}\t{path}\t{existing_blob}")
    if success:
        log(f"duplicate replaced with hardlink: {path} -> {existing_blob}")
    return success


def process_file(drive_root: Path, path: Path, log: LogFn = _default_log) -> None:
    """Index a single file: skip if it's already a known hardlink, otherwise
    hash it and either store it as a new blob or automatically dedupe it
    against an existing one.
    """
    try:
        st = path.stat()
    except OSError:
        return  # file may have already been moved/deleted

    if st.st_nlink > 1:
        # Already a hardlink to something known (our own store_new_blob() call,
        # or one the user made on purpose) -- nothing new to index.
        return

    digest = hash_file(path)
    if digest is None:
        return

    existing_blob = find_existing_blob(drive_root, digest)
    if existing_blob is None:
        try:
            store_new_blob(drive_root, digest, path)
            log(f"stored new blob {digest} <- {path}")
            return
        except FileExistsError:
            # Race: another process stored this exact hash between our check
            # and now. Fall through and treat it as a duplicate below.
            existing_blob = find_existing_blob(drive_root, digest)

    if existing_blob is not None:
        apply_dedupe(drive_root, path, existing_blob, digest, log=log)


def full_scan(drive_root: Path, scan_root: Path, log: LogFn = _default_log) -> int:
    """Walk scan_root and process_file() every file found. Cheap for files
    already indexed (nlink check short-circuits before any hashing).
    Returns the number of files processed.
    """
    cas_dir = cas_root(drive_root)
    count = 0
    for root, _dirs, files in os.walk(scan_root):
        root_path = Path(root)
        # Don't index our own CAS tree if it's nested under the scan root.
        if root_path == cas_dir or cas_dir in root_path.parents:
            continue
        for name in files:
            process_file(drive_root, root_path / name, log=log)
            count += 1
    return count


def scan_root_for(drive_root: Path) -> Path:
    """<pod>\\-\\ -- the tree whose files get indexed into the pod's CAS."""
    return drive_root / CONCEPTS_DIR


def scan_pod(drive_root: Path, log: LogFn = _default_log) -> int | None:
    """Reconcile one pod: make sure its CAS root exists, then full_scan() its
    scan root. Shared by service/dedupe.py (at startup, before it starts
    watching) and cli/dedupe.py (on demand).

    Returns the number of files processed, or None if the pod has no scan root
    (nothing to index -- and nothing for a watcher to watch).
    """
    scan_root = scan_root_for(drive_root)
    if not scan_root.is_dir():
        log(f"scan root {scan_root} does not exist; skipping {drive_root}.")
        return None

    cas_root(drive_root).mkdir(parents=True, exist_ok=True)

    log(f"scanning {scan_root} ...")
    count = full_scan(drive_root, scan_root, log=log)
    log(f"scan of {drive_root} complete ({count} files processed).")
    return count
