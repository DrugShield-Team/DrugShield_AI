"""SQLite persistence for simulation events, evidence reports, and review audit."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class CaseStore:
    def __init__(self, database_path: Path, cipher=None):
        self.database_path = Path(database_path)
        self.cipher = cipher
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()
        if self.cipher:
            self._migrate_encrypted_columns()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA synchronous = FULL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS simulation_events (
                    event_id TEXT PRIMARY KEY,
                    channel TEXT NOT NULL,
                    conversation_id TEXT NOT NULL,
                    message_id TEXT NOT NULL,
                    received_at TEXT NOT NULL,
                    event_json TEXT NOT NULL,
                    analysis_json TEXT NOT NULL,
                    UNIQUE(channel, conversation_id, message_id)
                );
                CREATE TABLE IF NOT EXISTS evidence_cases (
                    case_id TEXT PRIMARY KEY,
                    event_id TEXT NOT NULL UNIQUE REFERENCES simulation_events(event_id),
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    report_json TEXT NOT NULL,
                    report_sha256 TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS review_history (
                    review_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    case_id TEXT NOT NULL REFERENCES evidence_cases(case_id),
                    reviewer_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    note TEXT NOT NULL,
                    occurred_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_cases_status_created
                    ON evidence_cases(status, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_reviews_case
                    ON review_history(case_id, review_id);
                """
            )

    def event_exists(self, channel: str, conversation_id: str, message_id: str) -> Optional[str]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT event_id FROM simulation_events WHERE channel=? AND conversation_id=? AND message_id=?",
                (channel, conversation_id, message_id),
            ).fetchone()
        return row["event_id"] if row else None

    def save_event(self, event_id: str, channel: str, conversation_id: str, message_id: str,
                   event: Dict[str, Any], analysis: Dict[str, Any]) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO simulation_events VALUES (?, ?, ?, ?, ?, ?, ?)",
                (event_id, channel, conversation_id, message_id, _now(),
                 self._encode(event, "event"), self._encode(analysis, "analysis")),
            )

    def save_event_and_case(
        self,
        *,
        event_id: str,
        channel: str,
        conversation_id: str,
        message_id: str,
        event: Dict[str, Any],
        analysis: Dict[str, Any],
        case_id: Optional[str],
        report: Optional[Dict[str, Any]],
        report_sha256: Optional[str],
    ) -> None:
        """Persist the event and optional review case in one transaction."""
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO simulation_events VALUES (?, ?, ?, ?, ?, ?, ?)",
                (event_id, channel, conversation_id, message_id, _now(),
                 self._encode(event, "event"), self._encode(analysis, "analysis")),
            )
            if case_id is not None:
                if report is None or report_sha256 is None:
                    raise ValueError("A case requires a report and its digest")
                connection.execute(
                    "INSERT INTO evidence_cases VALUES (?, ?, 'pending_review', ?, ?, ?)",
                    (case_id, event_id, _now(), self._encode(report, "report"), report_sha256),
                )

    def create_case(self, case_id: str, event_id: str, report: Dict[str, Any], report_sha256: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO evidence_cases VALUES (?, ?, 'pending_review', ?, ?, ?)",
                (case_id, event_id, _now(), self._encode(report, "report"), report_sha256),
            )

    def get_case(self, case_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT case_id, event_id, status, created_at, report_json, report_sha256 "
                "FROM evidence_cases WHERE case_id=?", (case_id,),
            ).fetchone()
            if not row:
                return None
            reviews = connection.execute(
                "SELECT reviewer_id, action, note, occurred_at FROM review_history "
                "WHERE case_id=? ORDER BY review_id", (case_id,),
            ).fetchall()
        result = dict(row)
        result["report"] = self._decode(result.pop("report_json"), "report")
        result["review_history"] = []
        for item in reviews:
            review = dict(item)
            if self.cipher:
                review["note"] = self._decode(review["note"], "review").get("note", "")
                review["reviewer_id"] = self._decode(review["reviewer_id"], "reviewer").get("reviewer_id", "")
            result["review_history"].append(review)
        return result

    def list_cases(self, status: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        query = "SELECT case_id, event_id, status, created_at, report_json, report_sha256 FROM evidence_cases"
        params: List[Any] = []
        if status:
            query += " WHERE status=?"
            params.append(status)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        results = []
        for row in rows:
            result = dict(row)
            report = self._decode(result.pop("report_json"), "report")
            result["summary"] = report.get("summary", {})
            results.append(result)
        return results

    def get_attachment(self, case_id: str, attachment_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT e.event_json FROM evidence_cases c JOIN simulation_events e "
                "ON c.event_id=e.event_id WHERE c.case_id=?", (case_id,),
            ).fetchone()
        if not row:
            return None
        event = self._decode(row["event_json"], "event")
        return next(
            (item for item in event.get("attachments", []) if item.get("attachment_id") == attachment_id),
            None,
        )

    def add_review(self, case_id: str, reviewer_id: str, action: str, note: str) -> Optional[Dict[str, Any]]:
        status_for_action = {
            "accept": "accepted",
            "further_review": "further_review",
            "dismiss": "dismissed",
        }
        with self._connect() as connection:
            row = connection.execute(
                "SELECT status FROM evidence_cases WHERE case_id=?", (case_id,),
            ).fetchone()
            if not row:
                return None
            if row["status"] in {"accepted", "dismissed"}:
                raise ValueError("A finalized review cannot be changed")
            new_status = status_for_action[action]
            connection.execute(
                "UPDATE evidence_cases SET status=? WHERE case_id=?", (new_status, case_id),
            )
            connection.execute(
                "INSERT INTO review_history (case_id, reviewer_id, action, note, occurred_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (case_id, self._encode({"reviewer_id": reviewer_id}, "reviewer"),
                 action, self._encode({"note": note}, "review"), _now()),
            )
        return self.get_case(case_id)

    def ping(self) -> bool:
        with self._connect() as connection:
            connection.execute("SELECT 1").fetchone()
        return True

    def backup_to(self, destination: Path) -> None:
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as source, sqlite3.connect(destination) as target:
            source.backup(target)

    def attachment_storage_paths(self) -> List[Path]:
        with self._connect() as connection:
            rows = connection.execute("SELECT event_json FROM simulation_events").fetchall()
        paths = []
        for row in rows:
            event = self._decode(row["event_json"], "event")
            paths.extend(Path(item["storage_path"]) for item in event.get("attachments", []) if item.get("storage_path"))
        return paths

    def purge_expired(self, before_iso: str) -> List[Path]:
        # Remove expired records; the caller deletes returned evidence files.
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT event_id, event_json FROM simulation_events WHERE received_at < ?", (before_iso,)
            ).fetchall()
            paths = []
            event_ids = []
            for row in rows:
                event = self._decode(row["event_json"], "event")
                paths.extend(Path(item["storage_path"]) for item in event.get("attachments", []) if item.get("storage_path"))
                event_ids.append(row["event_id"])
            for event_id in event_ids:
                connection.execute("DELETE FROM review_history WHERE case_id IN (SELECT case_id FROM evidence_cases WHERE event_id=?)", (event_id,))
                connection.execute("DELETE FROM evidence_cases WHERE event_id=?", (event_id,))
                connection.execute("DELETE FROM simulation_events WHERE event_id=?", (event_id,))
        return paths

    def count_expired(self, before_iso: str) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS total FROM simulation_events WHERE received_at < ?", (before_iso,)
            ).fetchone()
        return int(row["total"])

    def _encode(self, value: Dict[str, Any], purpose: str) -> str:
        return self.cipher.encrypt_json(value, purpose) if self.cipher else _dump(value)

    def _decode(self, value: str, purpose: str) -> Dict[str, Any]:
        if self.cipher:
            return self.cipher.decrypt_json(value, purpose)
        return json.loads(value)

    def _migrate_encrypted_columns(self) -> None:
        """Encrypt legacy local plaintext rows in place on first protected startup."""
        with self._connect() as connection:
            for table, column, primary_key, purpose in (
                ("simulation_events", "event_json", "event_id", "event"),
                ("simulation_events", "analysis_json", "event_id", "analysis"),
                ("evidence_cases", "report_json", "case_id", "report"),
                ("review_history", "note", "review_id", "review"),
                ("review_history", "reviewer_id", "review_id", "reviewer"),
            ):
                rows = connection.execute(
                    f"SELECT {primary_key}, {column} FROM {table}"
                ).fetchall()
                for row in rows:
                    encoded = row[column]
                    try:
                        raw = bytes.fromhex(encoded)
                        if raw.startswith(b"DSENC1"):
                            self.cipher.decrypt_json(encoded, purpose)
                            continue
                    except ValueError:
                        pass
                    if purpose == "review":
                        value = {"note": encoded}
                    elif purpose == "reviewer":
                        value = {"reviewer_id": encoded}
                    else:
                        value = json.loads(encoded)
                    connection.execute(
                        f"UPDATE {table} SET {column}=? WHERE {primary_key}=?",
                        (self._encode(value, purpose), row[primary_key]),
                    )
        with self._connect() as connection:
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    def migrate_attachments(self, storage_root: Path) -> int:
        """Encrypt legacy attachment files referenced by stored events."""
        storage_root = Path(storage_root).resolve()
        migrated = 0
        remove_after_commit = []
        with self._connect() as connection:
            rows = connection.execute("SELECT event_id, event_json FROM simulation_events").fetchall()
            for row in rows:
                event = self._decode(row["event_json"], "event")
                changed = False
                old_files = []
                for attachment in event.get("attachments", []):
                    old_value = attachment.get("storage_path")
                    if not old_value:
                        continue
                    old_path = Path(old_value).resolve()
                    if not old_path.is_relative_to(storage_root) or not old_path.is_file():
                        continue
                    file_content = old_path.read_bytes()
                    if file_content.startswith(b"DSENC1"):
                        self.cipher.decrypt_bytes(file_content, "attachment")
                        continue
                    encrypted_path = old_path.with_suffix(old_path.suffix + ".enc")
                    encrypted_path.write_bytes(self.cipher.encrypt_bytes(file_content, "attachment"))
                    attachment["storage_path"] = str(encrypted_path)
                    old_files.append(old_path)
                    changed = True
                if changed:
                    connection.execute(
                        "UPDATE simulation_events SET event_json=? WHERE event_id=?",
                        (self._encode(event, "event"), row["event_id"]),
                    )
                    remove_after_commit.extend(old_files)
                    migrated += len(old_files)
        for old_path in remove_after_commit:
            old_path.unlink(missing_ok=True)
        with self._connect() as connection:
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        return migrated


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
