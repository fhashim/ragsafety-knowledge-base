"""Shared helpers for the demo scripts: a configured app and a pretty printer."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ragsafety.app import RagSafetyApp  # noqa: E402
from ragsafety.schema import QueryResult  # noqa: E402
from ragsafety.security import persona_meta  # noqa: E402
from ragsafety.settings import Settings  # noqa: E402

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
CYAN = "\033[36m"
YELLOW = "\033[33m"
GREEN = "\033[32m"
RED = "\033[31m"


def make_app(*, show_traces: bool = False, enable_web: bool = False) -> RagSafetyApp:
    settings = Settings(
        mock_mode=True,
        quiet_tracing=not show_traces,
        enable_bing_grounding=enable_web,
        log_level="ERROR",
    )
    app = RagSafetyApp(settings=settings)
    app.ingest([settings.chunk_strategy])
    return app


def banner(text: str) -> None:
    print(f"\n{BOLD}{CYAN}{'=' * 74}{RESET}")
    print(f"{BOLD}{CYAN}  {text}{RESET}")
    print(f"{BOLD}{CYAN}{'=' * 74}{RESET}")


def who(persona: str) -> str:
    m = persona_meta(persona)
    return f"{m['display_name']} ({m['role']})"


def ask(app: RagSafetyApp, persona: str, query: str) -> QueryResult:
    print(f"\n{DIM}[{who(persona)}]{RESET}")
    print(f"{BOLD}Q:{RESET} {query}")
    r = app.answer(query, persona)
    render(r)
    return r


def render(r: QueryResult) -> None:
    color = {
        "answered": GREEN,
        "clarified": YELLOW,
        "refused": RED,
        "blocked": RED,
    }.get(r.outcome, RESET)
    print(f"{BOLD}Outcome:{RESET} {color}{r.outcome.upper()}{RESET}")
    if r.outcome == "answered" and r.checklist:
        c = r.checklist
        meta = " | ".join(x for x in [c.task, c.equipment, c.location] if x)
        print(f"{DIM}  task: {meta}{RESET}")
        for it in c.items:
            cites = "; ".join(f"{cit.doc} p{cit.page}" for cit in it.citations)
            val = f" = {BOLD}{it.value}{RESET}" if it.value else ""
            label = f"[{it.category.value}]"
            print(f"  • {label} {it.instruction[:70]}{val}")
            if cites:
                print(f"      {DIM}source: {cites}{RESET}")
        if c.web_sources:
            print(f"  {YELLOW}web (regulator, labeled separately):{RESET}")
            for w in c.web_sources:
                print(f"      {YELLOW}• {w.doc} <{w.url}>{RESET}")
        if c.stop_work_conditions:
            print(f"  {RED}stop-work conditions:{RESET}")
            for s in c.stop_work_conditions[:4]:
                print(f"      {RED}‣ {s[:80]}{RESET}")
    elif r.outcome == "clarified" and r.clarification:
        print(f"  {YELLOW}Clarifying question:{RESET} {r.clarification.question}")
    else:
        print(f"  {DIM}{r.message}{RESET}")
    if r.audit:
        a = r.audit
        print(
            f"{DIM}  trace={a.trace_id[:8]} tokens_in={a.tokens_in} "
            f"tokens_out={a.tokens_out} cost=${a.cost_usd:.5f} "
            f"latency={a.latency_ms:.1f}ms{RESET}"
        )
