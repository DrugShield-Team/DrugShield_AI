"""Extract candidate UPI/VPA identifiers from message text or decoded payloads.

This module performs syntax-oriented candidate extraction only. A match does
not verify that a VPA exists, belongs to a person, or is suspicious.
"""

from __future__ import annotations

import html
import re
from typing import Dict, List
from urllib.parse import parse_qs, urlsplit


# Broad candidate pattern. Provider-specific acceptance rules can change, so
# extracted values must be verified separately before being treated as valid.
_VPA_PATTERN = re.compile(
    r"(?<![A-Za-z0-9._%+\-])"
    r"(?P<local>[A-Za-z0-9](?:[A-Za-z0-9._-]{0,253}[A-Za-z0-9])?)"
    r"@(?P<provider>[A-Za-z0-9][A-Za-z0-9.-]{0,61}[A-Za-z0-9])"
    r"(?![A-Za-z0-9._%+@\-])"
)
_UPI_URI_PATTERN = re.compile(r"(?i)\bupi://[^\s<>\"']+")
_URI_TRAILING_PUNCTUATION = ".,;:!?)]}"


def extract_vpa_candidates(text: str, source: str = "text") -> List[Dict[str, str]]:
    """Return unique VPA-shaped strings with their source and evidence type.

    Also reads the ``pa`` parameter from UPI payment URIs such as
    ``upi://pay?pa=name@provider&pn=...``. The function does not resolve or
    validate the account and deliberately does not assign a fraud label.
    """
    if not isinstance(text, str) or not text:
        return []

    found: Dict[str, Dict[str, str]] = {}
    normalized_text = html.unescape(text)

    # Parse UPI URIs first so their `pa` field keeps the more specific evidence
    # type instead of being classified as only a generic VPA-shaped string.
    for match in _UPI_URI_PATTERN.finditer(normalized_text):
        token = match.group(0).rstrip(_URI_TRAILING_PUNCTUATION)
        try:
            query = parse_qs(urlsplit(token).query, keep_blank_values=False)
        except ValueError:
            continue
        for value in query.get("pa", []):
            candidate = _normalize_candidate(value)
            if candidate:
                found.setdefault(candidate.casefold(), {
                    "candidate": candidate,
                    "source": source,
                    "evidence_type": "upi_uri_pa",
                })

    # Then look for VPA-shaped candidates in ordinary text. This intentionally
    # stays provider-agnostic, so an email-shaped string may also be a candidate
    # and must be checked by downstream review rather than treated as verified.
    for match in _VPA_PATTERN.finditer(normalized_text):
        candidate = match.group(0)
        if not _valid_parts(match.group("local"), match.group("provider")):
            continue
        found.setdefault(candidate.casefold(), {
            "candidate": candidate,
            "source": source,
            "evidence_type": "vpa_pattern",
        })

    return list(found.values())


def _normalize_candidate(value: str) -> str | None:
    """Trim harmless surrounding punctuation and validate an exact VPA value."""
    candidate = value.strip().strip("\"'<> ")
    match = _VPA_PATTERN.fullmatch(candidate)
    if not match or not _valid_parts(match.group("local"), match.group("provider")):
        return None
    return candidate


def _valid_parts(local: str, provider: str) -> bool:
    """Reject malformed separators while allowing provider-agnostic handles."""
    if not local or not provider:
        return False
    if local[0] in "._-" or local[-1] in "._-" or ".." in local:
        return False
    if provider[0] in ".-" or provider[-1] in ".-" or ".." in provider:
        return False
    return True
