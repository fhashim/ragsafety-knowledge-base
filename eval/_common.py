"""Shared helpers for the eval and ablation scripts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ragsafety.app import RagSafetyApp
from ragsafety.schema import QueryResult
from ragsafety.settings import ChunkStrategy, RetrievalMode, Settings

EVAL_DIR = Path(__file__).resolve().parent
GOLDEN = EVAL_DIR / "golden_set.jsonl"


@dataclass
class GoldenItem:
    id: str
    category: str
    persona: str
    query: str
    expected_facts: list[str]
    expected_doc: str | None
    expected_page: int
    expected_outcome: str
    needs_web: bool = False


def load_golden(path: Path = GOLDEN) -> list[GoldenItem]:
    items = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        d = json.loads(line)
        items.append(
            GoldenItem(
                id=d["id"],
                category=d["category"],
                persona=d["persona"],
                query=d["query"],
                expected_facts=[f.lower() for f in d.get("expected_facts", [])],
                expected_doc=d.get("expected_doc"),
                expected_page=int(d.get("expected_page", 0)),
                expected_outcome=d["expected_outcome"],
                needs_web=bool(d.get("needs_web", False)),
            )
        )
    return items


def build_app(
    strategy: ChunkStrategy,
    mode: RetrievalMode,
    *,
    enable_web: bool = True,
) -> RagSafetyApp:
    settings = Settings(
        mock_mode=True,
        chunk_strategy=strategy,
        retrieval_mode=mode,
        enable_bing_grounding=enable_web,
        log_level="ERROR",
    )
    app = RagSafetyApp(settings=settings)
    app.ingest([strategy])
    return app


def recall_hit(result: QueryResult, item: GoldenItem) -> bool:
    if not item.expected_doc:
        return True
    return any(cid.startswith(item.expected_doc) for cid in result.audit.retrieved_chunk_ids)


def rank_of_expected(result: QueryResult, item: GoldenItem) -> int | None:
    """1-based rank of the first retrieved chunk from the expected doc."""
    if not item.expected_doc:
        return None
    for i, cid in enumerate(result.audit.retrieved_chunk_ids):
        if cid.startswith(item.expected_doc):
            return i + 1
    return None


def answer_text(result: QueryResult) -> str:
    if not result.checklist:
        return ""
    parts = []
    for it in result.checklist.items:
        parts.append(it.instruction)
        if it.value:
            parts.append(it.value)
    return " ".join(parts).lower()


def facts_present(result: QueryResult, item: GoldenItem) -> float:
    if not item.expected_facts:
        return 1.0
    text = answer_text(result)
    hit = sum(1 for f in item.expected_facts if f.replace(" ", "") in text.replace(" ", ""))
    return hit / len(item.expected_facts)


def citation_accuracy(result: QueryResult, item: GoldenItem) -> float:
    if not item.expected_facts or not result.checklist:
        return 1.0
    hits = 0
    for fact in item.expected_facts:
        norm = fact.replace(" ", "")
        for it in result.checklist.items:
            line = (it.instruction + " " + (it.value or "")).lower().replace(" ", "")
            doc_ok = (item.expected_doc is None) or any(
                c.doc == item.expected_doc for c in it.citations
            )
            if norm in line and doc_ok:
                hits += 1
                break
    return hits / len(item.expected_facts)


def valued_items_cited(result: QueryResult) -> bool:
    if not result.checklist:
        return True
    return all(it.citations for it in result.checklist.items if it.value)


def retrieve_for(app, item: GoldenItem, strategy: ChunkStrategy, mode: RetrievalMode, top_k: int = 5):
    """Retrieve chunks for an item (chunk-level view used by the ablation)."""
    from ragsafety.pipeline.retrieve import retrieve
    from ragsafety.security import persona_groups

    rewrite, _ = app.clients.chat.rewrite(item.query)
    groups = persona_groups(item.persona)
    chunks, _ = retrieve(
        app.clients,
        strategy=strategy.value,
        query=rewrite.rewritten_query,
        allowed_groups=groups,
        mode=mode,
        top_k=top_k,
    )
    return chunks


def fact_rank(chunks, item: GoldenItem) -> int | None:
    """1-based rank of the first retrieved chunk that actually contains the fact.

    Chunk-level (not doc-level) so the ablation can distinguish retrieval modes
    even on a small corpus.
    """
    for i, rc in enumerate(chunks):
        t = rc.chunk.text.lower().replace(" ", "")
        if item.expected_facts:
            if any(f.replace(" ", "") in t for f in item.expected_facts):
                return i + 1
        elif item.expected_doc and rc.chunk.chunk_id.startswith(item.expected_doc):
            return i + 1
    return None


def index_profile(app, strategy: ChunkStrategy) -> tuple[int, float]:
    """(chunk count, avg tokens/chunk) for the in-memory index of a strategy."""
    from ragsafety.util import count_tokens

    idx = app.clients.search._indexes.get(strategy.value)
    if not idx or not idx.entries:
        return 0, 0.0
    toks = [count_tokens(e.chunk.text) for e in idx.entries]
    return len(toks), sum(toks) / len(toks)


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = max(0, min(len(s) - 1, int(round((pct / 100.0) * (len(s) - 1)))))
    return s[k]
