# file: src/tray/restart.py
import os
import sys
import subprocess
from pathlib import Path

def main():
    tray_dir = Path(__file__).parent
    main_script = tray_dir / "main.py"
    src_dir = tray_dir.parent
    project_root = src_dir.parent

    # Terminate any existing tray instances to avoid duplicate icons
    if os.name == 'nt':
        try:
            subprocess.run(
                ["powershell", "-Command", f"Get-WmiObject Win32_Process | Where-Object {{ $_.CommandLine -like '*{main_script.name}*' -and $_.ProcessId -ne {os.getpid()} }} | ForEach-Object {{ $_.Terminate() }}"],
                capture_output=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
        except Exception:
            pass

    # Launch a fresh instance of the tray hub
    env = os.environ.copy()
    env["PYTHONPATH"] = str(src_dir)
    subprocess.Popen(
        [sys.executable, str(main_script)],
        cwd=str(project_root),
        env=env,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    )

if __name__ == "__main__":
    main()