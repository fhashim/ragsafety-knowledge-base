"""Query flow orchestration.

Runs the eight stages, each in its own OpenTelemetry span:

    guardrail_in -> rewrite -> clarify -> retrieve -> rerank -> generate
                 -> guardrail_out -> audit

Outcomes:
    answered   — a grounded checklist was produced and passed the output guardrail
    clarified  — the hazard could not be scoped; a clarifying question is returned
    refused    — nothing retrievable for this user (unauthorized or out-of-scope);
                 the reply never reveals whether a restricted document exists
    blocked    — the input/retrieved/output guardrail rejected the request
"""

from __future__ import annotations

import logging
import time
import uuid

from .clients import Clients
from .cost import cost_usd
from .pipeline.generate import generate_checklist
from .pipeline.retrieve import retrieve
from .schema import (
    AuditRecord,
    Checklist,
    QueryResult,
    TokenUsage,
)
from .security import can_access_domain, persona_groups
from .settings import ChunkStrategy, RetrievalMode, Settings, load_bing_allowlist
from .tracing import (
    GEN_AI_REQUEST_MODEL,
    GEN_AI_USAGE_INPUT_TOKENS,
    GEN_AI_USAGE_OUTPUT_TOKENS,
    configure_tracing,
    stage_span,
)
from .util import answer_hash, today_utc

logger = logging.getLogger("ragsafety.flow")

_REFUSAL_MESSAGE = (
    "I can't provide a checklist for that request with the access you have. If you "
    "believe you need this information, contact your supervisor or the HSE team. "
    "Do not proceed with the task until you have the correct, authorized procedure."
)


def run_query(
    clients: Clients,
    settings: Settings,
    query: str,
    persona_id: str,
    *,
    strategy: ChunkStrategy | None = None,
    mode: RetrievalMode | None = None,
) -> QueryResult:
    configure_tracing(settings)
    strategy = strategy or settings.chunk_strategy
    mode = mode or settings.retrieval_mode
    trace_id = uuid.uuid4().hex
    started = time.perf_counter()
    groups = persona_groups(persona_id)

    usages: list[TokenUsage] = []
    embedding_tokens = 0
    retrieved = []
    rewritten = query
    clarification_asked = False
    guard_cats: list[str] = []

    def _finish(outcome: str, checklist: Checklist | None, message: str) -> QueryResult:
        latency_ms = (time.perf_counter() - started) * 1000.0
        total_cost = sum(cost_usd(u) for u in usages)
        tokens_in = sum(u.prompt_tokens for u in usages) + embedding_tokens
        tokens_out = sum(u.completion_tokens for u in usages)
        ahash = answer_hash(checklist.model_dump_json()) if checklist else answer_hash(message)
        record = AuditRecord(
            trace_id=trace_id,
            date=today_utc(),
            user=persona_id,
            persona=persona_id,
            original_query=query,
            rewritten_query=rewritten,
            clarification_asked=clarification_asked,
            retrieved_chunk_ids=[rc.chunk.chunk_id for rc in retrieved],
            retrieved_scores=[round(rc.final_score, 6) for rc in retrieved],
            model=settings.chat_large_deployment,
            deployment=settings.chat_large_deployment,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=round(total_cost, 8),
            latency_ms=round(latency_ms, 2),
            guardrail_in_allowed=(outcome != "blocked" or "input" not in guard_cats),
            guardrail_out_allowed=(outcome != "blocked" or "output" not in guard_cats),
            guardrail_categories=guard_cats,
            answer_hash=ahash,
            outcome=outcome,
        )
        with stage_span("audit", **{"ragsafety.outcome": outcome}):
            clients.audit.write(record)
        return QueryResult(
            outcome=outcome,
            checklist=checklist,
            clarification=None,
            message=message,
            trace_id=trace_id,
            audit=record,
        )

    # 1) Input guardrail -----------------------------------------------------
    with stage_span("guardrail_in") as span:
        verdict = clients.content_safety.check_input(query)
        span.set_attribute("ragsafety.guardrail.allowed", verdict.allowed)
        if not verdict.allowed:
            guard_cats = ["input", *verdict.categories]
            logger.info("Input blocked: %s", verdict.categories)
            return _finish("blocked", None, verdict.reason)

    # 2) Rewrite -------------------------------------------------------------
    with stage_span("rewrite") as span:
        rewrite_result, usage = clients.chat.rewrite(query)
        usages.append(usage)
        rewritten = rewrite_result.rewritten_query
        span.set_attribute(GEN_AI_REQUEST_MODEL, usage.deployment)
        span.set_attribute(GEN_AI_USAGE_INPUT_TOKENS, usage.prompt_tokens)
        span.set_attribute(GEN_AI_USAGE_OUTPUT_TOKENS, usage.completion_tokens)
        span.set_attribute("ragsafety.rewritten_query", rewritten)

    # 3) Clarify -------------------------------------------------------------
    with stage_span("clarify") as span:
        clarification, usage = clients.chat.clarify(rewrite_result)
        usages.append(usage)
        span.set_attribute("ragsafety.clarification_needed", clarification.needed)
        if clarification.needed:
            clarification_asked = True
            result = _finish("clarified", None, clarification.question)
            result.clarification = clarification
            return result

    # Authorization: if the request targets a restricted domain the user is not
    # in, refuse and log the attempt (without revealing the document exists).
    # The AI Search filter below is still the primary boundary (defense in depth).
    inferred = rewrite_result.slots.domain.value if rewrite_result.slots.domain else None
    if not can_access_domain(groups, inferred):
        guard_cats = ["unauthorized_domain"]
        logger.info("Unauthorized domain attempt: persona=%s domain=%s", persona_id, inferred)
        return _finish("refused", None, _REFUSAL_MESSAGE)

    # 4) Retrieve (+ 5 rerank, as a flag) ------------------------------------
    with stage_span("retrieve", **{"ragsafety.strategy": strategy.value, "ragsafety.mode": mode.value}) as span:
        retrieved, emb_tokens = retrieve(
            clients,
            strategy=strategy.value,
            query=rewritten,
            allowed_groups=groups,
            mode=mode,
            top_k=settings.top_k,
        )
        embedding_tokens += emb_tokens
        span.set_attribute("ragsafety.retrieved_count", len(retrieved))

    with stage_span("rerank") as span:
        span.set_attribute("ragsafety.reranked", mode == RetrievalMode.HYBRID_RERANK)
        span.set_attribute("ragsafety.retrieved_count", len(retrieved))

    # Indirect-injection guardrail on retrieved documents.
    inj = clients.content_safety.check_retrieved(retrieved)
    if not inj.allowed:
        guard_cats = ["retrieved", *inj.categories]
        logger.info("Retrieved content blocked: %s", inj.categories)
        return _finish("blocked", None, inj.reason)

    # Nothing retrievable for this user => refuse without revealing existence.
    if not retrieved:
        return _finish("refused", None, _REFUSAL_MESSAGE)

    # Optional web grounding (labeled separately; internal policy wins).
    web_results = []
    if settings.enable_bing_grounding:
        web_results = clients.web.search(rewritten, load_bing_allowlist())

    # 6) Generate ------------------------------------------------------------
    with stage_span("generate") as span:
        checklist, usage = generate_checklist(
            clients, rewrite_result, retrieved, web_results, persona_id
        )
        usages.append(usage)
        span.set_attribute(GEN_AI_REQUEST_MODEL, usage.deployment)
        span.set_attribute(GEN_AI_USAGE_INPUT_TOKENS, usage.prompt_tokens)
        span.set_attribute(GEN_AI_USAGE_OUTPUT_TOKENS, usage.completion_tokens)

    # 7) Output guardrail ----------------------------------------------------
    with stage_span("guardrail_out") as span:
        out_verdict = clients.content_safety.check_output(checklist, retrieved)
        span.set_attribute("ragsafety.guardrail.allowed", out_verdict.allowed)
        if not out_verdict.allowed:
            guard_cats = ["output", *out_verdict.categories]
            logger.info("Output blocked: %s", out_verdict.categories)
            return _finish("blocked", None, out_verdict.reason)

    # The specific value the technician asked for could not be grounded in any
    # source they are allowed to see (an unauthorized or out-of-scope request).
    # Refuse with a stop-work instruction; never reveal that a restricted
    # document exists. The attempt is still audited.
    if checklist.unsupported_claims:
        return _finish("refused", None, _REFUSAL_MESSAGE)

    return _finish("answered", checklist, "")
