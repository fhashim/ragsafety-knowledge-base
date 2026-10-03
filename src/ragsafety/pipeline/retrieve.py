"""Retrieve (+ rerank) stage.

Embeds the query, then runs hybrid retrieval with the ``allowed_groups`` security
filter and (for ``hybrid_rerank``) the semantic reranker. Rerank is expressed as
a flag on the search call so the same code path serves mock and Azure.
"""

from __future__ import annotations

from ..clients import Clients
from ..schema import RetrievedChunk
from ..settings import RetrievalMode


def retrieve(
    clients: Clients,
    *,
    strategy: str,
    query: str,
    allowed_groups: list[str],
    mode: RetrievalMode,
    top_k: int,
) -> tuple[list[RetrievedChunk], int]:
    """Return (retrieved_chunks, embedding_tokens_used)."""
    from ..util import count_tokens

    query_vector = clients.embeddings.embed([query])[0]
    results = clients.search.search(
        strategy,
        query,
        query_vector,
        allowed_groups=allowed_groups,
        mode=mode.value,
        top_k=top_k,
        semantic_rerank=(mode == RetrievalMode.HYBRID_RERANK),
    )
    return results, count_tokens(query)
