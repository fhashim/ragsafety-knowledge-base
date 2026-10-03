#!/usr/bin/env python3
"""Ingest the knowledge base: parse -> chunk -> embed -> index.

Owned by Python (data-plane). Reads endpoints from settings/Terraform outputs via
the environment. Idempotent (merge/upload by chunk id).

Usage:
    python scripts/ingest.py [--strategy section_aware|...|all]
"""

from __future__ import annotations

import argparse

import _bootstrap  # noqa: F401
from ragsafety.app import RagSafetyApp
from ragsafety.settings import ChunkStrategy, get_settings


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strategy", default="section_aware")
    args = parser.parse_args()

    settings = get_settings()
    app = RagSafetyApp(settings=settings)
    strategies = (
        list(ChunkStrategy) if args.strategy == "all" else [ChunkStrategy(args.strategy)]
    )
    counts = app.ingest(strategies)
    for strat, n in counts.items():
        print(f"  indexed {n} chunks for strategy={strat}")
    print(f"Ingestion complete (mock={settings.mock_mode}).")


if __name__ == "__main__":
    main()
