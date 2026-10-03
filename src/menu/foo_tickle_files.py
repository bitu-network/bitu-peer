# file: src/menu/foo_tickle_files.py
import sys

selected_files = sys.argv[1:]
print("Tickling your files until they giggle!")
for f in selected_files:
    print(f"  {f} has been tickled 😂")
