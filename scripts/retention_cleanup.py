"""Retention cleanup. Preview by default; pass --apply to permanently delete."""
from __future__ import annotations
import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path

from config.settings import DATA_ENCRYPTION_KEY, DATABASE_PATH, PROJECT_ROOT, RETENTION_DAYS, RUNTIME_DIR
from src.database.case_store import CaseStore
from src.security.crypto import DataCipher

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Permanently delete expired database records and evidence")
    args = parser.parse_args()
    if RETENTION_DAYS < 1:
        raise SystemExit("DRUGSHIELD_RETENTION_DAYS must be positive")
    database = DATABASE_PATH if DATABASE_PATH.is_absolute() else PROJECT_ROOT / DATABASE_PATH
    runtime = RUNTIME_DIR if RUNTIME_DIR.is_absolute() else PROJECT_ROOT / RUNTIME_DIR
    if not database.is_file():
        raise SystemExit("No runtime database exists; there is nothing to retain or purge.")
    store = CaseStore(database, DataCipher.from_environment(DATA_ENCRYPTION_KEY))
    cutoff = (datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)).isoformat()
    expired_count = store.count_expired(cutoff)
    if not args.apply:
        print(f"Preview only: {expired_count} events are older than {cutoff}. Use --apply to delete.")
        return
    paths = store.purge_expired(cutoff)
    for path in paths:
        resolved = path.resolve()
        if resolved.is_relative_to((runtime / "raw").resolve()) and resolved.is_file():
            resolved.unlink()
    print("Expired records were purged; encrypted evidence files removed: " + str(len(paths)))

if __name__ == "__main__":
    main()
