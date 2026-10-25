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
