#!/usr/bin/env python3
"""Demo 3 — Clarification: ambiguous task triggers a question, then answers."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _common import ask, banner, make_app


def main():
    app = make_app()
    banner("Demo 3: Clarification on an ambiguous request")
    ask(app, "priya", "what do I need for the line job tomorrow?")
    print("\n  ...technician replies with the missing detail:")
    ask(app, "priya", "inspect the 11 kV line, what approach distance and PPE?")


if __name__ == "__main__":
    main()
