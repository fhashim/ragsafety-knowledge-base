"""Embedding clients.

``MockEmbeddingClient`` is deterministic and dependency-free. It combines two
signals so the retrieval ablation shows a *real* difference:

* a **lexical** component (each token hashed into a dimension) — lets exact
  tokens match, but behaves like bag-of-words;
* a **concept** component (phrases from ``config/concepts.yaml`` activate stable
  dimensions) — lets paraphrases align even with no shared tokens.

Because concepts are weighted higher than raw tokens, a conceptual/paraphrased
query lands near the right chunk in vector space (vectors beat BM25), while an
exact equipment code like ``TX-400`` — which is *not* a concept — relies on the
lexical signal and is better served by BM25. That asymmetry is the whole point
of the ablation.
"""

from __future__ import annotations

import hashlib
import math

from ..concepts import detect_concepts
from ..settings import Settings, load_concepts
from ..util import tokenize
from .base import EmbeddingClient

_LEXICAL_WEIGHT = 1.0
_CONCEPT_WEIGHT = 3.0
_CONCEPT_DIMS = 8  # dimensions activated per concept


def _stable_int(key: str) -> int:
    return int(hashlib.sha256(key.encode("utf-8")).hexdigest(), 16)


class MockEmbeddingClient(EmbeddingClient):
    def __init__(self, dim: int = 256) -> None:
        self.dim = dim
        # Pre-expand the concept lexicon: phrase -> concept name.
        self._concepts: dict[str, list[str]] = load_concepts()
        # Pre-compute the dimensions each concept activates.
        self._concept_dims: dict[str, list[tuple[int, float]]] = {}
        for concept in self._concepts:
            dims: list[tuple[int, float]] = []
            seed = _stable_int(concept)
            for i in range(_CONCEPT_DIMS):
                h = _stable_int(f"{concept}:{i}:{seed}")
                idx = h % self.dim
                sign = 1.0 if (h >> 8) & 1 else -1.0
                dims.append((idx, sign))
            self._concept_dims[concept] = dims

    def _embed_one(self, text: str) -> list[float]:
        vec = [0.0] * self.dim

        # Lexical component.
        for tok in tokenize(text):
            idx = _stable_int(tok) % self.dim
            sign = 1.0 if (_stable_int(tok) >> 16) & 1 else -1.0
            vec[idx] += _LEXICAL_WEIGHT * sign

        # Concept component (semantic signal).
        for concept in detect_concepts(text):
            for idx, sign in self._concept_dims[concept]:
                vec[idx] += _CONCEPT_WEIGHT * sign

        # L2 normalize.
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]


class AzureEmbeddingClient(EmbeddingClient):
    """Real embeddings via the Foundry/Azure OpenAI embedding deployment.

    Imported lazily so mock mode never needs the azure/openai packages.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.dim = settings.embedding_dim
        self._client = None  # built on first use

    def _ensure_client(self):  # pragma: no cover - real-Azure only
        if self._client is not None:
            return
        from azure.identity import DefaultAzureCredential, get_bearer_token_provider
        from openai import AzureOpenAI

        token_provider = get_bearer_token_provider(
            DefaultAzureCredential(
                managed_identity_client_id=self.settings.managed_identity_client_id or None
            ),
            "https://cognitiveservices.azure.com/.default",
        )
        # VERIFY: confirm api_version against your Foundry/Azure OpenAI deployment.
        self._client = AzureOpenAI(
            azure_endpoint=self.settings.foundry_endpoint,
            azure_ad_token_provider=token_provider,
            api_version="2024-10-21",
        )

    def embed(self, texts: list[str]) -> list[list[float]]:  # pragma: no cover
        self._ensure_client()
        resp = self._client.embeddings.create(
            model=self.settings.embedding_deployment,
            input=texts,
            dimensions=self.dim,
        )
        return [d.embedding for d in resp.data]
