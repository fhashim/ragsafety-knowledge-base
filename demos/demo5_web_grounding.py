#!/usr/bin/env python3
"""Demo 5 — Web grounding: regulator guidance labeled separately from policy."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _common import ask, banner, make_app


def main():
    app = make_app(enable_web=True)
    banner("Demo 5: Web grounding (regulator allow-list; web labeled separately)")
    ask(app, "marcus", "regulator guidance on confined space entry and gas detection?")
    print("\n  Note: web content is labeled separately; internal policy wins on conflict.")


if __name__ == "__main__":
    main()
