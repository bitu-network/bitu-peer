# file: src/menu/foo_pretend_to_encrypt.py
import sys
import time

selected_files = sys.argv[1:]
print("Encrypting... or maybe not 😏")
for f in selected_files:
    print(f"  Pretending to encrypt: {f}")
    time.sleep(0.3)
print("All done! Totally secure. Or not.")
