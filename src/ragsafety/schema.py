"""Pydantic models shared across the pipeline.

The :class:`Checklist` model doubles as the strict JSON schema the final
generation model must emit (see pipeline/generate.py).
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class ContentType(str, Enum):
    TEXT = "text"
    TABLE = "table"
    OCR = "ocr"


class Domain(str, Enum):
    ELECTRICAL = "electrical"
    GAS = "gas"
    SHARED = "shared"


class SourceType(str, Enum):
    INTERNAL = "internal"
    WEB = "web"


# --------------------------------------------------------------------------- #
# Documents and chunks                                                         #
# --------------------------------------------------------------------------- #
class Chunk(BaseModel):
    """A retrievable unit of a document, with security + provenance metadata."""

    chunk_id: str
    doc: str
    domain: Domain
    section_path: list[str] = Field(default_factory=list)
    page: int
    content_type: ContentType = ContentType.TEXT
    effective_date: str = "2026-01-01"
    allowed_groups: list[str] = Field(default_factory=list)
    strategy: str
    text: str

    @property
    def section_display(self) -> str:
        return " > ".join(self.section_path) if self.section_path else "(root)"

    def citation(self) -> Citation:
        return Citation(
            doc=self.doc,
            section=self.section_display,
            page=self.page,
            source_type=SourceType.INTERNAL,
        )


class RetrievedChunk(BaseModel):
    chunk: Chunk
    score: float = 0.0
    rerank_score: float | None = None

    @property
    def final_score(self) -> float:
        return self.rerank_score if self.rerank_score is not None else self.score


class WebResult(BaseModel):
    title: str
    url: str
    snippet: str
    domain: str


# --------------------------------------------------------------------------- #
# Query understanding                                                          #
# --------------------------------------------------------------------------- #
class Slots(BaseModel):
    """Structured task understanding extracted during rewrite."""

    task: str | None = None
    equipment: str | None = None
    voltage: str | None = None
    location: str | None = None
    domain: Domain | None = None


class RewriteResult(BaseModel):
    original_query: str
    rewritten_query: str
    slots: Slots


class ClarificationRequest(BaseModel):
    needed: bool = False
    question: str = ""
    missing_slots: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Guardrails                                                                   #
# --------------------------------------------------------------------------- #
class GuardrailStage(str, Enum):
    INPUT = "input"
    OUTPUT = "output"


class GuardrailVerdict(BaseModel):
    stage: GuardrailStage
    allowed: bool
    categories: list[str] = Field(default_factory=list)
    reason: str = ""


# --------------------------------------------------------------------------- #
# Output: the checklist                                                        #
# --------------------------------------------------------------------------- #
class Citation(BaseModel):
    doc: str
    section: str
    page: int
    source_type: SourceType = SourceType.INTERNAL
    url: str | None = None


class ChecklistCategory(str, Enum):
    PPE = "ppe"
    CLEARANCE = "clearance"
    PERMIT = "permit"
    ISOLATION = "isolation"
    GAS = "gas"
    STOP_WORK = "stop_work"
    GENERAL = "general"


class ChecklistItem(BaseModel):
    category: ChecklistCategory
    instruction: str
    value: str | None = None  # e.g. "2.44 m", "11 kV", "10 %LEL"
    citations: list[Citation] = Field(default_factory=list)


class Checklist(BaseModel):
    """Strict output schema for the final generation model."""

    task: str
    equipment: str | None = None
    location: str | None = None
    persona: str
    items: list[ChecklistItem] = Field(default_factory=list)
    stop_work_conditions: list[str] = Field(default_factory=list)
    # Facts the model wanted to state but could not ground in any source.
    # Non-empty => the renderer surfaces a hard stop-work / contact-supervisor
    # instruction instead of inventing a value.
    unsupported_claims: list[str] = Field(default_factory=list)
    web_sources: list[Citation] = Field(default_factory=list)
    disclaimer: str = (
        "Prototype output. Not a substitute for site safety procedures, a live "
        "permit, or a competent person's assessment."
    )


# --------------------------------------------------------------------------- #
# Cost / usage / audit                                                         #
# --------------------------------------------------------------------------- #
class TokenUsage(BaseModel):
    model: str = ""
    deployment: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    embedding_tokens: int = 0


class AuditRecord(BaseModel):
    trace_id: str
    date: str  # YYYY-MM-DD, Table PartitionKey
    user: str
    persona: str
    original_query: str
    rewritten_query: str
    clarification_asked: bool
    retrieved_chunk_ids: list[str] = Field(default_factory=list)
    retrieved_scores: list[float] = Field(default_factory=list)
    model: str = ""
    deployment: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    guardrail_in_allowed: bool = True
    guardrail_out_allowed: bool = True
    guardrail_categories: list[str] = Field(default_factory=list)
    answer_hash: str = ""
    outcome: str = "answered"  # answered | clarified | refused | blocked


class QueryResult(BaseModel):
    """What the app returns to the caller / MCP tool."""

    outcome: str  # answered | clarified | refused | blocked
    checklist: Checklist | None = None
    clarification: ClarificationRequest | None = None
    message: str = ""
    trace_id: str = ""
    audit: AuditRecord | None = None
