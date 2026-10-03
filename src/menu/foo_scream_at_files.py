# file: src/menu/foo_scream_at_files.py
import sys

selected_files = sys.argv[1:]
print("AAAAAAAAA!!! Files, listen to me!!!")
for f in selected_files:
    print(f"  {f} is now being yelled at!!!")
