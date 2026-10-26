"""Create a password hash record for DRUGSHIELD_USERS_JSON."""
from __future__ import annotations
import getpass
import json
import sys
from .auth import hash_password

def main() -> None:
    if len(sys.argv) != 3 or sys.argv[2] not in {"simulator", "reviewer", "admin"}:
        raise SystemExit("Usage: python -m src.security.manage_users USERNAME simulator|reviewer|admin")
    first = getpass.getpass("Password (12+ characters): ")
    second = getpass.getpass("Repeat password: ")
    if first != second:
        raise SystemExit("Passwords did not match")
    print(json.dumps({"username": sys.argv[1], "roles": [sys.argv[2]], "password_hash": hash_password(first)}))

if __name__ == "__main__":
    main()
