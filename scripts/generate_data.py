#!/usr/bin/env python3
"""Generate the synthetic knowledge base.

Produces, in ``data/raw/``:
  * four PDFs and one PNG poster (the "real" documents, for Azure DocIntel), and
  * a ``*.layout.json`` sidecar per document (the deterministic stand-in for
    Document Intelligence's layout output, consumed by the mock pipeline).

Deliberately plants traps so the ablation shows measurable differences:
  1. a rule whose condition and value are separated within a section, so
     no-overlap chunking splits them (overlap / section-aware keep them);
  2. an arc-flash PPE table that spans a page break, so naive extraction loses
     rows (section-aware merges the continuation);
  3. near-duplicate approach-distance rules (11 kV vs 33 kV), so reranking
     matters;
  4. exact equipment codes (TX-400, CB-22, GV-17, CS-3), so BM25 beats vectors;
  5. paraphrasable conceptual content (PPE / gloves), so vectors beat BM25.

Idempotent: safe to re-run. Outputs are committed to the repo.
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RAW = REPO_ROOT / "data" / "raw"

# ~44 words of lead-in so that, at ablation chunk size 60 / overlap 20, the
# condition and value below fall in the SAME overlap window but DIFFERENT
# no-overlap windows. This is trap #1, authored to be deterministic.
_LEADIN = (
    "This clause applies to planned maintenance on substation plant and must be "
    "read together with the isolation procedure and the site single line diagram. "
    "It covers the additional controls required for elevated system voltages and "
    "takes precedence over any general guidance where the two differ in scope or "
    "in the applied margins for safe working near exposed live conductors today."
)

# --------------------------------------------------------------------------- #
# Document definitions: each is (filename, domain, allowed_groups, blocks).
# A block is a dict {kind, text, page, level?}. kind in
# {heading, paragraph, table, ocr}.
# --------------------------------------------------------------------------- #

HV_SUBSTATION = {
    "filename": "HV_Substation_Safety_Policy.pdf",
    "doc": "HV Substation Safety Policy",
    "domain": "electrical",
    "allowed_groups": ["grp-electrical"],
    "blocks": [
        {"kind": "heading", "text": "HV Substation Safety Policy", "page": 1, "level": 1},
        {
            "kind": "paragraph",
            "page": 1,
            "text": (
                "This policy governs work on high voltage (HV) substation equipment "
                "including busbars, circuit breakers such as CB-22, and the main "
                "transformer TX-400. All work requires a permit to work and a valid "
                "isolation."
            ),
        },
        {"kind": "heading", "text": "1. Minimum Approach Distances", "page": 1, "level": 2},
        {
            "kind": "paragraph",
            "page": 1,
            "text": (
                "The minimum approach distance (the safe gap you must keep from an "
                "exposed live conductor) depends on the system voltage. Use the table "
                "below. These are near-duplicate rules with different values, so read "
                "the voltage row carefully."
            ),
        },
        {
            "kind": "table",
            "page": 1,
            "text": (
                "| Voltage | Minimum Approach Distance |\n"
                "| --- | --- |\n"
                "| 11 kV | 0.64 m |\n"
                "| 33 kV | 0.86 m |\n"
                "| 66 kV | 1.00 m |\n"
                "| 132 kV | 1.40 m |"
            ),
        },
        {"kind": "heading", "text": "2. Elevated-Voltage Clearance for TX-400", "page": 1, "level": 2},
        {
            "kind": "paragraph",
            "page": 1,
            "text": _LEADIN,
        },
        {
            "kind": "paragraph",
            "page": 1,
            "text": (
                "Where the busbar TX-400 is worked on and the system voltage exceeds "
                "33 kV without a secondary isolation point established, an additional "
                "clearance applies before any approach is permitted at all."
            ),
        },
        {
            "kind": "paragraph",
            "page": 1,
            "text": (
                "In that case the minimum approach distance shall be increased to "
                "1.20 m and a second authorized person must be present throughout."
            ),
        },
        {"kind": "heading", "text": "3. Lockout / Tagout (LOTO)", "page": 2, "level": 2},
        {
            "kind": "paragraph",
            "page": 2,
            "text": (
                "Before any work, isolate the circuit, apply locks and tags, verify "
                "dead with an approved tester, and apply circuit main earths. Never "
                "remove another person's lock. Confirm CB-22 is open and racked out."
            ),
        },
        {"kind": "heading", "text": "4. Arc-Flash PPE Categories", "page": 2, "level": 2},
        {
            "kind": "paragraph",
            "page": 2,
            "text": (
                "Select arc-rated PPE by the arc-flash incident energy category. The "
                "category table continues on the next page; use the full table."
            ),
        },
        # Trap #2: this table spans pages 2 and 3. Emitted as TWO table blocks;
        # section-aware merges them, naive fixed chunking splits them.
        {
            "kind": "table",
            "page": 2,
            "text": (
                "| Category | Incident Energy | Required Arc-Rated PPE |\n"
                "| --- | --- | --- |\n"
                "| CAT 1 | 4 cal/cm2 | Arc-rated shirt and trousers, face shield |\n"
                "| CAT 2 | 8 cal/cm2 | Arc-rated shirt and trousers, balaclava |"
            ),
        },
        {
            "kind": "table",
            "page": 3,
            "text": (
                "| CAT 3 | 25 cal/cm2 | Arc flash suit, hood, gloves |\n"
                "| CAT 4 | 40 cal/cm2 | Arc flash suit (40 cal), hood, gloves |"
            ),
        },
        {
            "kind": "paragraph",
            "page": 3,
            "text": (
                "If the incident energy cannot be determined, stop work and contact "
                "your supervisor. Do not estimate the category."
            ),
        },
    ],
}

GAS_PIPELINE = {
    "filename": "Gas_Pipeline_Compressor_Procedures.pdf",
    "doc": "Gas Pipeline Compressor Procedures",
    "domain": "gas",
    "allowed_groups": ["grp-gas"],
    "blocks": [
        {"kind": "heading", "text": "Gas Pipeline Compressor Procedures", "page": 1, "level": 1},
        {
            "kind": "paragraph",
            "page": 1,
            "text": (
                "Procedures for work on gas pipeline compressor stations, including "
                "compressor CS-3 and isolation valve GV-17. All hot work requires a "
                "hot-work permit."
            ),
        },
        {"kind": "heading", "text": "1. Gas Detection Thresholds", "page": 1, "level": 2},
        {
            "kind": "paragraph",
            "page": 1,
            "text": (
                "Continuously monitor for flammable gas with a calibrated detector. "
                "Alarm thresholds are expressed as a percentage of the lower explosive "
                "limit (%LEL)."
            ),
        },
        {
            "kind": "table",
            "page": 1,
            "text": (
                "| Level | Threshold | Action |\n"
                "| --- | --- | --- |\n"
                "| Low alarm | 10 %LEL | Investigate and ventilate |\n"
                "| High alarm | 20 %LEL | Stop work, evacuate the exclusion zone |\n"
                "| Trip | 40 %LEL | Automatic compressor shutdown |"
            ),
        },
        {"kind": "heading", "text": "2. Exclusion Zones", "page": 1, "level": 2},
        {
            "kind": "paragraph",
            "page": 1,
            "text": (
                "Establish an exclusion zone around the work. For compressor CS-3 the "
                "exclusion-zone radius is 15 m during venting. For valve GV-17 "
                "operations the exclusion-zone radius is 8 m."
            ),
        },
        {"kind": "heading", "text": "3. Hot-Work Permit Process", "page": 2, "level": 2},
        {
            "kind": "paragraph",
            "page": 2,
            "text": (
                "Obtain a hot-work permit before welding, grinding or any ignition "
                "source. Test the atmosphere, confirm it is below 10 %LEL, post a fire "
                "watch, and keep the permit on site. If gas is detected above 20 %LEL, "
                "stop work and contact your supervisor."
            ),
        },
    ],
}

CORP_HSE = {
    "filename": "Corporate_HSE_PPE_Standard.pdf",
    "doc": "Corporate HSE PPE Standard",
    "domain": "shared",
    "allowed_groups": ["grp-all"],
    "blocks": [
        {"kind": "heading", "text": "Corporate HSE PPE Standard", "page": 1, "level": 1},
        {
            "kind": "paragraph",
            "page": 1,
            "text": (
                "This corporate standard applies to all field technicians across every "
                "discipline. It covers personal protective equipment (PPE), high "
                "visibility clothing, working at height, and fatigue management."
            ),
        },
        {"kind": "heading", "text": "1. Hand Protection (Glove Classes)", "page": 1, "level": 2},
        {
            "kind": "paragraph",
            "page": 1,
            "text": (
                "Select hand protection appropriate to the hazard. Insulating gloves "
                "must be class-rated for the working voltage and inspected before use."
            ),
        },
        {
            "kind": "table",
            "page": 1,
            "text": (
                "| Glove Class | Max Working Voltage | Typical Use |\n"
                "| --- | --- | --- |\n"
                "| Class 00 | 500 V | Low voltage work |\n"
                "| Class 0 | 1000 V | LV switching |\n"
                "| Class 2 | 17000 V | HV up to 17 kV |\n"
                "| Class 4 | 36000 V | HV up to 36 kV |"
            ),
        },
        {"kind": "heading", "text": "2. High-Visibility Clothing", "page": 1, "level": 2},
        {
            "kind": "paragraph",
            "page": 1,
            "text": (
                "Wear high-visibility (hi-vis) clothing to at least class 2 on any site "
                "with vehicle or plant movement. Hi-vis must be clean and serviceable."
            ),
        },
        {"kind": "heading", "text": "3. Working at Height", "page": 2, "level": 2},
        {
            "kind": "paragraph",
            "page": 2,
            "text": (
                "Working at height means any work above 2 m where a fall could cause "
                "injury. Use fall protection, a rated harness and edge protection. "
                "Inspect the harness before each use."
            ),
        },
        {"kind": "heading", "text": "4. Fatigue Management", "page": 2, "level": 2},
        {
            "kind": "paragraph",
            "page": 2,
            "text": (
                "Do not work more than 12 hours in a shift without a documented risk "
                "assessment. Take a rest break at least every 2 hours. If you are too "
                "fatigued to work safely, stop work and contact your supervisor."
            ),
        },
    ],
}

CONFINED_SPACE = {
    "filename": "Confined_Space_Standard.pdf",
    "doc": "Confined Space Standard",
    "domain": "shared",
    "allowed_groups": ["grp-all"],
    "blocks": [
        {"kind": "heading", "text": "Confined Space Standard", "page": 1, "level": 1},
        {
            "kind": "paragraph",
            "page": 1,
            "text": (
                "A confined space is an enclosed or partially enclosed space not "
                "designed for continuous occupancy, with a risk of a hazardous "
                "atmosphere. Entry requires a confined space entry permit."
            ),
        },
        {"kind": "heading", "text": "1. Entry Permit", "page": 1, "level": 2},
        {"kind": "heading", "text": "1.1 Pre-Entry Checks", "page": 1, "level": 3},
        {
            "kind": "paragraph",
            "page": 1,
            "text": (
                "Before entry, test the atmosphere for oxygen, flammable gas and toxic "
                "gas. Oxygen must be between 19.5% and 23.5%. Flammable gas must be "
                "below 10 %LEL. Isolate all inflows and verify lockout."
            ),
        },
        {"kind": "heading", "text": "1.2 Attendant and Rescue", "page": 1, "level": 3},
        {
            "kind": "paragraph",
            "page": 1,
            "text": (
                "A trained attendant must remain outside the space for the duration of "
                "the entry. A rescue plan and retrieval equipment must be in place "
                "before anyone enters."
            ),
        },
        {"kind": "heading", "text": "2. Ventilation", "page": 2, "level": 2},
        {
            "kind": "paragraph",
            "page": 2,
            "text": (
                "Ventilate continuously during occupancy. If any gas reading exceeds "
                "its threshold, evacuate the space immediately, stop work and contact "
                "your supervisor before re-entry."
            ),
        },
    ],
}

# Poster is image-only; its text is reached via OCR. It is deliberately NOT a PDF.
LIFTING_POSTER = {
    "filename": "Lifting_Rigging_Poster.png",
    "doc": "Lifting and Rigging Poster",
    "domain": "shared",
    "allowed_groups": ["grp-all"],
    "blocks": [
        {
            "kind": "ocr",
            "page": 1,
            "text": (
                "LIFTING AND RIGGING SAFETY\n"
                "Never stand or walk under a suspended load.\n"
                "Inspect slings and shackles before every lift.\n"
                "Know the load weight and the sling Working Load Limit.\n"
                "Use a tag line to control the load.\n"
                "Sling angle factor table:\n"
                "| Sling Angle | Capacity Factor |\n"
                "| 90 degrees | 1.00 |\n"
                "| 60 degrees | 0.87 |\n"
                "| 45 degrees | 0.71 |\n"
                "| 30 degrees | 0.50 |\n"
                "If in doubt about the lift plan, stop work and contact your supervisor."
            ),
        }
    ],
}

DOCUMENTS = [HV_SUBSTATION, GAS_PIPELINE, CORP_HSE, CONFINED_SPACE, LIFTING_POSTER]


# --------------------------------------------------------------------------- #
# Rendering                                                                    #
# --------------------------------------------------------------------------- #
def write_layout(doc: dict) -> Path:
    out = RAW / (Path(doc["filename"]).stem + ".layout.json")
    payload = {
        "doc": doc["doc"],
        "domain": doc["domain"],
        "allowed_groups": doc["allowed_groups"],
        "blocks": doc["blocks"],
    }
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return out


def _md_table_rows(md: str) -> list[list[str]]:
    rows = []
    for line in md.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if all(set(c) <= {"-", ":", ""} for c in cells):
            continue  # separator row
        rows.append(cells)
    return rows


def render_pdf(doc: dict) -> Path:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import (
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    out = RAW / doc["filename"]
    styles = getSampleStyleSheet()
    story = []
    current_page = 1
    for block in doc["blocks"]:
        if int(block.get("page", 1)) > current_page:
            story.append(PageBreak())
            current_page = int(block["page"])
        kind = block["kind"]
        if kind == "heading":
            level = block.get("level", 1)
            style = styles["Title"] if level == 1 else styles["Heading2"]
            story.append(Paragraph(block["text"], style))
            story.append(Spacer(1, 6))
        elif kind == "paragraph":
            story.append(Paragraph(block["text"], styles["BodyText"]))
            story.append(Spacer(1, 6))
        elif kind == "table":
            rows = _md_table_rows(block["text"])
            if rows:
                table = Table(rows, hAlign="LEFT")
                table.setStyle(
                    TableStyle(
                        [
                            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                            ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                            ("FONTSIZE", (0, 0), (-1, -1), 9),
                        ]
                    )
                )
                story.append(table)
                story.append(Spacer(1, 6))
    SimpleDocTemplate(str(out), pagesize=A4, title=doc["doc"]).build(story)
    return out


def render_png(doc: dict) -> Path:
    from PIL import Image, ImageDraw

    out = RAW / doc["filename"]
    width, height = 800, 1000
    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)
    y = 30
    for block in doc["blocks"]:
        for line in block["text"].splitlines():
            draw.text((40, y), line, fill="black")
            y += 28
    img.save(out)
    return out


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    manifest = []
    for doc in DOCUMENTS:
        layout = write_layout(doc)
        asset = render_pdf(doc) if doc["filename"].endswith(".pdf") else render_png(doc)
        manifest.append(
            {
                "source": str(asset.relative_to(REPO_ROOT)),
                "doc": doc["doc"],
                "domain": doc["domain"],
                "allowed_groups": doc["allowed_groups"],
            }
        )
        print(f"  wrote {asset.name} + {layout.name}")
    (REPO_ROOT / "data" / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    print(f"Generated {len(DOCUMENTS)} documents in {RAW}")


if __name__ == "__main__":
    main()
