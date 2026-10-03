"""Grounded fact extraction from source text.

Used by the mock generator to build a checklist *only* from values that actually
appear in retrieved chunks, and by the output guardrail to verify that every
cited value is supported. Keeping extraction separate (not buried in the LLM
client) is what makes the "never invent a value" rule testable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .concepts import category_for_text
from .schema import ChecklistCategory, ContentType, RetrievedChunk

# Units seen in the synthetic knowledge base. Longer/compound units first so the
# alternation does not match a shorter unit by mistake (e.g. "minutes" before "m").
_UNIT = (
    r"(?:kv|cal/cm2|cal/cm²|%\s?lel|%lel|lel|minutes|min|hours|hour|hrs|"
    r"mm|cm|bar|psi|°c|kpa|m|v|%)"
)
_VALUE_RE = re.compile(r"\b\d+(?:\.\d+)?\s?" + _UNIT + r"\b", re.IGNORECASE)

# Imperative safety verbs that make a line worth keeping even without a number.
_IMPERATIVE = (
    "wear",
    "select",
    "use",
    "isolate",
    "lock",
    "tag",
    "obtain",
    "verify",
    "confirm",
    "test",
    "ventilate",
    "cordon",
    "evacuate",
    "stop",
    "do not",
    "never",
    "ensure",
    "apply",
    "earth",
    "ground",
    "inspect",
)
# PPE / equipment nouns that make a conceptual line worth keeping even without a
# number or imperative (so "insulating gloves must be class-rated" is captured).
_KEEP_TERMS = (
    "glove",
    "goggle",
    "face shield",
    "visor",
    "harness",
    "respirator",
    "helmet",
    "hard hat",
    "boots",
    "hi-vis",
    "high-visibility",
    "high visibility",
)


@dataclass
class Fact:
    line: str
    value: str | None
    category: ChecklistCategory
    chunk: RetrievedChunk

    def citation(self):
        return self.chunk.chunk.citation()


def _clean_line(line: str) -> str:
    # Flatten markdown table rows "| a | b |" into "a - b".
    if line.strip().startswith("|"):
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        cells = [c for c in cells if c and not set(c) <= {"-", ":", " "}]
        return " — ".join(cells)
    return line.strip().lstrip("#").strip("-* ").strip()


def _normalize_value(v: str) -> str:
    return v.lower().replace(" ", "")


def extract_values(text: str) -> list[str]:
    """All numeric+unit values present in ``text`` (normalized surface forms)."""
    return [m.group(0) for m in _VALUE_RE.finditer(text)]


def value_supported(sources_text: str, value: str) -> bool:
    """True if ``value`` (ignoring spaces/case) appears in ``sources_text``."""
    hay = _normalize_value(sources_text)
    return _normalize_value(value) in hay


def _candidate_lines(text: str) -> list[str]:
    """Split chunk text into fact candidates.

    Table rows (``| a | b |``) stay whole; prose lines are further split into
    sentences so one grounded value lands in one citable fact (otherwise a whole
    section collapses into a single giant "fact" with the wrong value).
    """
    out: list[str] = []
    for raw in text.splitlines():
        if raw.strip().startswith("|"):
            out.append(raw)
        else:
            out.extend(re.split(r"(?<=[.;:])\s+", raw))
    return out


def extract_facts(retrieved: list[RetrievedChunk]) -> list[Fact]:
    """Pull grounded, citable facts from retrieved chunks, de-duplicated by line."""
    facts: list[Fact] = []
    seen: set[str] = set()
    for rc in retrieved:
        for raw in _candidate_lines(rc.chunk.text):
            is_table_row = raw.strip().startswith("|")
            line = _clean_line(raw)
            if len(line) < 4:
                continue
            lower = line.lower()
            values = extract_values(line)
            has_value = bool(values)
            is_imperative = any(lower.startswith(v) or f" {v} " in f" {lower} " for v in _IMPERATIVE)
            has_keep_term = any(t in lower for t in _KEEP_TERMS)
            # Table rows are always informative (they may hold unit-less values
            # like a sling capacity factor of 0.71), so keep them unconditionally.
            if not (has_value or is_imperative or has_keep_term or is_table_row):
                continue
            key = _normalize_value(line)
            if key in seen:
                continue
            seen.add(key)
            facts.append(
                Fact(
                    # For table rows the condition comes first and the answer
                    # last ("| 11 kV | 0.64 m |"), so the last value is the one
                    # a technician needs.
                    line=line,
                    value=values[-1] if values else None,
                    category=category_for_text(line),
                    chunk=rc,
                )
            )
    return facts


def find_fact(
    facts: list[Fact],
    category: ChecklistCategory,
    must_contain: list[str] | None = None,
) -> Fact | None:
    """First fact in ``category`` whose line contains all ``must_contain`` tokens.

    Table-sourced facts are preferred: a value in a table (e.g. the approach-
    distance table) is more authoritative than the same number mentioned in
    prose, so a plain "distance at 33 kV" resolves to the table row.
    """
    needles = [m.lower() for m in (must_contain or [])]

    def _matches(f: Fact) -> bool:
        return f.category == category and all(n in f.line.lower() for n in needles)

    candidates = [f for f in facts if _matches(f)]
    candidates.sort(key=lambda f: 0 if f.chunk.chunk.content_type == ContentType.TABLE else 1)
    return candidates[0] if candidates else None
