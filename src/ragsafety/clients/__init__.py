"""Client factory.

``build_clients(settings)`` returns a :class:`Clients` bundle wired for either
mock or Azure mode. The pipeline depends on this bundle, never on concrete
classes, so ``MOCK_MODE`` is the only switch.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..settings import Settings
from .base import (
    AuditClient,
    ChatClient,
    ContentSafetyClient,
    DocIntelClient,
    EmbeddingClient,
    SearchClient,
    WebGroundingClient,
)


@dataclass
class Clients:
    embeddings: EmbeddingClient
    chat: ChatClient
    search: SearchClient
    docintel: DocIntelClient
    content_safety: ContentSafetyClient
    web: WebGroundingClient
    audit: AuditClient


def build_clients(settings: Settings) -> Clients:
    if settings.mock_mode:
        from .audit import LocalAuditClient
        from .contentsafety import MockContentSafetyClient
        from .docintel import MockDocIntelClient
        from .embeddings import MockEmbeddingClient
        from .llm import MockChatClient
        from .search import InMemorySearchClient
        from .web import MockWebGroundingClient

        return Clients(
            embeddings=MockEmbeddingClient(dim=settings.embedding_dim),
            chat=MockChatClient(settings),
            search=InMemorySearchClient(),
            docintel=MockDocIntelClient(),
            content_safety=MockContentSafetyClient(settings),
            web=MockWebGroundingClient(settings),
            audit=LocalAuditClient(settings),
        )

    # Real Azure implementations (imported lazily to keep mock mode dependency-free).
    from .audit import AzureAuditClient
    from .contentsafety import AzureContentSafetyClient
    from .docintel import AzureDocIntelClient
    from .embeddings import AzureEmbeddingClient
    from .llm import AzureChatClient
    from .search import AzureSearchClient
    from .web import AzureWebGroundingClient

    return Clients(
        embeddings=AzureEmbeddingClient(settings),
        chat=AzureChatClient(settings),
        search=AzureSearchClient(settings),
        docintel=AzureDocIntelClient(settings),
        content_safety=AzureContentSafetyClient(settings),
        web=AzureWebGroundingClient(settings),
        audit=AzureAuditClient(settings),
    )
