"""Document Intelligence clients.

The mock loads a sidecar ``*.layout.json`` emitted next to each synthetic
document by ``scripts/generate_data.py``. That JSON is the deterministic stand-in
for Document Intelligence's layout output: heading hierarchy, paragraphs, tables
as Markdown, and OCR text for the poster. The real client calls the Azure
Document Intelligence *prebuilt-layout* model and converts its output to the same
``DocBlock`` shape, so the chunkers downstream never know the difference.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..settings import Settings
from .base import DocBlock, DocIntelClient, ParsedDocument


def layout_path_for(source_path: str) -> Path:
    p = Path(source_path)
    return p.with_suffix(".layout.json")


class MockDocIntelClient(DocIntelClient):
    def parse(self, source_path: str) -> ParsedDocument:
        layout = layout_path_for(source_path)
        if not layout.exists():
            raise FileNotFoundError(
                f"Missing layout sidecar {layout}. Run scripts/generate_data.py first."
            )
        data = json.loads(layout.read_text(encoding="utf-8"))
        blocks = [
            DocBlock(
                kind=b["kind"],
                text=b["text"],
                page=int(b.get("page", 1)),
                level=int(b.get("level", 0)),
            )
            for b in data["blocks"]
        ]
        return ParsedDocument(
            doc=data["doc"],
            domain=data["domain"],
            allowed_groups=data["allowed_groups"],
            blocks=blocks,
        )


class AzureDocIntelClient(DocIntelClient):
    """Azure Document Intelligence (prebuilt-layout). Imported lazily."""

    def __init__(self, settings: Settings) -> None:  # pragma: no cover - real-Azure only
        self.settings = settings

    def parse(self, source_path: str) -> ParsedDocument:  # pragma: no cover
        from azure.ai.documentintelligence import DocumentIntelligenceClient
        from azure.ai.documentintelligence.models import DocumentContentFormat
        from azure.identity import DefaultAzureCredential

        client = DocumentIntelligenceClient(
            endpoint=self.settings.docintel_endpoint,
            credential=DefaultAzureCredential(
                managed_identity_client_id=self.settings.managed_identity_client_id or None
            ),
        )
        with open(source_path, "rb") as fh:
            poller = client.begin_analyze_document(
                "prebuilt-layout",
                body=fh,
                output_content_format=DocumentContentFormat.MARKDOWN,
            )
        result = poller.result()
        # VERIFY: map result.paragraphs/tables/sections to DocBlock for your
        #         Document Intelligence SDK version. The markdown output already
        #         preserves tables; here we split it into coarse blocks by page.
        blocks: list[DocBlock] = []
        for page_idx, page in enumerate(getattr(result, "pages", []) or [], start=1):
            md = getattr(page, "markdown", None) or ""
            if md:
                blocks.append(DocBlock(kind="paragraph", text=md, page=page_idx))
        if not blocks and getattr(result, "content", None):
            blocks.append(DocBlock(kind="paragraph", text=result.content, page=1))
        # Metadata (domain/allowed_groups) is not in the document; callers pass it
        # via the ingest manifest. Defaults here are placeholders.
        return ParsedDocument(
            doc=Path(source_path).name, domain="shared", allowed_groups=["grp-all"], blocks=blocks
        )
