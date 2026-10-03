"""MCP server exposing the RAG safety tools.

Uses the official MCP Python SDK (`mcp` 2.x), where the server class is
``MCPServer`` (formerly FastMCP). The ``@mcp.tool()`` decorator and
``mcp.run(transport=...)`` are unchanged.

Run locally (mock mode):
    RAGSAFETY_MOCK_MODE=true python -m ragsafety.mcp_server.server

Transport is streamable HTTP so the server can be registered as an MCP tool on
the Foundry agent and run in Azure Container Apps.

Identity / group enforcement: each tool accepts an optional ``groups`` argument.
The Foundry agent / API gateway is expected to populate it from the caller's
*validated* Entra ID token claims (never from the end user directly). The tool
then enforces those groups as the AI Search ``allowed_groups`` filter. When
``groups`` is absent, the configured demo ``persona`` is used to resolve groups.

SECURITY NOTE: in production, put the Container App behind authentication and
derive ``groups`` from the validated token at the gateway so a caller cannot
spoof them; the server trusts the forwarded claims.
"""

from __future__ import annotations

import os

from ..app import RagSafetyApp
from ..settings import get_settings
from .tools import (
    get_document_section_impl,
    get_safety_checklist_impl,
    resolve_identity,
    search_policies_impl,
)


def build_server():
    from mcp.server.mcpserver import MCPServer

    settings = get_settings()
    app = RagSafetyApp(settings=settings)
    app.ensure_ingested()  # mock mode: build the in-memory index; Azure: no-op
    mcp = MCPServer("ragsafety")

    def ident(persona: str | None, groups: list[str] | None):
        return resolve_identity(persona or settings.persona, groups)

    @mcp.tool()
    def get_safety_checklist(
        query: str, persona: str | None = None, groups: list[str] | None = None
    ) -> dict:
        """Grounded, cited pre-task safety checklist for a described maintenance task."""
        return get_safety_checklist_impl(app, ident(persona, groups), query)

    @mcp.tool()
    def search_policies(
        query: str,
        persona: str | None = None,
        groups: list[str] | None = None,
        top_k: int = 5,
    ) -> list[dict]:
        """Search internal safety policies, security-trimmed to the caller's groups."""
        return search_policies_impl(app, ident(persona, groups), query, top_k)

    @mcp.tool()
    def get_document_section(
        doc: str,
        section: str = "",
        persona: str | None = None,
        groups: list[str] | None = None,
    ) -> dict:
        """Fetch a named document section the caller is authorized to read."""
        return get_document_section_impl(app, ident(persona, groups), doc, section)

    return mcp


def main() -> None:
    mcp = build_server()
    transport = os.environ.get("RAGSAFETY_MCP_TRANSPORT", "streamable-http")
    if transport == "streamable-http":
        # Bind to 0.0.0.0 — Azure Container Apps ingress cannot reach a server
        # listening only on 127.0.0.1 (the SDK default). Served at /mcp.
        host = os.environ.get("RAGSAFETY_MCP_HOST", "0.0.0.0")  # noqa: S104
        port = int(os.environ.get("RAGSAFETY_MCP_PORT", "8000"))
        mcp.run(transport=transport, host=host, port=port)
    else:
        mcp.run(transport=transport)


if __name__ == "__main__":
    main()
