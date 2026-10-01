# file: src/cli/user/list.py
## bitu user list
# Lists the web members of the pod the current directory is on.

import sys

from pod.users import UserError, current_pod, list_users

_HEADERS = ["ALIAS", "IDENTITY"]


def main(argv: list[str] | None = None) -> int:
    try:
        users = list_users(current_pod())
    except UserError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if not users:
        print("[info] No users found.")
        return 0

    rows = [[u["alias"], f"{u['scheme']}:{u['pubkey']}"] for u in users]
    widths = [max(len(r[i]) for r in rows + [_HEADERS]) for i in range(2)]
    print(" | ".join(h.ljust(widths[i]) for i, h in enumerate(_HEADERS)))
    print("-+-".join("-" * w for w in widths))
    for row in rows:
        print(" | ".join(row[i].ljust(widths[i]) for i in range(2)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
