#!/usr/bin/env python3
"""Generate an INTERNAL_ADMIN_PASSWORD_HASH without echoing the password."""

from __future__ import annotations

import getpass
import pathlib
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from packages.security.passwords import hash_password  # noqa: E402


def main() -> int:
    password = getpass.getpass("Internal administrator password: ")
    confirmation = getpass.getpass("Confirm password: ")
    if password != confirmation:
        print("Passwords do not match", file=sys.stderr)
        return 1
    try:
        print(hash_password(password))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

