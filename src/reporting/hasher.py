"""Canonical JSON hashing for local simulation evidence reports."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def sha256_json(value: Any) -> str:
    canonical = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()
