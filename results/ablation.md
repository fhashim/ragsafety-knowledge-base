# Retrieval & Chunking Ablation

Golden set run across chunking strategy x retrieval mode. recall@5 and MRR are measured at the **chunk** level (did the chunk that actually holds the fact rank?), over the 6 retrieval categories (keyword, semantic, table, multi-hop, OCR, messy-prompt).

## Chunking profile

| Chunking | chunks | avg tokens/chunk |
| --- | --- | --- |
| fixed_no_overlap | 6 | 148 |
| fixed_overlap | 6 | 157 |
| section_aware | 24 | 42 |

Fixed strategies over-split the corpus (more, smaller chunks and, with overlap, duplicated text => higher embedding/query cost). Section-aware produces fewer, self-contained chunks that each carry their heading path.

## Metrics

| Chunking | Retrieval | recall@5 | MRR | groundedness | avg cost $ | p50 ms |
| --- | --- | --- | --- | --- | --- | --- |
| fixed_no_overlap | vector | 1.00 | 0.95 | 1.00 | 0.00678 | 1.51 |
| fixed_no_overlap | bm25 | 1.00 | 1.00 | 1.00 | 0.00677 | 1.48 |
| fixed_no_overlap | hybrid | 1.00 | 0.98 | 1.00 | 0.00675 | 1.47 |
| fixed_no_overlap | hybrid_rerank | 1.00 | 0.98 | 1.00 | 0.00674 | 1.47 |
| fixed_overlap | vector | 1.00 | 0.95 | 1.00 | 0.00689 | 1.51 |
| fixed_overlap | bm25 | 1.00 | 0.98 | 1.00 | 0.00688 | 1.48 |
| fixed_overlap | hybrid | 1.00 | 0.96 | 1.00 | 0.00684 | 1.49 |
| fixed_overlap | hybrid_rerank | 1.00 | 0.98 | 1.00 | 0.00684 | 1.50 |
| section_aware | vector | 1.00 | 0.75 | 1.00 | 0.00499 | 1.36 |
| section_aware | bm25 | 1.00 | 0.93 | 1.00 | 0.00497 | 1.33 |
| section_aware | hybrid | 1.00 | 0.91 | 1.00 | 0.00511 | 1.32 |
| section_aware | hybrid_rerank | 1.00 | 0.89 | 1.00 | 0.00527 | 1.36 |

## Worked examples — retrieval mode (section-aware chunking)

### `kw2` — What is the exclusion zone radius for GV-17?
_Exact code (GV-17): BM25 pins it; pure vector is weaker._

| Retrieval mode | Top-1 chunk (doc / section) | Fact chunk rank | In top-5 |
| --- | --- | --- | --- |
| vector | Gas Pipeline Compressor Procedures / Gas Pipel | 1 | yes |
| bm25 | Gas Pipeline Compressor Procedures / Gas Pipel | 1 | yes |
| hybrid | Gas Pipeline Compressor Procedures / Gas Pipel | 1 | yes |
| hybrid_rerank | Gas Pipeline Compressor Procedures / Gas Pipel | 1 | yes |

### `sem3` — what clothing makes me visible to vehicles and plant on site?
_Paraphrase (visible clothing -> hi-vis): vectors bridge the wording._

| Retrieval mode | Top-1 chunk (doc / section) | Fact chunk rank | In top-5 |
| --- | --- | --- | --- |
| vector | Corporate HSE PPE Standard / Corporate HSE PPE | 1 | yes |
| bm25 | Corporate HSE PPE Standard / Corporate HSE PPE | 1 | yes |
| hybrid | Corporate HSE PPE Standard / Corporate HSE PPE | 1 | yes |
| hybrid_rerank | Corporate HSE PPE Standard / Corporate HSE PPE | 1 | yes |

### `tab2` — minimum approach distance at 33 kV
_Near-duplicate rows (33 kV vs 11 kV): reranking sharpens the top hit._

| Retrieval mode | Top-1 chunk (doc / section) | Fact chunk rank | In top-5 |
| --- | --- | --- | --- |
| vector | HV Substation Safety Policy / HV Substation Sa | 1 | yes |
| bm25 | HV Substation Safety Policy / HV Substation Sa | 1 | yes |
| hybrid | HV Substation Safety Policy / HV Substation Sa | 1 | yes |
| hybrid_rerank | HV Substation Safety Policy / HV Substation Sa | 2 | yes |

### `ocr1` — sling capacity factor at 45 degrees
_OCR-only poster: evidence exists only via OCR of the image._

| Retrieval mode | Top-1 chunk (doc / section) | Fact chunk rank | In top-5 |
| --- | --- | --- | --- |
| vector | Lifting and Rigging Poster / (root) | 1 | yes |
| bm25 | Lifting and Rigging Poster / (root) | 1 | yes |
| hybrid | Lifting and Rigging Poster / (root) | 1 | yes |
| hybrid_rerank | Lifting and Rigging Poster / (root) | 1 | yes |

## Worked example — chunking (page-spanning arc-flash table)
_The arc-flash PPE table spans pages 2-3 (CAT 1-2 on p2, CAT 3-4 on p3). This looks at the chunk that holds `40 cal` (CAT 4): does one chunk hold the whole table, is it typed as a table, and does it keep its heading path?_

| Chunking | chunk type of '40 cal' | all CAT 1-4 in one chunk | heading kept |
| --- | --- | --- | --- |
| fixed_no_overlap | text | no | no |
| fixed_overlap | text | yes | no |
| section_aware | table | yes | yes |

> Numbers vary per run on real Azure (embeddings, ranker, model). The relative ordering is the lesson, not the absolute values.
