"""Small, dependency-free utilities: tokenization, hashing, PII redaction."""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime

_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9\-/\.%]*")

# PII patterns used to redact audit logs. Deliberately conservative — this is a
# demo, not a certified PII engine. Content Safety PII does the real work in
# Azure mode; this keeps local logs clean.
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?\d[\d\-\s()]{7,}\d)(?!\d)")
_LONG_NUM_RE = re.compile(r"(?<!\d)\d{9,}(?!\d)")  # SSNs, card-like, account ids


def tokenize(text: str) -> list[str]:
    """Lowercased word/number tokens. Keeps codes like ``tx-400`` intact."""
    return [m.group(0).lower() for m in _TOKEN_RE.finditer(text)]


def count_tokens(text: str) -> int:
    """Cheap token estimate (~1.3 words/token heuristic kept simple: words)."""
    return len(tokenize(text))


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def answer_hash(text: str) -> str:
    """Short, stable hash for the audit trail."""
    return sha256(text)[:16]


def redact_pii(text: str) -> str:
    """Replace emails, phone numbers and long digit runs with placeholders."""
    text = _EMAIL_RE.sub("[REDACTED_EMAIL]", text)
    text = _PHONE_RE.sub("[REDACTED_PHONE]", text)
    text = _LONG_NUM_RE.sub("[REDACTED_NUM]", text)
    return text


def today_utc() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


def now_iso() -> str:
    return datetime.now(UTC).isoformat()
