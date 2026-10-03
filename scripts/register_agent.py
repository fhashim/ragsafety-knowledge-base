#!/usr/bin/env python3
"""Register (or update) the Foundry agent and its MCP tool.

Data-plane step owned by Python (no mature Terraform path for the agent/tool
definition). In mock mode this prints the registration plan. In Azure mode it
uses the Foundry Agents SDK to create/update an agent that:
  * uses the strong chat deployment for final checklist generation;
  * calls the MCP server (Azure Container App URL) as an MCP tool, forwarding the
    caller's identity + group claims;
  * optionally enables Grounding with Bing restricted to the allow-list.

Usage:
    python scripts/register_agent.py --mcp-url https://<app>.azurecontainerapps.io
"""

from __future__ import annotations

import argparse

import _bootstrap  # noqa: F401
from ragsafety.settings import get_settings, load_bing_allowlist


def _plan(settings, mcp_url: str) -> dict:
    return {
        "agent_name": "ragsafety-checklist-agent",
        "model_deployment": settings.chat_large_deployment,
        "instructions": (
            "You generate grounded, cited pre-task safety checklists for energy "
            "field technicians. Never invent a distance, voltage or threshold; if "
            "a value is not supported by a source, instruct the user to stop work "
            "and contact their supervisor. Enforce the caller's group claims."
        ),
        "mcp_tool": {
            "server_label": "ragsafety",
            "server_url": mcp_url,
            "allowed_tools": ["get_safety_checklist", "search_policies", "get_document_section"],
            "forward_claims_header": "X-RAGSAFETY-GROUPS",
        },
        "bing_grounding": {
            "enabled": settings.enable_bing_grounding,
            "allowed_domains": load_bing_allowlist(),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mcp-url", default="http://localhost:8000")
    args = parser.parse_args()
    settings = get_settings()
    plan = _plan(settings, args.mcp_url)

    if settings.mock_mode:
        import json

        print("MOCK_MODE: would register the following Foundry agent + MCP tool:\n")
        print(json.dumps(plan, indent=2))
        return

    register_agent_azure(settings, plan)  # pragma: no cover


def register_agent_azure(settings, plan) -> None:  # pragma: no cover - real-Azure only
    # VERIFY: Foundry Agents SDK surface (azure-ai-projects) and the MCP tool
    # definition shape change frequently. Confirm against Microsoft Learn.
    from azure.ai.projects import AIProjectClient  # noqa: F401
    from azure.identity import DefaultAzureCredential  # noqa: F401

    # Construct the client and call create/update with the plan above. The exact
    # create_agent / MCP-tool registration surface depends on the azure-ai-projects
    # version, e.g.:
    #   client = AIProjectClient(endpoint=settings.foundry_project_endpoint,
    #                            credential=DefaultAzureCredential(...))
    #   tool = McpTool(server_label="ragsafety", server_url=plan["mcp_tool"]["server_url"])
    #   client.agents.create_agent(model=plan["model_deployment"],
    #                              instructions=plan["instructions"], tools=[tool])
    raise NotImplementedError(
        "Wire the Foundry Agents SDK create/update call for your azure-ai-projects "
        "version using the plan above."
    )


if __name__ == "__main__":
    main()
