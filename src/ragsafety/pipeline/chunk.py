"""Chunking — three switchable strategies.

The strategies are deliberately different so the ablation can measure the cost of
getting chunking wrong:

* ``fixed_no_overlap`` — flatten the whole document to one token stream and cut
  fixed windows. Ignores structure. A rule whose condition and value straddle a
  window boundary gets split; a table that spans a page gets cut mid-row.
* ``fixed_overlap`` — same, but windows overlap, so a straddling rule survives in
  at least one window.
* ``section_aware`` — split on headings, never split a table (consecutive table
  blocks that continue across a page are merged), prepend the heading path as
  context, and add overlap only *within* a section.

Only ``section_aware`` reads the layout structure; that is what the traps in the
synthetic data are designed to expose.
"""

from __future__ import annotations

from ..clients.base import DocBlock, ParsedDocument
from ..schema import Chunk, ContentType, Domain
from ..settings import ChunkStrategy

_WORD = str  # a whitespace-delimited token kept verbatim for reconstruction


def _words(text: str) -> list[_WORD]:
    return text.split()


def _window(words: list[_WORD], size: int, overlap: int) -> list[str]:
    if not words:
        return []
    if size <= 0:
        return [" ".join(words)]
    step = max(1, size - max(0, overlap))
    out: list[str] = []
    i = 0
    while i < len(words):
        out.append(" ".join(words[i : i + size]))
        if i + size >= len(words):
            break
        i += step
    return out


def _mk(
    doc: str,
    domain: str,
    allowed_groups: list[str],
    strategy: str,
    idx: int,
    text: str,
    page: int,
    section_path: list[str],
    content_type: ContentType,
) -> Chunk:
    return Chunk(
        chunk_id=f"{doc}::{strategy}::{idx}",
        doc=doc,
        domain=Domain(domain),
        section_path=list(section_path),
        page=page,
        content_type=content_type,
        allowed_groups=list(allowed_groups),
        strategy=strategy,
        text=text,
    )


def _flatten(blocks: list[DocBlock]) -> tuple[list[_WORD], dict[int, int]]:
    """Flatten blocks to a word stream, tracking word-index -> page for provenance."""
    words: list[_WORD] = []
    word_page: dict[int, int] = {}
    for b in blocks:
        for w in _words(b.text):
            word_page[len(words)] = b.page
            words.append(w)
    return words, word_page


def _fixed(
    parsed: ParsedDocument, strategy: ChunkStrategy, size: int, overlap: int
) -> list[Chunk]:
    words, word_page = _flatten(parsed.blocks)
    chunks: list[Chunk] = []
    step = max(1, size - overlap)
    for idx, start in enumerate(range(0, max(1, len(words)), step)):
        window_words = words[start : start + size]
        if not window_words:
            break
        page = word_page.get(start, 1)
        chunks.append(
            _mk(
                parsed.doc,
                parsed.domain,
                parsed.allowed_groups,
                strategy.value,
                idx,
                " ".join(window_words),
                page,
                [],  # naive: no heading context
                ContentType.TEXT,
            )
        )
        if start + size >= len(words):
            break
    return chunks


def _merge_table_runs(blocks: list[DocBlock]) -> list[DocBlock]:
    """Merge consecutive table blocks (a table continued across a page break).

    The continuation block repeats no header row, so we just append its rows.
    """
    merged: list[DocBlock] = []
    for b in blocks:
        if b.kind == "table" and merged and merged[-1].kind == "table":
            prev = merged[-1]
            merged[-1] = DocBlock(
                kind="table",
                text=prev.text.rstrip() + "\n" + b.text.strip(),
                page=prev.page,
                level=prev.level,
            )
        else:
            merged.append(b)
    return merged


def _section_aware(parsed: ParsedDocument, size: int, overlap: int) -> list[Chunk]:
    blocks = _merge_table_runs(parsed.blocks)
    strategy = ChunkStrategy.SECTION_AWARE.value
    chunks: list[Chunk] = []
    heading_stack: list[tuple[int, str]] = []  # (level, text)
    buf: list[str] = []  # pending paragraph text in the current section
    buf_page = 1
    idx = 0

    def heading_path() -> list[str]:
        return [h for _, h in heading_stack]

    def flush_text():
        nonlocal idx, buf
        if not buf:
            return
        path = heading_path()
        prefix = ("Section: " + " > ".join(path) + "\n\n") if path else ""
        body = " ".join(buf)
        for w in _window(_words(body), size, overlap):
            chunks.append(
                _mk(
                    parsed.doc,
                    parsed.domain,
                    parsed.allowed_groups,
                    strategy,
                    idx,
                    prefix + w,
                    buf_page,
                    path,
                    ContentType.TEXT,
                )
            )
            idx += 1
        buf = []

    for b in blocks:
        if b.kind == "heading":
            flush_text()
            # Pop deeper/equal headings, then push this one.
            while heading_stack and heading_stack[-1][0] >= b.level:
                heading_stack.pop()
            heading_stack.append((b.level, b.text.strip().lstrip("#").strip()))
        elif b.kind == "table":
            flush_text()
            path = heading_path()
            prefix = ("Section: " + " > ".join(path) + "\n\n") if path else ""
            chunks.append(
                _mk(
                    parsed.doc,
                    parsed.domain,
                    parsed.allowed_groups,
                    strategy,
                    idx,
                    prefix + b.text.strip(),
                    b.page,
                    path,
                    ContentType.TABLE,
                )
            )
            idx += 1
        elif b.kind == "ocr":
            flush_text()
            path = heading_path()
            prefix = ("Section: " + " > ".join(path) + "\n\n") if path else ""
            chunks.append(
                _mk(
                    parsed.doc,
                    parsed.domain,
                    parsed.allowed_groups,
                    strategy,
                    idx,
                    prefix + b.text.strip(),
                    b.page,
                    path,
                    ContentType.OCR,
                )
            )
            idx += 1
        else:  # paragraph
            if not buf:
                buf_page = b.page
            buf.append(b.text.strip())
    flush_text()
    return chunks


def chunk_document(
    parsed: ParsedDocument,
    strategy: ChunkStrategy,
    *,
    size_tokens: int,
    overlap_tokens: int,
) -> list[Chunk]:
    """Chunk a parsed document with the chosen strategy."""
    if strategy == ChunkStrategy.FIXED_NO_OVERLAP:
        return _fixed(parsed, strategy, size_tokens, 0)
    if strategy == ChunkStrategy.FIXED_OVERLAP:
        return _fixed(parsed, strategy, size_tokens, overlap_tokens)
    return _section_aware(parsed, size_tokens, overlap_tokens)
