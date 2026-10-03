"""Search clients: an in-memory hybrid index for mock mode and an Azure AI
Search wrapper for real mode.

The in-memory index implements, by hand, the same retrieval primitives Azure AI
Search gives you — so the ablation is honest:

* **BM25** keyword scoring (classic Okapi BM25 with corpus-wide IDF);
* **vector** cosine similarity;
* **RRF** (Reciprocal Rank Fusion) to combine them for hybrid search;
* a **semantic rerank** stage (mock proxy for the Azure semantic ranker) that
  resolves near-duplicate chunks by rewarding salient query-term matches;
* **security trimming** via an ``allowed_groups`` filter applied *before*
  scoring — never in the prompt.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field

from ..schema import Chunk, RetrievedChunk
from ..settings import Settings
from ..util import tokenize
from .base import SearchClient

_BM25_K1 = 1.5
_BM25_B = 0.75
_RRF_K = 60
_RERANK_CANDIDATES = 20
# Tokens that carry disambiguating meaning (codes, numbers, units): rewarded by
# the semantic reranker so near-duplicate rules (11 kV vs 33 kV) are ordered right.
_SALIENT_RE_HINT = ("kv", "m", "mm", "%lel", "cal/cm2", "bar", "psi")


def _is_salient(token: str) -> bool:
    if any(c.isdigit() for c in token):
        return True
    if "-" in token and any(c.isdigit() for c in token):  # codes like tx-400
        return True
    return token in _SALIENT_RE_HINT


@dataclass
class _Entry:
    chunk: Chunk
    vector: list[float]
    tokens: list[str]


@dataclass
class _Index:
    entries: list[_Entry] = field(default_factory=list)
    df: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    total_len: int = 0

    @property
    def n(self) -> int:
        return len(self.entries)

    @property
    def avgdl(self) -> float:
        return (self.total_len / self.n) if self.n else 0.0


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


def _rrf(rankings: list[list[str]]) -> dict[str, float]:
    """Fuse ranked id-lists with Reciprocal Rank Fusion."""
    fused: dict[str, float] = defaultdict(float)
    for ranking in rankings:
        for rank, cid in enumerate(ranking):
            fused[cid] += 1.0 / (_RRF_K + rank + 1)
    return fused


class InMemorySearchClient(SearchClient):
    def __init__(self) -> None:
        self._indexes: dict[str, _Index] = {}

    def create_or_update_index(self, strategy: str) -> None:
        self._indexes.setdefault(strategy, _Index())

    def upload(self, strategy: str, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        self.create_or_update_index(strategy)
        idx = self._indexes[strategy]
        for chunk, vec in zip(chunks, vectors, strict=False):
            tokens = tokenize(chunk.text + " " + chunk.section_display)
            idx.entries.append(_Entry(chunk=chunk, vector=vec, tokens=tokens))
            idx.total_len += len(tokens)
            for term in set(tokens):
                idx.df[term] += 1

    # --- scoring helpers ---------------------------------------------------- #
    def _bm25_scores(
        self, idx: _Index, candidates: list[_Entry], query_tokens: list[str]
    ) -> dict[str, float]:
        scores: dict[str, float] = {}
        avgdl = idx.avgdl or 1.0
        for entry in candidates:
            tf: dict[str, int] = defaultdict(int)
            for t in entry.tokens:
                tf[t] += 1
            dl = len(entry.tokens)
            score = 0.0
            for term in query_tokens:
                if term not in tf:
                    continue
                df = idx.df.get(term, 0)
                idf = math.log(1 + (idx.n - df + 0.5) / (df + 0.5))
                freq = tf[term]
                denom = freq + _BM25_K1 * (1 - _BM25_B + _BM25_B * dl / avgdl)
                score += idf * (freq * (_BM25_K1 + 1)) / denom
            scores[entry.chunk.chunk_id] = score
        return scores

    def _vector_scores(
        self, candidates: list[_Entry], query_vector: list[float]
    ) -> dict[str, float]:
        return {e.chunk.chunk_id: _cosine(query_vector, e.vector) for e in candidates}

    def _semantic_rerank(
        self, candidates: list[_Entry], query_tokens: list[str]
    ) -> dict[str, float]:
        """Mock semantic ranker: lexical overlap + salient-term boost.

        Rewards chunks that match the *disambiguating* query tokens (numbers,
        units, codes), which is what lets it separate near-duplicate rules.
        """
        qset = set(query_tokens)
        salient = {t for t in qset if _is_salient(t)}
        scores: dict[str, float] = {}
        for entry in candidates:
            tset = set(entry.tokens)
            overlap = len(qset & tset) / (len(qset) or 1)
            salient_match = len(salient & tset)
            scores[entry.chunk.chunk_id] = overlap + 2.0 * salient_match
        return scores

    # --- main search -------------------------------------------------------- #
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
        idx = self._indexes.get(strategy)
        if not idx or not idx.entries:
            return []

        allowed = set(allowed_groups)
        # Security trimming BEFORE scoring.
        candidates = [
            e for e in idx.entries if allowed.intersection(e.chunk.allowed_groups)
        ]
        if not candidates:
            return []

        query_tokens = tokenize(query)
        by_id = {e.chunk.chunk_id: e for e in candidates}

        bm25 = self._bm25_scores(idx, candidates, query_tokens)
        vec = self._vector_scores(candidates, query_vector)

        if mode == "bm25":
            primary = bm25
        elif mode == "vector":
            primary = vec
        else:  # hybrid or hybrid_rerank
            bm25_rank = [cid for cid, _ in sorted(bm25.items(), key=lambda x: -x[1])]
            vec_rank = [cid for cid, _ in sorted(vec.items(), key=lambda x: -x[1])]
            primary = _rrf([bm25_rank, vec_rank])

        ranked = sorted(primary.items(), key=lambda x: -x[1])

        do_rerank = semantic_rerank and mode == "hybrid_rerank"
        if do_rerank:
            top_ids = [cid for cid, _ in ranked[:_RERANK_CANDIDATES]]
            rerank = self._semantic_rerank(
                [by_id[cid] for cid in top_ids], query_tokens
            )
            reranked = sorted(top_ids, key=lambda cid: -rerank[cid])
            return [
                RetrievedChunk(
                    chunk=by_id[cid].chunk,
                    score=primary[cid],
                    rerank_score=rerank[cid],
                )
                for cid in reranked[:top_k]
            ]

        return [
            RetrievedChunk(chunk=by_id[cid].chunk, score=score)
            for cid, score in ranked[:top_k]
        ]


class AzureSearchClient(SearchClient):
    """Azure AI Search wrapper (hybrid + RRF + semantic ranker + filter).

    Imported lazily. The index schema is defined here in code (idempotent
    ``create_or_update``) using endpoint names from the Terraform outputs.
    """

    def __init__(self, settings: Settings) -> None:  # pragma: no cover - real-Azure only
        self.settings = settings
        self._credential = None

    def _cred(self):  # pragma: no cover
        if self._credential is None:
            from azure.identity import DefaultAzureCredential

            self._credential = DefaultAzureCredential(
                managed_identity_client_id=self.settings.managed_identity_client_id or None
            )
        return self._credential

    def create_or_update_index(self, strategy: str) -> None:  # pragma: no cover
        from azure.search.documents.indexes import SearchIndexClient
        from azure.search.documents.indexes.models import (
            HnswAlgorithmConfiguration,
            SearchableField,
            SearchField,
            SearchFieldDataType,
            SearchIndex,
            SemanticConfiguration,
            SemanticField,
            SemanticPrioritizedFields,
            SemanticSearch,
            SimpleField,
            VectorSearch,
            VectorSearchProfile,
        )

        name = self.settings.index_name_from_strategy(strategy)
        fields = [
            SimpleField(name="chunk_id", type=SearchFieldDataType.String, key=True),
            SearchableField(name="text", type=SearchFieldDataType.String),
            SearchableField(name="doc", type=SearchFieldDataType.String, filterable=True),
            SearchableField(
                name="section", type=SearchFieldDataType.String, filterable=True
            ),
            SimpleField(name="page", type=SearchFieldDataType.Int32, filterable=True),
            SimpleField(name="domain", type=SearchFieldDataType.String, filterable=True),
            SimpleField(
                name="content_type", type=SearchFieldDataType.String, filterable=True
            ),
            SimpleField(
                name="effective_date", type=SearchFieldDataType.String, filterable=True
            ),
            SimpleField(
                name="allowed_groups",
                type=SearchFieldDataType.Collection(SearchFieldDataType.String),
                filterable=True,
            ),
            SearchField(
                name="embedding",
                type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
                searchable=True,
                vector_search_dimensions=self.settings.embedding_dim,
                vector_search_profile_name="hnsw-profile",
            ),
        ]
        vector_search = VectorSearch(
            algorithms=[HnswAlgorithmConfiguration(name="hnsw")],
            profiles=[VectorSearchProfile(name="hnsw-profile", algorithm_configuration_name="hnsw")],
        )
        semantic = SemanticSearch(
            configurations=[
                SemanticConfiguration(
                    name="semantic-config",
                    prioritized_fields=SemanticPrioritizedFields(
                        content_fields=[SemanticField(field_name="text")]
                    ),
                )
            ]
        )
        index = SearchIndex(
            name=name,
            fields=fields,
            vector_search=vector_search,
            semantic_search=semantic,
        )
        client = SearchIndexClient(self.settings.search_endpoint, self._cred())
        client.create_or_update_index(index)

    def upload(self, strategy, chunks, vectors):  # pragma: no cover
        from azure.search.documents import SearchClient as AzSearchClient

        name = self.settings.index_name_from_strategy(strategy)
        client = AzSearchClient(self.settings.search_endpoint, name, self._cred())
        docs = []
        for c, v in zip(chunks, vectors, strict=False):
            docs.append(
                {
                    "chunk_id": c.chunk_id,
                    "text": c.text,
                    "doc": c.doc,
                    "section": c.section_display,
                    "page": c.page,
                    "domain": c.domain.value,
                    "content_type": c.content_type.value,
                    "effective_date": c.effective_date,
                    "allowed_groups": c.allowed_groups,
                    "embedding": v,
                }
            )
        client.merge_or_upload_documents(docs)

    def search(  # pragma: no cover
        self,
        strategy,
        query,
        query_vector,
        *,
        allowed_groups,
        mode,
        top_k,
        semantic_rerank,
    ):
        from azure.search.documents import SearchClient as AzSearchClient
        from azure.search.documents.models import VectorizedQuery

        name = self.settings.index_name_from_strategy(strategy)
        client = AzSearchClient(self.settings.search_endpoint, name, self._cred())
        # Security trimming as an OData filter (never prompt-only).
        groups = ",".join(allowed_groups)
        flt = f"allowed_groups/any(g: search.in(g, '{groups}'))"
        kwargs: dict = {"filter": flt, "top": top_k}
        if mode in ("bm25", "hybrid", "hybrid_rerank"):
            kwargs["search_text"] = query
        if mode in ("vector", "hybrid", "hybrid_rerank"):
            kwargs["vector_queries"] = [
                VectorizedQuery(vector=query_vector, k_nearest_neighbors=top_k, fields="embedding")
            ]
        if semantic_rerank and mode == "hybrid_rerank":
            kwargs["query_type"] = "semantic"
            kwargs["semantic_configuration_name"] = "semantic-config"
        results = client.search(**kwargs)
        out: list[RetrievedChunk] = []
        for r in results:
            chunk = Chunk(
                chunk_id=r["chunk_id"],
                doc=r["doc"],
                domain=r["domain"],
                section_path=[r.get("section", "")],
                page=r["page"],
                content_type=r.get("content_type", "text"),
                effective_date=r.get("effective_date", "2026-01-01"),
                allowed_groups=r.get("allowed_groups", []),
                strategy=strategy,
                text=r["text"],
            )
            out.append(
                RetrievedChunk(
                    chunk=chunk,
                    score=r.get("@search.score", 0.0),
                    rerank_score=r.get("@search.reranker_score"),
                )
            )
        return out
