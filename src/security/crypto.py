"""Authenticated encryption for evidence fields and attachment files."""
from __future__ import annotations

import base64
import binascii
import json
import os
from dataclasses import dataclass

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

PREFIX = b"DSENC1"

@dataclass(frozen=True)
class DataCipher:
    key: bytes

    @classmethod
    def from_environment(cls, encoded: str) -> "DataCipher":
        if not encoded or encoded.startswith(("REPLACE_", "SET_ME", "CHANGE_ME")):
            raise RuntimeError("DRUGSHIELD_DATA_ENCRYPTION_KEY must be configured")
        try:
            key = base64.b64decode(encoded.encode("ascii"), altchars=b"-_", validate=True)
        except (ValueError, binascii.Error, UnicodeEncodeError) as exc:
            raise RuntimeError("DRUGSHIELD_DATA_ENCRYPTION_KEY must be URL-safe base64") from exc
        if len(key) != 32:
            raise RuntimeError("DRUGSHIELD_DATA_ENCRYPTION_KEY must decode to exactly 32 bytes")
        return cls(key)

    @classmethod
    def generate_key(cls) -> str:
        return base64.urlsafe_b64encode(os.urandom(32)).decode("ascii")

    def encrypt_bytes(self, value: bytes, purpose: str) -> bytes:
        nonce = os.urandom(12)
        return PREFIX + nonce + AESGCM(self.key).encrypt(nonce, value, purpose.encode("utf-8"))

    def decrypt_bytes(self, value: bytes, purpose: str) -> bytes:
        if not value.startswith(PREFIX) or len(value) < len(PREFIX) + 28:
            raise ValueError("Evidence is not encrypted or has an invalid envelope")
        start = len(PREFIX)
        return AESGCM(self.key).decrypt(value[start:start + 12], value[start + 12:], purpose.encode("utf-8"))

    def encrypt_json(self, value: object, purpose: str) -> str:
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        return self.encrypt_bytes(encoded, purpose).hex()

    def decrypt_json(self, value: str, purpose: str) -> object:
        try:
            raw = bytes.fromhex(value)
        except ValueError:
            return json.loads(value)
        if not raw.startswith(PREFIX):
            return json.loads(value)
        return json.loads(self.decrypt_bytes(raw, purpose))
