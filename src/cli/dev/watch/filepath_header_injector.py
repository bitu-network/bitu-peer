# file: src/cli/dev/watch/filepath_header_injector.py

import sys
import time
from pathlib import Path

TARGET_EXTENSIONS = {".py", ".js", ".ts", ".html", ".css", ".md"}
EXCLUDE_DIRS = {".git", ".vscode", ".venv", "venv", "__pycache__", "node_modules", "dist", "build"}


def get_comment_syntax(suffix: str, rel_path: str) -> str:
    if suffix in {".py", ".md"}:
        return f"# file: {rel_path}\n"
    elif suffix in {".js", ".ts"}:
        return f"// file: {rel_path}\n"
    elif suffix == ".css":
        return f"/* file: {rel_path} */\n"
    elif suffix == ".html":
        return f"<!-- file: {rel_path} -->\n"
    return f"# file: {rel_path}\n"


def needs_header(file_path: Path, rel_path: str) -> bool:
    try:
        content = file_path.read_text(encoding="utf-8")
        lines = content.splitlines()
        for i in range(min(3, len(lines))):
            if "file:" in lines[i] and rel_path in lines[i]:
                return False
        return True
    except Exception:
        return False


def inject_header(file_path: Path, project_root: Path):
    try:
        rel_path = file_path.relative_to(project_root).as_posix()
        content = file_path.read_text(encoding="utf-8")
        
        prefix = get_comment_syntax(file_path.suffix, rel_path)
        lines = content.splitlines(keepends=True)
        
        header_idx = -1
        for i in range(min(3, len(lines))):
            if "file:" in lines[i]:
                header_idx = i
                break

        if header_idx != -1:
            lines[header_idx] = prefix if lines[header_idx].endswith("\n") else prefix.rstrip("\n") + "\n"
        else:
            lines.insert(0, prefix if prefix.endswith("\n") else prefix + "\n")

        file_path.write_text("".join(lines), encoding="utf-8")
        print(f"[+] Injected/Updated header for: {rel_path}")
    except Exception as e:
        print(f"[!] Error injecting header into {file_path}: {e}")


def watch_directory(root_dir: Path, interval: float = 0.5):
    print(f"[*] Filepath header injector daemon started, monitoring: {root_dir}")
    tracked = {}

    while True:
        try:
            current_paths = set()
            for path in root_dir.rglob("*"):
                if any(part in EXCLUDE_DIRS for part in path.parts):
                    continue
                if path.is_file() and path.suffix in TARGET_EXTENSIONS:
                    current_paths.add(path)
                    try:
                        mtime = path.stat().st_mtime
                        rel_path = path.relative_to(root_dir).as_posix()
                        
                        is_new = path not in tracked
                        is_modified = is_new or (mtime > tracked[path])
                        
                        if is_modified or needs_header(path, rel_path):
                            inject_header(path, root_dir)
                            tracked[path] = path.stat().st_mtime
                        else:
                            tracked[path] = mtime
                    except Exception:
                        pass
                        
            for p in list(tracked.keys()):
                if p not in current_paths:
                    del tracked[p]
                    
            time.sleep(interval)
        except KeyboardInterrupt:
            break


def run(project_root: Path) -> None:
    """Watcher entry point used by cli.dev.watch.__main__ (blocks forever)."""
    watch_directory(project_root)


def main():
    project_root = Path.cwd()
    if "--watch" in sys.argv or len(sys.argv) == 1:
        watch_directory(project_root)
    else:
        for path in project_root.rglob("*"):
            if not any(part in EXCLUDE_DIRS for part in path.parts) and path.suffix in TARGET_EXTENSIONS:
                inject_header(path, project_root)


if __name__ == "__main__":
    main()