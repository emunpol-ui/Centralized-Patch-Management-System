#!/usr/bin/env python3
"""
Create (or reset the password of) a CPMS administrator account.

FR-019's precondition states: "An administrator account has been
provisioned during server installation or configuration" - i.e. account
provisioning is an out-of-band operations step, not a REST endpoint (there
is no "create the first admin" API, since every dashboard endpoint
requires an authenticated administrator to already exist). This script is
that out-of-band step, matching the project's existing ``scripts/``
directory (SAD Section 7.9).

Usage:
    python scripts/create_admin.py --username admin
    python scripts/create_admin.py --username admin --password "S0meStrongP@ss"
    python scripts/create_admin.py --username admin --reset-password

If ``--password`` is not supplied, the script prompts for one via
``getpass`` (not echoed to the terminal, not left in shell history).
"""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

# Allow running this script directly (`python scripts/create_admin.py`)
# regardless of the current working directory, by ensuring the project
# root is on sys.path so `backend.*` imports resolve.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.core.security import hash_password  # noqa: E402
from backend.database.session import SessionLocal  # noqa: E402
from backend.repositories.administrator_repository import AdministratorRepository  # noqa: E402
from backend.models.administrator import Administrator  # noqa: E402

MIN_PASSWORD_LENGTH = 8


def _read_password(provided: str | None) -> str:
    """Return ``provided``, or interactively prompt for a password twice."""
    if provided:
        return provided

    while True:
        password = getpass.getpass("Administrator password: ")
        if len(password) < MIN_PASSWORD_LENGTH:
            print(f"Password must be at least {MIN_PASSWORD_LENGTH} characters. Try again.")
            continue
        confirm = getpass.getpass("Confirm password: ")
        if password != confirm:
            print("Passwords do not match. Try again.")
            continue
        return password


def main() -> int:
    parser = argparse.ArgumentParser(description="Provision or reset a CPMS administrator account.")
    parser.add_argument("--username", required=True, help="Administrator login name.")
    parser.add_argument(
        "--password",
        default=None,
        help="Administrator password. If omitted, you will be prompted (recommended).",
    )
    parser.add_argument(
        "--reset-password",
        action="store_true",
        help="If the username already exists, reset its password instead of failing.",
    )
    args = parser.parse_args()

    db = SessionLocal()
    repo = AdministratorRepository()

    try:
        existing = repo.get_by_username(db, args.username)

        if existing is not None and not args.reset_password:
            print(
                f"Error: administrator '{args.username}' already exists. "
                "Pass --reset-password to change its password instead.",
                file=sys.stderr,
            )
            return 1

        password = _read_password(args.password)
        if len(password) < MIN_PASSWORD_LENGTH:
            print(f"Error: password must be at least {MIN_PASSWORD_LENGTH} characters.", file=sys.stderr)
            return 1

        if existing is not None:
            existing.password_hash = hash_password(password)
            db.add(existing)
            db.commit()
            print(f"Password reset for administrator '{args.username}'.")
        else:
            administrator = Administrator(username=args.username, password_hash=hash_password(password))
            db.add(administrator)
            db.commit()
            print(f"Administrator '{args.username}' created successfully.")

        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
