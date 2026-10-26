"""Create a timestamped backup of the encrypted database and evidence files."""
from __future__ import annotations
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from config.settings import BACKUP_DIR, DATABASE_PATH, DATA_ENCRYPTION_KEY, PROJECT_ROOT, RUNTIME_DIR
from src.database.case_store import CaseStore
from src.security.crypto import DataCipher

def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def main() -> None:
    cipher = DataCipher.from_environment(DATA_ENCRYPTION_KEY)
    database = DATABASE_PATH if DATABASE_PATH.is_absolute() else PROJECT_ROOT / DATABASE_PATH
    runtime = RUNTIME_DIR if RUNTIME_DIR.is_absolute() else PROJECT_ROOT / RUNTIME_DIR
    backup_root = BACKUP_DIR if BACKUP_DIR.is_absolute() else PROJECT_ROOT / BACKUP_DIR
    if not database.is_file():
        raise SystemExit("No runtime database exists yet; refusing to create an empty backup.")
    store = CaseStore(database, cipher)
    store.migrate_attachments(runtime / "raw")
    target = backup_root / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target.mkdir(parents=True, exist_ok=False)
    database_copy = target / "drugshield.sqlite3"
    store.backup_to(database_copy)
    evidence_root = runtime / "raw"
    records = []
    for source in store.attachment_storage_paths():
        resolved = source.resolve()
        if not resolved.is_relative_to(evidence_root.resolve()) or not resolved.is_file():
            continue
        relative = resolved.relative_to(runtime.resolve())
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(resolved, destination)
        records.append({"path": relative.as_posix(), "sha256": _sha256(destination)})
    manifest = {"created_at": datetime.now(timezone.utc).isoformat(), "database": "drugshield.sqlite3",
                "database_sha256": _sha256(database_copy),
                "evidence_count": len(records), "evidence": records,
                "encryption": "AES-256-GCM; restore requires the original DRUGSHIELD_DATA_ENCRYPTION_KEY"}
    (target / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(str(target))

if __name__ == "__main__":
    main()
