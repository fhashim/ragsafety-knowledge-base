"""Chunking strategy behaviour, including the planted traps."""

from __future__ import annotations

from ragsafety.clients.docintel import MockDocIntelClient
from ragsafety.pipeline.chunk import chunk_document
from ragsafety.schema import ContentType
from ragsafety.settings import DATA_DIR, ChunkStrategy

HV = str(DATA_DIR / "raw" / "HV_Substation_Safety_Policy.pdf")


def _parse():
    return MockDocIntelClient().parse(HV)


def test_strategies_produce_chunks():
    parsed = _parse()
    for strat in ChunkStrategy:
        chunks = chunk_document(parsed, strat, size_tokens=60, overlap_tokens=20)
        assert chunks, f"{strat} produced no chunks"
        assert all(c.strategy == strat.value for c in chunks)


def test_section_aware_keeps_tables_whole_and_merges_page_spans():
    parsed = _parse()
    chunks = chunk_document(parsed, ChunkStrategy.SECTION_AWARE, size_tokens=60, overlap_tokens=20)
    table_chunks = [c for c in chunks if c.content_type == ContentType.TABLE]
    assert table_chunks, "expected table chunks"
    # The arc-flash table spans pages 2-3 (CAT 1..CAT 4). Section-aware merges
    # the continuation, so one table chunk holds all four categories.
    merged = [c for c in table_chunks if "CAT 1" in c.text and "CAT 4" in c.text]
    assert merged, "page-spanning arc-flash table was not merged"


def test_section_aware_prepends_heading_path():
    parsed = _parse()
    chunks = chunk_document(parsed, ChunkStrategy.SECTION_AWARE, size_tokens=60, overlap_tokens=20)
    assert any(c.text.startswith("Section:") for c in chunks)


def test_section_aware_preserves_heading_context_for_values():
    """Trap #1 (the split rule), shown via context: section-aware keeps the
    elevated-clearance value attached to its heading (TX-400 / elevated voltage),
    so a retrieved value never loses the condition it applies to.
    """
    parsed = _parse()
    chunks = chunk_document(parsed, ChunkStrategy.SECTION_AWARE, size_tokens=60, overlap_tokens=20)
    val_chunks = [c for c in chunks if "1.20 m" in c.text.lower()]
    assert val_chunks, "expected a chunk with the elevated-clearance value"
    assert all("tx-400" in c.text.lower() for c in val_chunks)


def test_fixed_chunking_drops_heading_context():
    """Naive fixed chunking strips structure — no chunk carries its heading path."""
    parsed = _parse()
    chunks = chunk_document(parsed, ChunkStrategy.FIXED_NO_OVERLAP, size_tokens=60, overlap_tokens=0)
    assert chunks
    assert all(not c.text.startswith("Section:") for c in chunks)


def test_overlap_shares_tokens_between_adjacent_chunks():
    """Overlap means adjacent windows share their boundary tokens (so a rule that
    straddles a boundary survives in at least one window); no-overlap does not."""
    parsed = _parse()
    no = chunk_document(parsed, ChunkStrategy.FIXED_NO_OVERLAP, size_tokens=60, overlap_tokens=0)
    ov = chunk_document(parsed, ChunkStrategy.FIXED_OVERLAP, size_tokens=60, overlap_tokens=20)
    assert len(ov) >= len(no)  # overlap produces more (overlapping) windows
    w0, w1 = ov[0].text.split(), ov[1].text.split()
    assert set(w0[-20:]) & set(w1[:20]), "adjacent overlap windows should share tokens"
