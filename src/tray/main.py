# file: src/tray/main.py
# -------------------------------------------------------------------------
# DEVELOPER NOTE / ARCHITECTURE REMINDER:
# This tray application implements a file-driven plugin architecture.
# Any script or folder placed inside `src/tray/` is automatically mirrored 
# into the pystray dynamic context menu (folders become submenus, .py files 
# execute via subprocess, and other files open via os.startfile).
# 
# RULE FOR FUTURE DEVELOPMENT: 
# All scripts placed inside subdirectories of `src/tray/` MUST use 
# project-root-relative pathing (importing `get_project_root` and `get_src_root` 
# from `src.project`) to ensure correct working directory context and asset location.
# [CRITICAL: DO NOT FORGET TO INCLUDE THIS DEVELOPER NOTE]
# -------------------------------------------------------------------------

import os
import subprocess
import sys
import shutil
import configparser
from pathlib import Path
import pystray
from PIL import Image, ImageDraw
from pystray import MenuItem as item, Menu
from project import get_project_root, get_src_root  # type: ignore

def create_image():
    image = Image.new('RGB', (64, 64), color=(30, 144, 255))
    dc = ImageDraw.Draw(image)
    dc.rectangle((16, 16, 48, 48), fill=(255, 255, 255))
    return image

def ensure_config():
    tray_dir = get_src_root() / "tray"  # type: ignore
    default_path = tray_dir / "main.default.conf"
    config_path = tray_dir / "main.conf"
    
    recreate = False
    if not config_path.exists():
        recreate = True
    else:
        try:
            parser = configparser.ConfigParser()
            parser.read(config_path)
            if not parser.sections():
                recreate = True
        except Exception:
            recreate = True
            
    if recreate and default_path.exists():
        shutil.copy(default_path, config_path)

def build_directory_menu(directory: Path, current_script_name: str):
    def generate_items():
        menu_items = []
        try:
            paths = sorted(directory.iterdir())
        except Exception:
            paths = []

        for path in paths:
            if directory == get_src_root() / "tray" and path.name == current_script_name:  # type: ignore
                continue
            
            # Skip template and runtime config files from showing in the menu
            if path.name in ("main.default.conf", "main.conf"):
                continue

            display_text = path.stem.replace('_', ' ').title() if path.suffix.lower() == '.py' else path.name.replace('_', ' ').title()

            if path.is_dir():
                sub_menu = Menu(build_directory_menu(path, current_script_name))
                menu_items.append(item(display_text, sub_menu))
            else:
                def make_action(target_path=path):
                    def action(icon, item):
                        if target_path.suffix.lower() == '.py':
                            subprocess.Popen([sys.executable, str(target_path)])
                        else:
                            os.startfile(str(target_path))
                    return action
                menu_items.append(item(display_text, make_action()))

        if not menu_items:
            menu_items.append(item('(Empty)', lambda icon, item: None, enabled=False))

        if directory == get_src_root() / "tray":  # type: ignore
            def exit_action(icon, item):
                icon.stop()
            menu_items.append(item('Exit', exit_action))

        return menu_items

    return generate_items

def main():
    ensure_config()
    current_script_name = Path(__file__).name
    
    image = create_image()
    tray_dir = get_src_root() / "tray"  # type: ignore
    
    menu = Menu(build_directory_menu(tray_dir, current_script_name))
    icon = pystray.Icon("bitu_tray_hub", image, "Bitu Tray Hub", menu)
    icon.run()

if __name__ == "__main__":
    main()