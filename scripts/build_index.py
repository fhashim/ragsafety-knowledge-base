#!/usr/bin/env python3
"""Create or update the AI Search index schema (idempotent).

Data-plane step owned by Python (the schema is code and churns with the chunking
strategy). Reads endpoint names from settings/Terraform outputs via the
environment. Safe to re-run.

Usage:
    python scripts/build_index.py [--strategy section_aware|fixed_overlap|fixed_no_overlap|all]
"""

from __future__ import annotations

import argparse

import _bootstrap  # noqa: F401  (sys.path side effect)
from ragsafety.clients import build_clients
from ragsafety.settings import ChunkStrategy, get_settings


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strategy", default="all")
    args = parser.parse_args()

    settings = get_settings()
    clients = build_clients(settings)
    strategies = (
        list(ChunkStrategy) if args.strategy == "all" else [ChunkStrategy(args.strategy)]
    )
    for strat in strategies:
        clients.search.create_or_update_index(strat.value)
        name = settings.index_name_from_strategy(strat.value)
        print(f"  ensured index schema: {name} (mock={settings.mock_mode})")
    print("Index schema ready.")


if __name__ == "__main__":
    main()
