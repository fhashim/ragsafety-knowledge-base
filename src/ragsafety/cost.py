"""Cost computation from recorded token usage.

Prices come from ``config/pricing.yaml`` (never hard-coded). Cost is computed per
LLM/embedding call and recorded on spans and in the audit record, so it can be
aggregated per user / per stage / per day by ``scripts/cost_report.py``.
"""

from __future__ import annotations

from .schema import TokenUsage
from .settings import load_pricing


def prices_unverified() -> bool:
    return bool(load_pricing().get("verify", False))


def _model_prices(model: str) -> dict:
    pricing = load_pricing()
    models = pricing.get("models", {})
    return models.get(model, pricing.get("default", {}))


def cost_usd(usage: TokenUsage) -> float:
    """USD cost for one call. Uses the model name, falling back to deployment."""
    key = usage.model or usage.deployment
    # Mock usage records "mock-small"/"mock-large"; map them to configured models.
    alias = {"mock-small": "gpt-4.1-mini", "mock-large": "gpt-4.1"}
    prices = _model_prices(alias.get(key, key))
    cost = 0.0
    cost += (usage.prompt_tokens / 1000.0) * prices.get("prompt_per_1k", 0.0)
    cost += (usage.completion_tokens / 1000.0) * prices.get("completion_per_1k", 0.0)
    cost += (usage.embedding_tokens / 1000.0) * prices.get("embedding_per_1k", 0.0)
    return round(cost, 8)
