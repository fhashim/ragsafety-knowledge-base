#!/usr/bin/env python3
"""Demo 7 — Cost & tracing: run a session with spans, then aggregate cost."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import subprocess

from _common import ask, banner, make_app


def main():
    banner("Demo 7: Cost & tracing (OpenTelemetry spans + audit cost aggregation)")
    print("Running a short session WITH console spans (GenAI semantic conventions):")
    app = make_app(show_traces=True)
    ask(app, "priya", "approach distance at 33 kV and arc flash PPE for cat 3?")

    print("\nNow aggregate cost from the audit table:")
    root = pathlib.Path(__file__).resolve().parents[1]
    subprocess.run([sys.executable, str(root / "scripts" / "cost_report.py")], check=False)


if __name__ == "__main__":
    main()
