#!/usr/bin/env python3
"""Evaluation gate.

Runs the golden set through the pipeline and computes:

  * quality:  groundedness, relevance, retrieval recall@5, citation accuracy
  * behavior: refusal correctness (unauthorized + out-of-scope), clarification
              triggered (ambiguous), jailbreak blocked
  * budget:   cost per query, p50/p95 latency

Fails (exit 1) if any threshold in ``config/eval_thresholds.yaml`` is missed, and
writes a Markdown table to stdout and to ``$GITHUB_STEP_SUMMARY`` when set.

In mock mode the metrics are computed locally and deterministically. In real
mode the groundedness/relevance scores can additionally be produced by the Azure
AI Evaluation SDK (see ``azure_ai_evaluators`` below); the gate logic is the same.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Make `ragsafety` and the sibling `_common` importable when run directly.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import (  # noqa: E402
    build_app,
    citation_accuracy,
    facts_present,
    load_golden,
    percentile,
    recall_hit,
    valued_items_cited,
)
from ragsafety.settings import (  # noqa: E402
    ChunkStrategy,
    RetrievalMode,
    load_eval_thresholds,
)

REFUSE_OK = {"refused", "blocked"}


def azure_ai_evaluators():  # pragma: no cover - real-Azure only
    """Return Azure AI Evaluation SDK evaluators (real mode).

    Kept as a stub so the dependency and intent are explicit; the deterministic
    local metrics below are what run in CI (mock mode).
    """
    from azure.ai.evaluation import GroundednessEvaluator, RelevanceEvaluator  # noqa: F401

    raise NotImplementedError("Wire real-mode evaluators when running against Azure.")


def run() -> int:
    thresholds = load_eval_thresholds()
    items = load_golden()
    app = build_app(ChunkStrategy.SECTION_AWARE, RetrievalMode.HYBRID_RERANK, enable_web=True)

    results = []
    for it in items:
        r = app.answer(it.query, it.persona)
        results.append((it, r))

    answered = [(it, r) for it, r in results if r.outcome == "answered"]
    with_doc = [(it, r) for it, r in answered if it.expected_doc]

    def _mean(xs: list[float]) -> float:
        return sum(xs) / len(xs) if xs else 1.0

    groundedness = _mean([1.0 if valued_items_cited(r) else 0.0 for _, r in answered])
    relevance = _mean([facts_present(r, it) for it, r in answered if it.expected_facts])
    recall = _mean([1.0 if recall_hit(r, it) else 0.0 for it, r in with_doc])
    citation = _mean([citation_accuracy(r, it) for it, r in answered if it.expected_facts])

    unauthorized_oos = [(it, r) for it, r in results if it.category in ("unauthorized", "out-of-scope")]
    refusal = _mean([1.0 if r.outcome in REFUSE_OK else 0.0 for _, r in unauthorized_oos])
    ambiguous = [(it, r) for it, r in results if it.category == "ambiguous"]
    clarification = _mean([1.0 if r.outcome == "clarified" else 0.0 for _, r in ambiguous])
    jailbreaks = [(it, r) for it, r in results if it.category == "jailbreak"]
    jb_blocked = _mean([1.0 if r.outcome == "blocked" else 0.0 for _, r in jailbreaks])

    costs = [r.audit.cost_usd for _, r in results]
    lats = [r.audit.latency_ms for _, r in results]
    cost_per_query = _mean(costs)
    p50 = percentile(lats, 50)
    p95 = percentile(lats, 95)

    outcome_match = _mean([1.0 if r.outcome == it.expected_outcome else 0.0 for it, r in results])

    q, b, bud = thresholds["quality"], thresholds["behavior"], thresholds["budget"]
    checks = [
        ("groundedness", groundedness, q["groundedness_min"], ">="),
        ("relevance", relevance, q["relevance_min"], ">="),
        ("retrieval_recall@5", recall, q["retrieval_recall_at_5_min"], ">="),
        ("citation_accuracy", citation, q["citation_accuracy_min"], ">="),
        ("refusal_correctness", refusal, b["refusal_correctness_min"], ">="),
        ("clarification_correctness", clarification, b["clarification_correctness_min"], ">="),
        ("jailbreak_blocked", jb_blocked, b["jailbreak_block_min"], ">="),
        ("cost_per_query_usd", cost_per_query, bud["cost_per_query_usd_max"], "<="),
        ("p50_latency_ms", p50, bud["p50_latency_ms_max"], "<="),
        ("p95_latency_ms", p95, bud["p95_latency_ms_max"], "<="),
    ]

    passed_all = True
    lines = [
        f"# Eval gate — {len(items)} golden items",
        "",
        f"Outcome match (all categories): **{outcome_match:.0%}**",
        "",
        "| Metric | Value | Threshold | Pass |",
        "| --- | --- | --- | --- |",
    ]
    for name, value, thr, op in checks:
        ok = value >= thr if op == ">=" else value <= thr
        passed_all = passed_all and ok
        shown = f"{value:.3f}" if value < 10 else f"{value:.1f}"
        lines.append(f"| {name} | {shown} | {op} {thr} | {'✅' if ok else '❌'} |")

    lines.append("")
    lines.append(f"**Gate: {'PASSED ✅' if passed_all else 'FAILED ❌'}**")
    report = "\n".join(lines)
    print(report)

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(report + "\n")
    (Path(__file__).resolve().parents[1] / "results" / "eval_report.md").write_text(
        report + "\n", encoding="utf-8"
    )
    return 0 if passed_all else 1


def main() -> None:
    sys.exit(run())


if __name__ == "__main__":
    main()
