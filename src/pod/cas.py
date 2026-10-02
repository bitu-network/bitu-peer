# file: src/pod/cas.py
# description: shared content-addressable-storage (CAS) logic for BITU's per-drive
# hash blob tree at <drive>:\o\<byte1>\<byte2>\<full-hash>\content.<ext>.
#
# Used by service/dedupe.py (the live indexer/hardlinker), service/pod/file_server.py
# (the network-facing reader), and any future one-off verify/fsck command, so the
# "how do we lay out and validate a blob" logic lives in exactly one place.

from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path

from pod.paths import BLOBS_DIR

CAS_ROOT_REL = Path(BLOBS_DIR)  # <drive>:\o\
HASH_CHUNK_SIZE = 1024 * 1024


def cas_root(drive_root: Path) -> Path:
    """<drive>:\\o\\ -- the root of this drive's content-addressable blob tree."""
    return drive_root / CAS_ROOT_REL


def hash_file(path: Path) -> str | None:
    """SHA-256 hex digest of a file's contents, or None if it can't be read."""
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(HASH_CHUNK_SIZE), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def blob_dir_for_hash(drive_root: Path, digest: str) -> Path:
    """<drive>:\\o\\<byte1>\\<byte2>\\<full-hash>\\ for a given hex digest."""
    return cas_root(drive_root) / digest[0:2] / digest[2:4] / digest


def find_existing_blob(drive_root: Path, digest: str) -> Path | None:
    """Return the existing blob's content file (content.<ext>) for this hash,
    or None if this hash isn't stored on this drive yet."""
    blob_dir = blob_dir_for_hash(drive_root, digest)
    if not blob_dir.is_dir():
        return None
    for child in blob_dir.iterdir():
        if child.is_file() and child.stem == "content":
            return child
    return None


def store_new_blob(drive_root: Path, digest: str, source_path: Path) -> Path:
    """Hardlink source_path into the CAS tree as a new blob for this hash.

    Raises FileExistsError if a blob for this hash already exists. Callers
    should check find_existing_blob() first as the common case, but must still
    handle this exception for the race where two processes store the same new
    hash at nearly the same time -- os.link() itself is the atomic check.
    """
    blob_dir = blob_dir_for_hash(drive_root, digest)
    blob_dir.mkdir(parents=True, exist_ok=True)
    ext = source_path.suffix  # includes leading '.', or '' if the file has none
    dest = blob_dir / f"content{ext}"
    os.link(source_path, dest)
    return dest


def copy_new_blob(drive_root: Path, digest: str, source_path: Path) -> Path:
    """Copy source_path's bytes into the CAS tree as a new blob for this hash.

    Use this instead of store_new_blob() when source_path lives on a
    different volume than drive_root -- hardlinks can't span volumes, so this
    performs an actual byte copy instead. Otherwise behaves the same:
    raises FileExistsError if a blob for this hash already exists.
    """
    blob_dir = blob_dir_for_hash(drive_root, digest)
    blob_dir.mkdir(parents=True, exist_ok=True)
    ext = source_path.suffix
    dest = blob_dir / f"content{ext}"
    if dest.exists():
        raise FileExistsError(dest)
    shutil.copyfile(source_path, dest)
    return dest


def verify_blob(blob_path: Path) -> bool:
    """Recompute a stored blob's hash and confirm it matches the hash directory
    it's stored under. Used by a future fsck-style command, not by the live
    dedupe path (which never needs to re-verify a blob it just wrote).
    """
    expected_digest = blob_path.parent.name
    actual_digest = hash_file(blob_path)
    return actual_digest == expected_digest
