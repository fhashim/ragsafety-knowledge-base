"""Unit tests for extraction, embeddings, security, cost and PII redaction."""

from __future__ import annotations

import math

import pytest

from ragsafety.clients.embeddings import MockEmbeddingClient
from ragsafety.cost import cost_usd
from ragsafety.extraction import extract_values, value_supported
from ragsafety.schema import TokenUsage
from ragsafety.security import UnknownPersona, persona_groups
from ragsafety.util import count_tokens, redact_pii


def _cos(a, b):
    return sum(x * y for x, y in zip(a, b, strict=False)) / (
        (math.sqrt(sum(x * x for x in a)) or 1) * (math.sqrt(sum(y * y for y in b)) or 1)
    )


def test_extract_values():
    vals = extract_values("Keep 0.64 m at 11 kV; alarm at 10 %LEL and 8 cal/cm2")
    joined = " ".join(vals).lower()
    assert "0.64 m" in joined and "11 kv" in joined and "10 %lel" in joined


def test_value_supported_ignores_spacing():
    assert value_supported("the limit is 0.64m here", "0.64 m")
    assert not value_supported("nothing relevant", "0.64 m")


def test_mock_embedding_paraphrase_closer_than_unrelated():
    emb = MockEmbeddingClient(dim=256)
    gloves = emb.embed(["gloves and hand protection"])[0]
    hands = emb.embed(["which hand protection is required"])[0]
    fatigue = emb.embed(["rest breaks and fatigue on shift"])[0]
    assert _cos(gloves, hands) > _cos(gloves, fatigue)


def test_persona_groups():
    assert "grp-electrical" in persona_groups("priya")
    assert "grp-gas" in persona_groups("marcus")
    assert "grp-all" in persona_groups("priya")
    with pytest.raises(UnknownPersona):
        persona_groups("nobody")


def test_cost_positive_for_tokens():
    usage = TokenUsage(model="gpt-4o", prompt_tokens=1000, completion_tokens=500)
    assert cost_usd(usage) > 0


def test_cost_zero_for_empty():
    assert cost_usd(TokenUsage(model="gpt-4o")) == 0.0


def test_redact_pii():
    out = redact_pii("email a@b.com call +1 415 555 2671 id 123456789012")
    assert "a@b.com" not in out
    assert "REDACTED" in out


def test_count_tokens():
    assert count_tokens("TX-400 at 11 kV") == 4
