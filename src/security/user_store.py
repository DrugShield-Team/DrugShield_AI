"""Persistent reviewer account and station assignment storage."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class UserStore:
    """Stores admin-created reviewers and assignments beside the case database."""

    def __init__(self, database_path: Path):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS reviewer_accounts (
                    username TEXT PRIMARY KEY COLLATE NOCASE,
                    password_hash TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS reviewer_station_assignments (
                    username TEXT PRIMARY KEY COLLATE NOCASE,
                    station TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 10000")
        return connection

    def get_dynamic_user(self, username: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT username, password_hash, active FROM reviewer_accounts WHERE username=? COLLATE NOCASE",
                (username,),
            ).fetchone()
        if row is None:
            return None
        return {"username": row["username"], "password_hash": row["password_hash"],
                "roles": ["reviewer"], "active": bool(row["active"]), "source": "dashboard"}

    def station_for(self, username: str) -> str | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT station FROM reviewer_station_assignments WHERE username=? COLLATE NOCASE",
                (username,),
            ).fetchone()
        return row["station"] if row else None

    def create_reviewer(self, username: str, password_hash: str, station: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO reviewer_accounts(username, password_hash, active, created_at) VALUES (?, ?, 1, ?)",
                (username, password_hash, _now()),
            )
            connection.execute(
                "INSERT INTO reviewer_station_assignments(username, station, updated_at) VALUES (?, ?, ?)",
                (username, station, _now()),
            )

    def assign_station(self, username: str, station: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO reviewer_station_assignments(username, station, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(username) DO UPDATE SET station=excluded.station, updated_at=excluded.updated_at",
                (username, station, _now()),
            )

    def set_active(self, username: str, active: bool) -> bool:
        with self._connect() as connection:
            result = connection.execute(
                "UPDATE reviewer_accounts SET active=? WHERE username=? COLLATE NOCASE",
                (int(active), username),
            )
        return result.rowcount > 0

    def set_password(self, username: str, password_hash: str) -> bool:
        with self._connect() as connection:
            result = connection.execute(
                "UPDATE reviewer_accounts SET password_hash=? WHERE username=? COLLATE NOCASE",
                (password_hash, username),
            )
        return result.rowcount > 0

    def list_reviewers(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT a.username, a.active, a.created_at, s.station, s.updated_at "
                "FROM reviewer_accounts a LEFT JOIN reviewer_station_assignments s "
                "ON a.username=s.username ORDER BY a.username COLLATE NOCASE"
            ).fetchall()
        return [dict(row) | {"roles": ["reviewer"], "source": "dashboard"} for row in rows]
