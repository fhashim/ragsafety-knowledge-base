"""Async MCP client used by the web explorer to call the deployed server.

The explorer does not import the pipeline or call the tools in-process; it is a
real MCP client that connects to a running server over streamable HTTP
(``RAGSAFETY_MCP_URL``) and invokes the tools via ``tools/call``. Point it at the
Azure Container App URL (``https://<app>.<region>.azurecontainerapps.io/mcp``)
and the output you see is produced by that server.

Auth (in order of precedence):
  * ``RAGSAFETY_MCP_BEARER_TOKEN`` -> ``Authorization: Bearer <token>``
  * ``RAGSAFETY_MCP_AAD_SCOPE``    -> token from ``DefaultAzureCredential``
plus any extra headers from ``RAGSAFETY_MCP_HEADERS_JSON`` (e.g. a Functions key
or an ``X-RAGSAFETY-GROUPS`` claims header the gateway would normally inject).

A fresh connection is opened per request. That is more than fast enough for an
interactive explorer and sidesteps the task-scoped lifetime of an MCP session.
"""

from __future__ import annotations

import json
from typing import Any

from ..settings import Settings


class MCPClientError(RuntimeError):
    """Raised when the MCP server call fails (connection, auth, or tool error)."""


def _root_cause(exc: BaseException) -> str:
    """Peel anyio ExceptionGroups down to the most informative leaf message."""
    seen: set[int] = set()
    while isinstance(exc, BaseExceptionGroup) and exc.exceptions:
        if id(exc) in seen:
            break
        seen.add(id(exc))
        exc = exc.exceptions[0]
    name = type(exc).__name__
    msg = str(exc).strip()
    return f"{name}: {msg}" if msg else name


def _extra_headers(settings: Settings) -> dict[str, str]:
    raw = settings.mcp_headers_json.strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise MCPClientError(f"RAGSAFETY_MCP_HEADERS_JSON is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise MCPClientError("RAGSAFETY_MCP_HEADERS_JSON must be a JSON object")
    return {str(k): str(v) for k, v in data.items()}


async def _auth_headers(settings: Settings) -> dict[str, str]:
    headers = _extra_headers(settings)
    if settings.mcp_bearer_token:
        headers["Authorization"] = f"Bearer {settings.mcp_bearer_token}"
    elif settings.mcp_aad_scope:
        import anyio

        def _token() -> str:
            from azure.identity import DefaultAzureCredential

            cred = DefaultAzureCredential(
                managed_identity_client_id=settings.managed_identity_client_id or None
            )
            return cred.get_token(settings.mcp_aad_scope).token

        token = await anyio.to_thread.run_sync(_token)
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _unwrap(result: Any) -> Any:
    """Return the tool's JSON payload from a CallToolResult.

    Prefer ``structured_content``; the MCP SDK wraps a non-object return (e.g. a
    list from ``search_policies``) under a single ``result`` key, which we peel.
    Fall back to concatenating/parsing the text content blocks.
    """
    structured = getattr(result, "structured_content", None)
    if structured is not None:
        if isinstance(structured, dict) and set(structured.keys()) == {"result"}:
            return structured["result"]
        return structured
    # Fallback: parse text blocks.
    texts = [getattr(c, "text", "") for c in (result.content or []) if getattr(c, "text", "")]
    if not texts:
        return None
    if len(texts) == 1:
        try:
            return json.loads(texts[0])
        except json.JSONDecodeError:
            return texts[0]
    out = []
    for t in texts:
        try:
            out.append(json.loads(t))
        except json.JSONDecodeError:
            out.append(t)
    return out


def _error_text(result: Any) -> str:
    texts = [getattr(c, "text", "") for c in (result.content or []) if getattr(c, "text", "")]
    return "; ".join(texts) or "tool returned an error"


async def _session(settings: Settings):
    """Async context manager yielding an initialized ClientSession."""
    from contextlib import asynccontextmanager

    from mcp import ClientSession
    from mcp.client.streamable_http import create_mcp_http_client, streamable_http_client

    headers = await _auth_headers(settings)

    @asynccontextmanager
    async def _cm():
        try:
            http_client = create_mcp_http_client(
                headers=headers or None,
                timeout=_timeout(settings),
            )
            async with streamable_http_client(settings.mcp_url, http_client=http_client) as streams:
                read, write = streams[0], streams[1]
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    yield session
        except MCPClientError:
            raise
        except Exception as exc:  # noqa: BLE001 - surface a clean message to the UI
            raise MCPClientError(
                f"cannot reach MCP server at {settings.mcp_url}: {_root_cause(exc)}"
            ) from exc

    return _cm()


def _timeout(settings: Settings):
    from mcp.client.streamable_http import httpx2

    return httpx2.Timeout(settings.mcp_timeout_seconds)


async def server_info(settings: Settings) -> dict:
    """Connect and list tools — used to show connection status in the UI."""
    try:
        cm = await _session(settings)
        async with cm as session:
            tools = await session.list_tools()
            info = session.server_info
            return {
                "connected": True,
                "url": settings.mcp_url,
                "server": getattr(info, "name", "") if info else "",
                "server_version": getattr(info, "version", "") if info else "",
                "tools": [
                    {"name": t.name, "description": (t.description or "").strip()}
                    for t in tools.tools
                ],
            }
    except MCPClientError as exc:
        return {"connected": False, "url": settings.mcp_url, "error": str(exc), "tools": []}


async def call_tool(settings: Settings, name: str, arguments: dict) -> Any:
    """Invoke a tool on the MCP server and return its unwrapped JSON payload."""
    cm = await _session(settings)
    async with cm as session:
        result = await session.call_tool(name, arguments)
    if getattr(result, "is_error", False):
        raise MCPClientError(_error_text(result))
    return _unwrap(result)
