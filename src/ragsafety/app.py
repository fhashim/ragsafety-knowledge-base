"""High-level application: ingest the knowledge base, then answer queries.

A single ``RagSafetyApp`` instance holds the clients (and, in mock mode, the
in-memory index), so ingest once and answer many times.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from .clients import Clients, build_clients
from .pipeline.chunk import chunk_document
from .pipeline.embed_index import index_chunks
from .pipeline.parse import parse_document
from .schema import QueryResult
from .settings import DATA_DIR, REPO_ROOT, ChunkStrategy, RetrievalMode, Settings, get_settings
from .tracing import configure_tracing

logger = logging.getLogger("ragsafety.app")

RAW_DIR = DATA_DIR / "raw"
MANIFEST = DATA_DIR / "manifest.json"


def _manifest_meta() -> dict[str, dict]:
    """Map repo-relative source path -> {doc, domain, allowed_groups} from manifest."""
    if not MANIFEST.exists():
        return {}
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return {m["source"]: m for m in data}


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
        meta = _manifest_meta()
        parsed_docs = []
        for s in sources:
            parsed = parse_document(self.clients, s)
            # Overlay per-document metadata from data/manifest.json. The mock
            # layout sidecars already carry this, but the real Document
            # Intelligence output does not know a document's domain or
            # allowed_groups, so the manifest is the source of truth (and gives
            # clean display names instead of file names).
            rel = str(Path(s).resolve().relative_to(REPO_ROOT))
            if rel in meta:
                m = meta[rel]
                parsed.doc = m.get("doc", parsed.doc)
                parsed.domain = m.get("domain", parsed.domain)
                parsed.allowed_groups = m.get("allowed_groups", parsed.allowed_groups)
            parsed_docs.append(parsed)
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
