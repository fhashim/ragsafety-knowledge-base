"""Generate stage.

Delegates to the chat client's ``generate`` (which emits a strict ``Checklist``).
Internal policy is authoritative: web results are passed through only as
separately-labeled ``web_sources`` and never override an internal value. The
"never invent a value" rule lives in the generator (mock) / the prompt (Azure):
an unsupported requested value becomes a ``stop_work`` instruction.
"""

from __future__ import annotations

from ..clients import Clients
from ..schema import Checklist, RetrievedChunk, RewriteResult, TokenUsage, WebResult


def generate_checklist(
    clients: Clients,
    rewrite: RewriteResult,
    retrieved: list[RetrievedChunk],
    web: list[WebResult],
    persona: str,
) -> tuple[Checklist, TokenUsage]:
    return clients.chat.generate(rewrite, retrieved, web, persona)
