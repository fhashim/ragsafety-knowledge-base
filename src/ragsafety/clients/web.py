"""Web grounding clients (Grounding with Bing Search).

Web grounding is feature-flagged and allow-listed to public safety regulators.
Mock mode returns deterministic, clearly-synthetic regulator snippets so the
web-grounding demo runs offline; the content is always labeled as web-sourced,
and the generator keeps internal policy authoritative on any conflict.
"""

from __future__ import annotations

from ..schema import WebResult
from ..settings import Settings
from .base import WebGroundingClient

# Deterministic, synthetic "regulator" snippets keyed by concept keyword. These
# are illustrative placeholders, not real quotations.  # VERIFY: real content
# comes from Grounding with Bing at runtime.
_CANNED = {
    "arc flash": WebResult(
        title="NFPA 70E arc-flash PPE categories (summary)",
        url="https://nfpa.org/70e-arc-flash",
        snippet=(
            "General guidance: select arc-rated PPE by incident-energy category; "
            "verify against the site's own arc-flash study before work."
        ),
        domain="nfpa.org",
    ),
    "confined space": WebResult(
        title="OSHA confined space entry overview",
        url="https://osha.gov/confined-spaces",
        snippet=(
            "General guidance: test the atmosphere, control hazards, and use an "
            "attendant; follow your employer's permit program."
        ),
        domain="osha.gov",
    ),
    "gas": WebResult(
        title="HSE guidance on flammable gas detection",
        url="https://hse.gov.uk/gas-detection",
        snippet=(
            "General guidance: calibrate detectors and set alarms relative to the "
            "lower explosive limit; follow site procedures for thresholds."
        ),
        domain="hse.gov.uk",
    ),
}


class MockWebGroundingClient(WebGroundingClient):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def search(self, query: str, allowed_domains: list[str]) -> list[WebResult]:
        lower = query.lower()
        results: list[WebResult] = []
        for key, result in _CANNED.items():
            if key in lower and result.domain in allowed_domains:
                results.append(result)
        return results[:2]


class AzureWebGroundingClient(WebGroundingClient):
    """Grounding with Bing via the Foundry agent tool. Imported lazily."""

    def __init__(self, settings: Settings) -> None:  # pragma: no cover - real-Azure only
        self.settings = settings

    def search(self, query: str, allowed_domains: list[str]) -> list[WebResult]:  # pragma: no cover
        # VERIFY: Grounding with Bing is invoked through the Foundry agent (see
        # scripts/register_agent.py), which enforces the domain allow-list on the
        # connection. Direct invocation here is intentionally not implemented;
        # the agent path is the supported one.
        return []
