"""Per-user access boundaries.

Group membership determines which chunks a user may retrieve. In Azure mode the
groups come from the signed-in user's Entra ID token (and from the MCP server's
forwarded claims); in mock mode they come from ``config/personas.yaml``. Either
way the groups become an ``allowed_groups`` filter applied at retrieval time —
never a prompt instruction.
"""

from __future__ import annotations

from .settings import load_personas


class UnknownPersona(KeyError):
    pass


def persona_groups(persona_id: str) -> list[str]:
    personas = load_personas().get("personas", {})
    if persona_id not in personas:
        raise UnknownPersona(persona_id)
    return list(personas[persona_id]["groups"])


def persona_meta(persona_id: str) -> dict:
    personas = load_personas().get("personas", {})
    if persona_id not in personas:
        raise UnknownPersona(persona_id)
    return personas[persona_id]


def groups_for_claims(groups: list[str]) -> list[str]:
    """Normalize a list of group claims forwarded by the MCP server / token."""
    return sorted(set(groups))


def domain_required_group(domain: str) -> str | None:
    """The group that owns a domain's documents (``grp-electrical`` / ``grp-gas``).

    Returns ``None`` for the shared domain (visible to everyone).
    """
    mapping = load_personas().get("domain_groups", {})
    group = mapping.get(domain)
    return None if group in (None, "grp-all") else group


def can_access_domain(user_groups: list[str], domain: str | None) -> bool:
    """Defense-in-depth authorization check used alongside the retrieval filter.

    The AI Search ``allowed_groups`` filter is the primary boundary; this gives a
    clean, auditable refusal when a user asks about a restricted domain they are
    not in, instead of silently returning only shared content.
    """
    if not domain:
        return True
    required = domain_required_group(domain)
    if required is None:
        return True
    return required in set(user_groups)
