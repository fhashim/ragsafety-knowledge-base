"""Client interfaces shared by the mock and Azure implementations.

The pipeline depends only on these abstractions, so swapping ``MOCK_MODE`` never
changes a line of pipeline code.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from ..schema import (
    Checklist,
    Chunk,
    ClarificationRequest,
    GuardrailStage,
    GuardrailVerdict,
    RetrievedChunk,
    RewriteResult,
    TokenUsage,
    WebResult,
)


@dataclass
class ChatResponse:
    text: str
    usage: TokenUsage = field(default_factory=TokenUsage)


class EmbeddingClient(ABC):
    dim: int

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector per input text."""


class ChatClient(ABC):
    """Task-oriented chat interface.

    The three methods mirror the three LLM touch-points in the query flow. The
    Azure implementation builds prompts and calls the model; the mock
    implementation produces deterministic structured output from ``*_ctx``.
    """

    @abstractmethod
    def rewrite(self, query: str) -> tuple[RewriteResult, TokenUsage]:
        ...

    @abstractmethod
    def clarify(self, rewrite: RewriteResult) -> tuple[ClarificationRequest, TokenUsage]:
        ...

    @abstractmethod
    def generate(
        self,
        rewrite: RewriteResult,
        retrieved: list[RetrievedChunk],
        web: list[WebResult],
        persona: str,
    ) -> tuple[Checklist, TokenUsage]:
        ...


class SearchClient(ABC):
    @abstractmethod
    def create_or_update_index(self, strategy: str) -> None:
        """Idempotently ensure the index for ``strategy`` exists."""

    @abstractmethod
    def upload(self, strategy: str, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        ...

    @abstractmethod
    def search(
        self,
        strategy: str,
        query: str,
        query_vector: list[float],
        *,
        allowed_groups: list[str],
        mode: str,
        top_k: int,
        semantic_rerank: bool,
    ) -> list[RetrievedChunk]:
        ...


class DocIntelClient(ABC):
    @abstractmethod
    def parse(self, source_path: str) -> ParsedDocument:
        """Parse a PDF/PNG into layout-aware Markdown blocks."""


class ContentSafetyClient(ABC):
    @abstractmethod
    def check_input(self, text: str) -> GuardrailVerdict:
        """Prompt Shields (jailbreak), harmful content, off-topic — on the user query."""

    @abstractmethod
    def check_retrieved(self, retrieved: list[RetrievedChunk]) -> GuardrailVerdict:
        """Prompt Shields for indirect injection planted in retrieved documents."""

    @abstractmethod
    def check_output(self, checklist, retrieved: list[RetrievedChunk]) -> GuardrailVerdict:
        """Groundedness + mandatory citations on the generated checklist."""

    def _verdict(
        self, stage: GuardrailStage, allowed: bool, categories: list[str], reason: str
    ) -> GuardrailVerdict:
        return GuardrailVerdict(
            stage=stage, allowed=allowed, categories=categories, reason=reason
        )


class WebGroundingClient(ABC):
    @abstractmethod
    def search(self, query: str, allowed_domains: list[str]) -> list[WebResult]:
        """Grounding with Bing, restricted to the regulator allow-list."""


class AuditClient(ABC):
    @abstractmethod
    def write(self, record) -> None:  # record: AuditRecord
        ...


@dataclass
class DocBlock:
    """One layout block produced by Document Intelligence."""

    kind: str  # heading | paragraph | table | ocr
    text: str  # markdown (tables are GitHub-flavored markdown tables)
    page: int
    level: int = 0  # heading level when kind == "heading"


@dataclass
class ParsedDocument:
    doc: str
    domain: str
    allowed_groups: list[str]
    blocks: list[DocBlock]
