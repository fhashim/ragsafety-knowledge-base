"""Parse stage: document bytes -> layout-aware blocks (Document Intelligence)."""

from __future__ import annotations

from ..clients import Clients
from ..clients.base import ParsedDocument


def parse_document(clients: Clients, source_path: str) -> ParsedDocument:
    """Parse a PDF/PNG into heading/paragraph/table/ocr blocks."""
    return clients.docintel.parse(source_path)
