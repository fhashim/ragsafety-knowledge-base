"""Concept detection shared by the mock embedder, generation, and guardrails.

A "concept" is a safety idea (hand protection, approach distance, ...) defined by
a list of trigger phrases in ``config/concepts.yaml``. Detecting concepts lets us
(a) build semantic-ish mock embeddings and (b) classify extracted facts into
checklist categories without an LLM.
"""

from __future__ import annotations

import functools

from .schema import ChecklistCategory
from .settings import load_concepts

# concept name -> checklist category
CONCEPT_TO_CATEGORY: dict[str, ChecklistCategory] = {
    "hand_protection": ChecklistCategory.PPE,
    "eye_face_protection": ChecklistCategory.PPE,
    "arc_flash": ChecklistCategory.PPE,
    "high_vis": ChecklistCategory.PPE,
    "ppe_general": ChecklistCategory.PPE,
    "approach_distance": ChecklistCategory.CLEARANCE,
    "voltage": ChecklistCategory.CLEARANCE,
    "exclusion_zone": ChecklistCategory.GAS,
    "gas_detection": ChecklistCategory.GAS,
    "isolation_loto": ChecklistCategory.ISOLATION,
    "permit": ChecklistCategory.PERMIT,
    "hot_work": ChecklistCategory.PERMIT,
    "confined_space": ChecklistCategory.PERMIT,
    "working_at_height": ChecklistCategory.GENERAL,
    "fatigue": ChecklistCategory.GENERAL,
    "lifting_rigging": ChecklistCategory.GENERAL,
    "emergency_stop": ChecklistCategory.STOP_WORK,
}


@functools.lru_cache(maxsize=1)
def _concepts() -> dict[str, list[str]]:
    return load_concepts()


def detect_concepts(text: str) -> list[str]:
    """Return the concepts whose trigger phrases appear in ``text``."""
    lower = text.lower()
    return [c for c, terms in _concepts().items() if any(t in lower for t in terms)]


def category_for_text(text: str) -> ChecklistCategory:
    """Best-fit checklist category for a line of source text."""
    for concept in detect_concepts(text):
        if concept in CONCEPT_TO_CATEGORY:
            return CONCEPT_TO_CATEGORY[concept]
    return ChecklistCategory.GENERAL
