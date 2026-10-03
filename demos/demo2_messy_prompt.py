#!/usr/bin/env python3
"""Demo 2 — Messy prompt: typos/shorthand rewritten, then a grounded checklist."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _common import ask, banner, make_app


def main():
    app = make_app()
    banner("Demo 2: Messy-prompt rewrite")
    q = "need 2 fix tx400 at sub 4 2moro wats the gap n do i need gloves"
    r = ask(app, "priya", q)
    print(f"\n  rewritten: '{r.audit.original_query}'")
    print(f"          -> '{r.audit.rewritten_query}'")


if __name__ == "__main__":
    main()
