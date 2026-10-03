#!/usr/bin/env python3
"""Demo 1 — Access boundaries: Priya vs Marcus on same + cross-domain questions."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _common import ask, banner, make_app


def main():
    app = make_app()
    banner("Demo 1: Per-user access boundaries (retrieval-time group filter)")
    print("Same shared question -> both answered from corporate HSE:")
    ask(app, "priya", "what hand protection do I need on site?")
    ask(app, "marcus", "what hand protection do I need on site?")

    print("\nDomain questions -> each sees only their own domain:")
    ask(app, "priya", "what is the minimum approach distance at 11 kV?")
    ask(app, "marcus", "what %LEL is the high gas alarm at compressor CS-3?")

    print("\nCross-domain -> Marcus is REFUSED on HV content (no leak that it exists):")
    ask(app, "marcus", "what is the minimum approach distance at 11 kV?")


if __name__ == "__main__":
    main()
