# file: src/pod/config.py
# description: centralizes everything about the per-drive BITU config file --
# its location, schema (required/optional keys, defaults), and load/save/
# validation logic. Other modules (pod/drives.py, pod/peers.py,
# service/dedupe.py, service/pod/file_server.py, cli/*.py) read AND write config
# through this module rather than touching config.json themselves, so a new
# field only needs to be understood in one place.

from __future__ import annotations

import json
from pathlib import Path

from .paths import BITU_DIR, PERSONAL_CONCEPTS_DIR, pod_root

CONFIG_REL_PATH = Path(PERSONAL_CONCEPTS_DIR) / BITU_DIR / "config.json"  # I\-\bitu\config.json

# Keys a config.json must have to be considered valid enough to opt a drive in.
#   port: int -- the single TCP port this pod's http server listens on. A pod
#         is one node in the mesh and needs exactly one port; there is no
#         per-service port offset scheme.
REQUIRED_KEYS = ("port",)


# Optional keys and their defaults, merged into a valid config after loading.
#   backup: str | None -- the *volume label* of a drive to mirror this drive's
#            <drive>:\I\ folder onto (see service/backup.py). None disables
#            backups for this drive. A label (not a boolean) so different
#            drives can target different backup destinations.
#   peers: list[dict] -- this pod's known peers, each
#            {"alias": str, "socket": "host:port", "public_key": str | None}.
#            Managed through pod.peers, never edited directly.
DEFAULT_VALUES: dict = {
    "backup": None,
    "peers": [],
}


def config_path(drive_root: Path) -> Path:
    """<drive>:\\I\\-\\bitu\\config.json for a given drive root."""
    return drive_root / CONFIG_REL_PATH


def load_drive_config(drive_root: Path) -> dict | None:
    """Load, validate, and apply defaults to a drive's config.json.

    Returns None if the file is missing, unreadable, malformed, or missing a
    required key. That's the intended mechanism for opting a drive out of
    running BITU services -- not an error condition.
    """
    path = config_path(drive_root)
    try:
        if not path.is_file():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # OSError covers unready/removed media (e.g. an empty optical drive);
        # ValueError covers malformed JSON. Both mean "treat as absent".
        return None

    if not isinstance(data, dict):
        return None
    if not all(key in data for key in REQUIRED_KEYS):
        return None

    return {**DEFAULT_VALUES, **data}


def save_drive_config(drive_root: Path, config: dict) -> None:
    """Persist `config` (as returned by load_drive_config, or that shape)
    back to the drive's config.json, creating the bitu directory if needed.

    Optional keys still at their default are omitted from the written file --
    it should only ever record what was actually opted into or changed.
    Required keys are always written. This is the single place anything
    (pod.peers included) writes a drive's config, so there's no parallel
    writer to keep in sync with load_drive_config's schema.
    """
    path = config_path(drive_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    to_write = {
        key: value
        for key, value in config.items()
        if key in REQUIRED_KEYS or DEFAULT_VALUES.get(key, object()) != value
    }
    path.write_text(json.dumps(to_write, indent=2) + "\n", encoding="utf-8")


def pod_config(path: Path) -> dict | None:
    """The BITU config of the pod `path` lives on, or None if that drive
    isn't opted in. Use this to gate behaviour on BITU drives; pod_root()
    itself deliberately doesn't require a config.
    """
    return load_drive_config(pod_root(path))
