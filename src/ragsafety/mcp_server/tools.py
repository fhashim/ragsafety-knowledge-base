"""MCP tool implementations (pure functions, no transport dependency).

Keeping the logic here — separate from the MCP server wiring (MCPServer) in ``server.py`` — means
the tools are unit-testable in mock mode without the ``mcp`` package, and the
identity/group enforcement is in one place.

Identity: every tool resolves the caller's groups and passes them to retrieval as
the ``allowed_groups`` filter. In production the Container App validates the
caller's token and forwards the group claims; here ``Identity`` can be built from
forwarded claims or, for the demo, from a persona id.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..app import RagSafetyApp
from ..pipeline.retrieve import retrieve
from ..security import groups_for_claims, persona_groups, persona_meta
from ..settings import ChunkStrategy, RetrievalMode


@dataclass
class Identity:
    user: str
    persona: str
    groups: list[str]


def resolve_identity(persona: str, groups: list[str] | None = None) -> Identity:
    """Build an Identity from forwarded group claims, or fall back to a persona."""
    if groups:
        return Identity(user=persona or "caller", persona=persona or "", groups=groups_for_claims(groups))
    persona_meta(persona)  # validates the persona exists (raises UnknownPersona)
    return Identity(user=persona, persona=persona, groups=persona_groups(persona))


def _resolve_strategy(app: RagSafetyApp, strategy: str | None) -> ChunkStrategy:
    """Coerce an optional strategy string, defaulting to the server setting."""
    if not strategy:
        return app.settings.chunk_strategy
    try:
        return ChunkStrategy(strategy)
    except ValueError as exc:
        raise ValueError(f"unknown chunk strategy: {strategy!r}") from exc


def _resolve_mode(app: RagSafetyApp, mode: str | None, default: RetrievalMode) -> RetrievalMode:
    """Coerce an optional retrieval-mode string, defaulting as given."""
    if not mode:
        return default
    try:
        return RetrievalMode(mode)
    except ValueError as exc:
        raise ValueError(f"unknown retrieval mode: {mode!r}") from exc


def get_safety_checklist_impl(
    app: RagSafetyApp,
    identity: Identity,
    query: str,
    strategy: str | None = None,
    mode: str | None = None,
) -> dict:
    """Produce a grounded pre-task safety checklist for the caller.

    ``strategy`` / ``mode`` are optional ablation overrides; when omitted the
    server's configured defaults are used.
    """
    chunk_strategy = _resolve_strategy(app, strategy)
    retrieval_mode = _resolve_mode(app, mode, app.settings.retrieval_mode)
    result = app.answer(query, identity.persona, strategy=chunk_strategy, mode=retrieval_mode)
    out: dict = {"outcome": result.outcome, "trace_id": result.trace_id}
    if result.outcome == "answered" and result.checklist:
        out["checklist"] = result.checklist.model_dump(mode="json")
    elif result.outcome == "clarified" and result.clarification:
        out["clarification"] = result.clarification.model_dump(mode="json")
    else:
        out["message"] = result.message
    return out


def search_policies_impl(
    app: RagSafetyApp,
    identity: Identity,
    query: str,
    top_k: int = 5,
    strategy: str | None = None,
    mode: str | None = None,
) -> list[dict]:
    """Security-trimmed policy search. Returns chunk summaries the caller may see.

    ``strategy`` / ``mode`` are optional ablation overrides; when omitted the
    server's configured strategy and the ``hybrid_rerank`` mode are used.
    """
    chunk_strategy = _resolve_strategy(app, strategy)
    retrieval_mode = _resolve_mode(app, mode, RetrievalMode.HYBRID_RERANK)
    app.ensure_ingested(chunk_strategy)  # idempotent; no-op in Azure mode
    chunks, _ = retrieve(
        app.clients,
        strategy=chunk_strategy.value,
        query=query,
        allowed_groups=identity.groups,
        mode=retrieval_mode,
        top_k=top_k,
    )
    return [
        {
            "doc": rc.chunk.doc,
            "section": rc.chunk.section_display,
            "page": rc.chunk.page,
            "content_type": rc.chunk.content_type.value,
            "score": round(rc.final_score, 4),
            "snippet": rc.chunk.text[:300],
        }
        for rc in chunks
    ]


def get_document_section_impl(
    app: RagSafetyApp,
    identity: Identity,
    doc: str,
    section: str = "",
    strategy: str | None = None,
    mode: str | None = None,
) -> dict:
    """Return the text of a named document section the caller is allowed to read.

    If the document exists but is outside the caller's boundary, this returns an
    empty result without revealing that the document exists. ``strategy`` /
    ``mode`` are optional ablation overrides (default: server strategy + hybrid).
    """
    chunk_strategy = _resolve_strategy(app, strategy)
    retrieval_mode = _resolve_mode(app, mode, RetrievalMode.HYBRID)
    app.ensure_ingested(chunk_strategy)
    chunks, _ = retrieve(
        app.clients,
        strategy=chunk_strategy.value,
        query=f"{doc} {section}".strip(),
        allowed_groups=identity.groups,
        mode=retrieval_mode,
        top_k=10,
    )
    matches = [
        rc
        for rc in chunks
        if doc.lower() in rc.chunk.doc.lower()
        and (not section or section.lower() in rc.chunk.section_display.lower())
    ]
    return {
        "doc": doc,
        "section": section,
        "found": bool(matches),
        "passages": [
            {
                "section": rc.chunk.section_display,
                "page": rc.chunk.page,
                "text": rc.chunk.text,
            }
            for rc in matches
        ],
    }
