# file: src/cli/user/add.py
## bitu user add <pubkey|scheme:pubkey> <alias>
# Authorizes a web member on the pod the current directory is on.

import sys

from pod.users import UserError, add_user, current_pod


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv if argv is None else argv
    if len(argv) != 3:
        print("Usage: bitu user add <pubkey|scheme:pubkey> <alias>", file=sys.stderr)
        return 1

    try:
        scheme, key = add_user(current_pod(), argv[1], argv[2])
    except UserError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    print(f"[added] user '{argv[2]}' ({scheme}:{key[:12]}...)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
