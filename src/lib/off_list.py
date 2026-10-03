# file: src/lib/off_list.py
# description: shared "drop a .py file in a folder and it runs" discovery used
# by cli/start.py (services) and cli/dev/watch/__main__.py (dev watchers).
#
# A file is skipped if its name starts with "_" (helper modules, not meant to
# be run directly), if it's not directly a .py file, or if its name (with or
# without ".py") is listed in an "off.txt" in the same folder. off.txt is
# gitignored and per-machine: one name per line, "#" starts a comment. It's a
# denylist, so a newly dropped .py file still starts automatically. It is read
# once at startup, so edits take effect on the next restart.

from __future__ import annotations

from pathlib import Path


def read_off_list(folder: Path) -> set[str]:
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


def discover_scripts(folder: Path) -> list[Path]:
    """Sorted .py files directly in `folder` that should be started."""
    if not folder.is_dir():
        return []
    off = read_off_list(folder)
    skipped = sorted(p.name for p in folder.glob("*.py") if p.stem in off)
    for name in skipped:
        print(f"[-] Skipping {folder.parent.name}/{folder.name}/{name} (listed in off.txt)", flush=True)
    return sorted(
        p for p in folder.glob("*.py")
        if p.is_file() and not p.name.startswith("_") and p.stem not in off
    )
