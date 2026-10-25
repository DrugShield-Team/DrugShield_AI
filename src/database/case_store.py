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
    def __init__(self, database_path: Path):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

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
                 _dump(event), _dump(analysis)),
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
                 _dump(event), _dump(analysis)),
            )
            if case_id is not None:
                if report is None or report_sha256 is None:
                    raise ValueError("A case requires a report and its digest")
                connection.execute(
                    "INSERT INTO evidence_cases VALUES (?, ?, 'pending_review', ?, ?, ?)",
                    (case_id, event_id, _now(), _dump(report), report_sha256),
                )

    def create_case(self, case_id: str, event_id: str, report: Dict[str, Any], report_sha256: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO evidence_cases VALUES (?, ?, 'pending_review', ?, ?, ?)",
                (case_id, event_id, _now(), _dump(report), report_sha256),
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
        result["report"] = json.loads(result.pop("report_json"))
        result["review_history"] = [dict(item) for item in reviews]
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
            report = json.loads(result.pop("report_json"))
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
        event = json.loads(row["event_json"])
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
                (case_id, reviewer_id, action, note, _now()),
            )
        return self.get_case(case_id)


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
