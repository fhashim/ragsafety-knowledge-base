#!/usr/bin/env python3
"""Aggregate token cost per user and per day.

In mock mode this reads the local audit sink (``audit_local/ragaudit.jsonl``). In
Azure mode it reads the ``ragaudit`` Table and runs a KQL query against App
Insights for the per-STAGE breakdown (spans carry token/cost attributes). The KQL
is printed below so it can be pasted into the Foundry/App Insights logs blade.

Usage:
    python scripts/cost_report.py
"""

from __future__ import annotations

import json
from collections import defaultdict

import _bootstrap  # noqa: F401
from ragsafety.cost import prices_unverified
from ragsafety.settings import get_settings

# Per-stage cost from App Insights (GenAI spans carry gen_ai.usage.* attributes).
STAGE_COST_KQL = """
dependencies
| where timestamp > ago(7d)
| extend stage = name
| extend tokens_in = toint(customDimensions['gen_ai.usage.input_tokens'])
| extend tokens_out = toint(customDimensions['gen_ai.usage.output_tokens'])
| summarize calls=count(), tokens_in=sum(tokens_in), tokens_out=sum(tokens_out)
    by stage, bin(timestamp, 1d)
| order by timestamp desc
""".strip()


def _rows_from_local(settings) -> list[dict]:
    path = settings.audit_dir / f"{settings.audit_table}.jsonl"
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def _print_table(title: str, data: dict[str, dict]) -> None:
    print(f"\n{title}")
    print(f"  {'key':<16} {'queries':>8} {'tokens_in':>10} {'tokens_out':>11} {'cost_usd':>10}")
    for key, agg in sorted(data.items()):
        print(
            f"  {key:<16} {agg['n']:>8} {agg['tin']:>10} {agg['tout']:>11} "
            f"{agg['cost']:>10.5f}"
        )


def main() -> None:
    settings = get_settings()
    rows = _rows_from_local(settings)  # Azure: swap for Table + KQL (see below)
    if not rows:
        print("No audit records found. Run a demo/session first (mock mode writes")
        print(f"to {settings.audit_dir}).")
        print("\nApp Insights per-stage KQL (Azure mode):\n")
        print(STAGE_COST_KQL)
        return

    per_user: dict[str, dict] = defaultdict(lambda: {"n": 0, "tin": 0, "tout": 0, "cost": 0.0})
    per_day: dict[str, dict] = defaultdict(lambda: {"n": 0, "tin": 0, "tout": 0, "cost": 0.0})
    per_outcome: dict[str, dict] = defaultdict(lambda: {"n": 0, "tin": 0, "tout": 0, "cost": 0.0})
    for r in rows:
        for bucket, key in ((per_user, r["user"]), (per_day, r["date"]), (per_outcome, r["outcome"])):
            agg = bucket[key]
            agg["n"] += 1
            agg["tin"] += r.get("tokens_in", 0)
            agg["tout"] += r.get("tokens_out", 0)
            agg["cost"] += r.get("cost_usd", 0.0)

    total = sum(r.get("cost_usd", 0.0) for r in rows)
    print(f"Cost report — {len(rows)} audited queries, total ${total:.5f}")
    if prices_unverified():
        print("WARNING: pricing in config/pricing.yaml is a placeholder (verify: true).")
    _print_table("By user", per_user)
    _print_table("By day", per_day)
    _print_table("By outcome", per_outcome)
    print("\nApp Insights per-stage KQL (Azure mode):\n")
    print(STAGE_COST_KQL)


if __name__ == "__main__":
    main()
