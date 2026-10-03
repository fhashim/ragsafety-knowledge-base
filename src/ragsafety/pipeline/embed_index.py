"""Embed + index stage.

Embeds each chunk's text and upserts it into the per-strategy index. The index
schema is created idempotently (``create_or_update_index``). Returns the number
of embedding tokens consumed so the ingest job can report cost.
"""

from __future__ import annotations

from ..clients import Clients
from ..schema import Chunk
from ..util import count_tokens


def index_chunks(clients: Clients, strategy: str, chunks: list[Chunk]) -> int:
    clients.search.create_or_update_index(strategy)
    if not chunks:
        return 0
    texts = [c.text for c in chunks]
    vectors = clients.embeddings.embed(texts)
    clients.search.upload(strategy, chunks, vectors)
    return sum(count_tokens(t) for t in texts)
