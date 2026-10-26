"""Environment settings for the local simulation-only application."""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

RUNTIME_DIR = Path(os.getenv("DRUGSHIELD_RUNTIME_DIR", "data/runtime"))
DATABASE_PATH = Path(os.getenv("DRUGSHIELD_DATABASE_PATH", RUNTIME_DIR / "drugshield.sqlite3"))
CORS_ORIGINS = tuple(
    origin.strip()
    for origin in os.getenv(
        "DRUGSHIELD_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",")
    if origin.strip()
)
MAX_ATTACHMENT_BYTES = int(os.getenv("MAX_ATTACHMENT_BYTES", str(12 * 1024 * 1024)))
MAX_ATTACHMENTS_PER_MESSAGE = int(os.getenv("MAX_ATTACHMENTS_PER_MESSAGE", "5"))
MAX_TOTAL_ATTACHMENT_BYTES = int(
    os.getenv("MAX_TOTAL_ATTACHMENT_BYTES", str(25 * 1024 * 1024))
)

APP_ENV = os.getenv("DRUGSHIELD_ENV", "development").casefold()
ALLOWED_HOSTS = tuple(host.strip() for host in os.getenv(
    "DRUGSHIELD_ALLOWED_HOSTS", "localhost,127.0.0.1"
).split(",") if host.strip())
AUTH_SECRET = os.getenv("DRUGSHIELD_AUTH_SECRET", "")
DATA_ENCRYPTION_KEY = os.getenv("DRUGSHIELD_DATA_ENCRYPTION_KEY", "")
AUTH_USERS_JSON = os.getenv("DRUGSHIELD_USERS_JSON", "[]")
SESSION_COOKIE_NAME = "drugshield_session"
SESSION_TTL_SECONDS = int(os.getenv("DRUGSHIELD_SESSION_TTL_SECONDS", "1800"))
RETENTION_DAYS = int(os.getenv("DRUGSHIELD_RETENTION_DAYS", "90"))
BACKUP_DIR = Path(os.getenv("DRUGSHIELD_BACKUP_DIR", "data/backups"))
MAX_REQUEST_BYTES = int(os.getenv("DRUGSHIELD_MAX_REQUEST_BYTES", str(30 * 1024 * 1024)))
