#!/usr/bin/env python3
"""Ablation study: chunking strategy x retrieval mode.

Runs the golden set across the three chunking strategies and the four retrieval
modes (vector / BM25 / hybrid / hybrid+rerank) and writes ``results/ablation.md``
with a comparison table (recall@5, MRR, groundedness, cost, latency) and a few
worked examples showing how the retrieved evidence — and therefore the answer —
changes with the configuration.

Numbers are deterministic for the mock pipeline but will differ per run on real
Azure; the point is the *shape* of the differences, which the planted traps make
visible:
  * exact codes (GV-17) favor BM25;
  * paraphrases (visible clothing) favor vectors;
  * near-duplicate rows (11 kV vs 33 kV) favor the reranker;
  * page-spanning tables favor section-aware chunking.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import (  # noqa: E402
    build_app,
    fact_rank,
    index_profile,
    load_golden,
    percentile,
    retrieve_for,
    valued_items_cited,
)
from ragsafety.settings import ChunkStrategy, RetrievalMode  # noqa: E402

RESULTS = Path(__file__).resolve().parents[1] / "results" / "ablation.md"
RETRIEVAL_CATEGORIES = {"keyword", "semantic", "table", "multi-hop", "OCR", "messy-prompt"}


def _mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def evaluate(strategy: ChunkStrategy, mode: RetrievalMode, items):
    app = build_app(strategy, mode, enable_web=False)
    recalls, rrs, grounded, costs, lats = [], [], [], [], []
    for it in items:
        if it.category not in RETRIEVAL_CATEGORIES or not it.expected_doc:
            continue
        # Chunk-level recall/MRR: did the chunk that actually holds the fact rank?
        chunks = retrieve_for(app, it, strategy, mode)
        rank = fact_rank(chunks, it)
        recalls.append(1.0 if (rank and rank <= 5) else 0.0)
        rrs.append(1.0 / rank if rank else 0.0)
        # Groundedness/cost/latency from the full answered flow.
        r = app.answer(it.query, it.persona)
        if r.outcome == "answered":
            grounded.append(1.0 if valued_items_cited(r) else 0.0)
        costs.append(r.audit.cost_usd)
        lats.append(r.audit.latency_ms)
    return {
        "recall@5": _mean(recalls),
        "MRR": _mean(rrs),
        "groundedness": _mean(grounded),
        "avg_cost_usd": _mean(costs),
        "p50_latency_ms": percentile(lats, 50),
    }


def worked_example(item, strategy: ChunkStrategy):
    rows = []
    for mode in RetrievalMode:
        app = build_app(strategy, mode, enable_web=False)
        chunks = retrieve_for(app, item, strategy, mode)
        rank = fact_rank(chunks, item)
        if chunks:
            top = chunks[0].chunk
            top_label = f"{top.doc} / {top.section_display}"[:46]
        else:
            top_label = "(none)"
        hit = "yes" if (rank and rank <= 5) else "no"
        rows.append((mode.value, top_label, rank if rank else "-", hit))
    return rows


def main() -> None:
    items = load_golden()
    strategies = list(ChunkStrategy)
    modes = list(RetrievalMode)

    lines = ["# Retrieval & Chunking Ablation", ""]
    lines.append(
        "Golden set run across chunking strategy x retrieval mode. recall@5 and MRR "
        "are measured at the **chunk** level (did the chunk that actually holds the "
        f"fact rank?), over the {len(RETRIEVAL_CATEGORIES)} retrieval categories "
        "(keyword, semantic, table, multi-hop, OCR, messy-prompt)."
    )

    # Chunking profile: a concrete, measurable difference between strategies.
    lines.append("")
    lines.append("## Chunking profile")
    lines.append("")
    lines.append("| Chunking | chunks | avg tokens/chunk |")
    lines.append("| --- | --- | --- |")
    for strat in strategies:
        app = build_app(strat, RetrievalMode.HYBRID, enable_web=False)
        n, avg = index_profile(app, strat)
        lines.append(f"| {strat.value} | {n} | {avg:.0f} |")
    lines.append("")
    lines.append(
        "Fixed strategies over-split the corpus (more, smaller chunks and, with "
        "overlap, duplicated text => higher embedding/query cost). Section-aware "
        "produces fewer, self-contained chunks that each carry their heading path."
    )

    lines.append("")
    lines.append("## Metrics")
    lines.append("")
    lines.append("| Chunking | Retrieval | recall@5 | MRR | groundedness | avg cost $ | p50 ms |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    for strat in strategies:
        for mode in modes:
            m = evaluate(strat, mode, items)
            lines.append(
                f"| {strat.value} | {mode.value} | {m['recall@5']:.2f} | {m['MRR']:.2f} | "
                f"{m['groundedness']:.2f} | {m['avg_cost_usd']:.5f} | {m['p50_latency_ms']:.2f} |"
            )

    # Worked examples: how the evidence changes with retrieval mode (section-aware).
    examples = {
        "kw2": "Exact code (GV-17): BM25 pins it; pure vector is weaker.",
        "sem3": "Paraphrase (visible clothing -> hi-vis): vectors bridge the wording.",
        "tab2": "Near-duplicate rows (33 kV vs 11 kV): reranking sharpens the top hit.",
        "ocr1": "OCR-only poster: evidence exists only via OCR of the image.",
    }
    by_id = {it.id: it for it in items}
    lines.append("")
    lines.append("## Worked examples — retrieval mode (section-aware chunking)")
    for ex_id, note in examples.items():
        it = by_id.get(ex_id)
        if not it:
            continue
        lines.append("")
        lines.append(f"### `{ex_id}` — {it.query}")
        lines.append(f"_{note}_")
        lines.append("")
        lines.append("| Retrieval mode | Top-1 chunk (doc / section) | Fact chunk rank | In top-5 |")
        lines.append("| --- | --- | --- | --- |")
        for mode_v, top_label, rank, hit in worked_example(it, ChunkStrategy.SECTION_AWARE):
            lines.append(f"| {mode_v} | {top_label} | {rank} | {hit} |")

    # Worked example — chunking: structure of the page-spanning arc-flash table.
    lines.append("")
    lines.append("## Worked example — chunking (page-spanning arc-flash table)")
    lines.append(
        "_The arc-flash PPE table spans pages 2-3 (CAT 1-2 on p2, CAT 3-4 on p3). "
        "This looks at the chunk that holds `40 cal` (CAT 4): does one chunk hold "
        "the whole table, is it typed as a table, and does it keep its heading path?_"
    )
    lines.append("")
    lines.append("| Chunking | chunk type of '40 cal' | all CAT 1-4 in one chunk | heading kept |")
    lines.append("| --- | --- | --- | --- |")
    for strat in strategies:
        app = build_app(strat, RetrievalMode.HYBRID, enable_web=False)
        entries = app.clients.search._indexes[strat.value].entries
        holder = next((e.chunk for e in entries if "40 cal" in e.chunk.text.lower()), None)
        if holder is None:
            lines.append(f"| {strat.value} | (not found) | no | no |")
            continue
        text = holder.text.lower()
        all_cats = all(f"cat {n}" in text for n in (1, 2, 3, 4))
        heading = "yes" if holder.text.startswith("Section:") else "no"
        lines.append(
            f"| {strat.value} | {holder.content_type.value} | "
            f"{'yes' if all_cats else 'no'} | {heading} |"
        )

    lines.append("")
    lines.append(
        "> Numbers vary per run on real Azure (embeddings, ranker, model). The "
        "relative ordering is the lesson, not the absolute values."
    )
    RESULTS.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {RESULTS}")


if __name__ == "__main__":
    main()
