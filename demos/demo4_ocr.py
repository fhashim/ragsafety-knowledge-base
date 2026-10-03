#!/usr/bin/env python3
"""Demo 4 — OCR: a question answered only from the image-only lifting poster."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _common import ask, banner, make_app


def main():
    app = make_app()
    banner("Demo 4: OCR-only source (lifting & rigging poster PNG)")
    ask(app, "marcus", "what is the sling capacity factor at 45 degrees for the lift?")


if __name__ == "__main__":
    main()
