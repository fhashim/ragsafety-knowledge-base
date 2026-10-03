"""High-level application: ingest the knowledge base, then answer queries.

A single ``RagSafetyApp`` instance holds the clients (and, in mock mode, the
in-memory index), so ingest once and answer many times.
"""

from __future__ import annotations

import logging
from pathlib import Path

from .clients import Clients, build_clients
from .pipeline.chunk import chunk_document
from .pipeline.embed_index import index_chunks
from .pipeline.parse import parse_document
from .schema import QueryResult
from .settings import DATA_DIR, ChunkStrategy, RetrievalMode, Settings, get_settings
from .tracing import configure_tracing

logger = logging.getLogger("ragsafety.app")

RAW_DIR = DATA_DIR / "raw"


def discover_sources(raw_dir: Path = RAW_DIR) -> list[str]:
    """Source documents = every pdf/png in data/raw that has a layout sidecar."""
    sources: list[str] = []
    for pattern in ("*.pdf", "*.png"):
        for p in sorted(raw_dir.glob(pattern)):
            if p.with_suffix(".layout.json").exists():
                sources.append(str(p))
    return sources


class RagSafetyApp:
    def __init__(self, settings: Settings | None = None, clients: Clients | None = None) -> None:
        self.settings = settings or get_settings()
        self.clients = clients or build_clients(self.settings)
        configure_tracing(self.settings)
        self._ingested: set[str] = set()

    def ingest(self, strategies: list[ChunkStrategy] | None = None) -> dict[str, int]:
        """Parse, chunk and index every source document for each strategy.

        Returns a map strategy -> chunk count.
        """
        strategies = strategies or [self.settings.chunk_strategy]
        sources = discover_sources()
        if not sources:
            raise FileNotFoundError(
                f"No source documents in {RAW_DIR}. Run `python scripts/generate_data.py` first."
            )
        counts: dict[str, int] = {}
        parsed_docs = [parse_document(self.clients, s) for s in sources]
        for strategy in strategies:
            total = 0
            for parsed in parsed_docs:
                chunks = chunk_document(
                    parsed,
                    strategy,
                    size_tokens=self.settings.chunk_size_tokens,
                    overlap_tokens=self.settings.chunk_overlap_tokens,
                )
                index_chunks(self.clients, strategy.value, chunks)
                total += len(chunks)
            counts[strategy.value] = total
            self._ingested.add(strategy.value)
            logger.info("Indexed %d chunks for strategy=%s", total, strategy.value)
        return counts

    def ensure_ingested(self, strategy: ChunkStrategy | None = None) -> None:
        """Ingest on demand in mock mode only.

        In Azure mode the AI Search index is populated out-of-band by the ingest
        job (``scripts/ingest.py`` / ``ingest.yml``), so a running service must
        never re-index on a query.
        """
        strategy = strategy or self.settings.chunk_strategy
        if self.settings.mock_mode and strategy.value not in self._ingested:
            self.ingest([strategy])

    def answer(
        self,
        query: str,
        persona_id: str | None = None,
        *,
        strategy: ChunkStrategy | None = None,
        mode: RetrievalMode | None = None,
    ) -> QueryResult:
        # Import here to avoid a circular import at module load.
        from .flow import run_query

        persona_id = persona_id or self.settings.persona
        strategy = strategy or self.settings.chunk_strategy
        self.ensure_ingested(strategy)
        return run_query(
            self.clients, self.settings, query, persona_id, strategy=strategy, mode=mode
        )
