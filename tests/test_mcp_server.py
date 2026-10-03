"""Smoke test: the MCP server builds and registers its tools.

Skipped automatically when the `mcp` package is not installed (it is a runtime
dependency, installed by `make setup`); this locks in the correct SDK import.
"""

from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("mcp")


def test_mcp_server_builds_and_lists_tools():
    from ragsafety.mcp_server.server import build_server

    server = build_server()
    tools = asyncio.run(server.list_tools())
    names = {t.name for t in tools}
    assert names == {"get_safety_checklist", "search_policies", "get_document_section"}


def test_mcp_tool_call_runs_flow():
    from ragsafety.mcp_server.server import build_server

    server = build_server()
    result = asyncio.run(
        server.call_tool(
            "get_safety_checklist",
            {"query": "approach distance at 11 kV?", "persona": "priya"},
        )
    )
    # mcp 2.x returns a CallToolResult; just assert the call succeeded.
    assert result is not None
