# file: src/cli/user/remove.py
## bitu user remove <alias|pubkey>
# Revokes a web member on the pod the current directory is on.

import sys

from pod.users import UserError, current_pod, remove_user


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv if argv is None else argv
    if len(argv) != 2:
        print("Usage: bitu user remove <alias|pubkey>", file=sys.stderr)
        return 1

    try:
        remove_user(current_pod(), argv[1])
    except UserError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    print(f"[removed] user '{argv[1]}'")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
