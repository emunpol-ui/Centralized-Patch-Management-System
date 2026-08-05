#!/usr/bin/env python3
"""
DEVELOPMENT / TESTING UTILITY ONLY - seed a registered ``Client`` row with
a known, plaintext API key so AUTH-002's authentication mechanism can be
exercised manually.

This is NOT the production mechanism for creating clients. FR-001 Client
Registration (ticket CLIENT-001, not yet implemented) is what will let a
real Client Agent register itself over the network; this script exists
only because AUTH-002 ("valid clients accepted, invalid clients
rejected") has no other way to be tested end-to-end until CLIENT-001
exists. Unlike ``scripts/create_admin.py`` (which implements a real,
PRS-documented provisioning step - FR-019's precondition explicitly
describes out-of-band administrator provisioning), this script has no
such textual basis in the PRS and should be considered scaffolding to be
retired once CLIENT-001 ships.

Usage:
    python scripts/dev_seed_client.py --hostname PC-LAB-01
"""

from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.core.security import generate_token, hash_token  # noqa: E402
from backend.database.session import SessionLocal  # noqa: E402
from backend.models.client import Client  # noqa: E402
from backend.models.enums import ClientStatus  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="[DEV ONLY] Seed a Client row with a known API key.")
    parser.add_argument("--hostname", required=True, help="Hostname for the seeded client.")
    parser.add_argument("--ip-address", default="192.168.10.99", help="IP address for the seeded client.")
    parser.add_argument("--os", dest="operating_system", default="Windows 11 Pro", help="Operating system string.")
    parser.add_argument("--agent-version", default="0.0.0-dev", help="Agent version string.")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        raw_key = generate_token()
        client = Client(
            agent_guid=uuid.uuid4(),
            api_key_hash=hash_token(raw_key),
            hostname=args.hostname,
            ip_address=args.ip_address,
            operating_system=args.operating_system,
            agent_version=args.agent_version,
            status=ClientStatus.UNKNOWN,
        )
        db.add(client)
        db.commit()

        print(f"Seeded client '{args.hostname}' (id={client.id}).")
        print(f"Raw API key (shown once, not recoverable): {raw_key}")
        print(f"\nTest with:\n  curl -H \"Authorization: Bearer {raw_key}\" http://localhost:8000/api/agent/ping")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
