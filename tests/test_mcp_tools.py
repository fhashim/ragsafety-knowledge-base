"""MCP tool logic: grounded checklist, security-trimmed search, section fetch.

Exercises the pure implementations (no `mcp` package needed), including that the
group boundary is enforced for a cross-domain caller.
"""

from __future__ import annotations

from ragsafety.mcp_server.tools import (
    get_document_section_impl,
    get_safety_checklist_impl,
    resolve_identity,
    search_policies_impl,
)


def test_get_safety_checklist_grounded(app):
    ident = resolve_identity("priya")
    out = get_safety_checklist_impl(app, ident, "approach distance at 11 kV?")
    assert out["outcome"] == "answered"
    assert "checklist" in out


def test_search_policies_security_trimmed(app):
    priya = resolve_identity("priya")
    marcus = resolve_identity("marcus")
    # Priya (electrical) can see the HV doc; Marcus (gas) cannot.
    p = search_policies_impl(app, priya, "arc flash PPE category", top_k=5)
    m = search_policies_impl(app, marcus, "arc flash PPE category", top_k=5)
    assert any(r["doc"] == "HV Substation Safety Policy" for r in p)
    assert all(r["doc"] != "HV Substation Safety Policy" for r in m)


def test_get_document_section_respects_boundary(app):
    marcus = resolve_identity("marcus")
    # The HV doc exists but is outside Marcus's boundary: no passages, no leak.
    out = get_document_section_impl(app, marcus, "HV Substation Safety Policy", "Approach")
    assert out["found"] is False
    assert out["passages"] == []


def test_forwarded_group_claims_override_persona():
    ident = resolve_identity("someone", groups=["grp-gas", "grp-all"])
    assert ident.groups == ["grp-all", "grp-gas"]
