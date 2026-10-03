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
from ..settings import RetrievalMode


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


def get_safety_checklist_impl(app: RagSafetyApp, identity: Identity, query: str) -> dict:
    """Produce a grounded pre-task safety checklist for the caller."""
    result = app.answer(query, identity.persona)
    out: dict = {"outcome": result.outcome, "trace_id": result.trace_id}
    if result.outcome == "answered" and result.checklist:
        out["checklist"] = result.checklist.model_dump(mode="json")
    elif result.outcome == "clarified" and result.clarification:
        out["clarification"] = result.clarification.model_dump(mode="json")
    else:
        out["message"] = result.message
    return out


def search_policies_impl(
    app: RagSafetyApp, identity: Identity, query: str, top_k: int = 5
) -> list[dict]:
    """Security-trimmed policy search. Returns chunk summaries the caller may see."""
    app.ensure_ingested()  # idempotent; no-op in Azure mode
    chunks, _ = retrieve(
        app.clients,
        strategy=app.settings.chunk_strategy.value,
        query=query,
        allowed_groups=identity.groups,
        mode=RetrievalMode.HYBRID_RERANK,
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
    app: RagSafetyApp, identity: Identity, doc: str, section: str = ""
) -> dict:
    """Return the text of a named document section the caller is allowed to read.

    If the document exists but is outside the caller's boundary, this returns an
    empty result without revealing that the document exists.
    """
    app.ensure_ingested()
    chunks, _ = retrieve(
        app.clients,
        strategy=app.settings.chunk_strategy.value,
        query=f"{doc} {section}".strip(),
        allowed_groups=identity.groups,
        mode=RetrievalMode.HYBRID,
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
