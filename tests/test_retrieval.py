"""Retrieval behaviour: the BM25-vs-vector asymmetry and security trimming."""

from __future__ import annotations

from ragsafety.clients.embeddings import MockEmbeddingClient
from ragsafety.clients.search import InMemorySearchClient
from ragsafety.schema import Chunk, ContentType, Domain


def _index():
    emb = MockEmbeddingClient(dim=256)
    search = InMemorySearchClient()
    chunks = [
        Chunk(
            chunk_id="code",
            doc="HV",
            domain=Domain.ELECTRICAL,
            page=1,
            content_type=ContentType.TEXT,
            allowed_groups=["grp-electrical"],
            strategy="t",
            text="Confirm breaker CB-22 is open and racked out before work.",
        ),
        Chunk(
            chunk_id="paraphrase",
            doc="HSE",
            domain=Domain.SHARED,
            page=1,
            content_type=ContentType.TEXT,
            allowed_groups=["grp-all"],
            strategy="t",
            text="Select appropriate hand protection; insulating gloves must be class rated.",
        ),
        Chunk(
            chunk_id="distractor",
            doc="HSE",
            domain=Domain.SHARED,
            page=2,
            content_type=ContentType.TEXT,
            allowed_groups=["grp-all"],
            strategy="t",
            text="Fatigue management requires a rest break every two hours on shift.",
        ),
    ]
    vectors = emb.embed([c.text for c in chunks])
    search.create_or_update_index("t")
    search.upload("t", chunks, vectors)
    return emb, search


def _top_id(search, emb, query, mode, groups=("grp-electrical", "grp-all")):
    qv = emb.embed([query])[0]
    res = search.search(
        "t", query, qv, allowed_groups=list(groups), mode=mode, top_k=1, semantic_rerank=False
    )
    return res[0].chunk.chunk_id if res else None


def test_bm25_beats_vector_on_exact_code():
    emb, search = _index()
    # The exact code is not a concept, so BM25 nails it where vectors are weak.
    assert _top_id(search, emb, "CB-22", "bm25") == "code"


def test_vector_beats_bm25_on_paraphrase():
    emb, search = _index()
    # "hand protection" shares no tokens with "gloves"; the concept embedding
    # bridges them, so vector search finds the glove chunk.
    assert _top_id(search, emb, "what gloves should I wear", "vector") == "paraphrase"


def test_security_trimming_hides_other_group_docs():
    emb, search = _index()
    qv = emb.embed(["breaker CB-22"])[0]
    # A gas-only user must not see the electrical chunk.
    res = search.search(
        "t", "breaker CB-22", qv, allowed_groups=["grp-gas", "grp-all"],
        mode="hybrid", top_k=5, semantic_rerank=False,
    )
    ids = {r.chunk.chunk_id for r in res}
    assert "code" not in ids
    assert ids <= {"paraphrase", "distractor"}
