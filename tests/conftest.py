"""Shared test fixtures. Forces mock mode before any settings are read."""

from __future__ import annotations

import os

os.environ.setdefault("RAGSAFETY_MOCK_MODE", "true")
os.environ.setdefault("RAGSAFETY_LOG_LEVEL", "WARNING")

import pytest

from ragsafety.app import RagSafetyApp
from ragsafety.settings import ChunkStrategy, Settings


@pytest.fixture(scope="session")
def settings() -> Settings:
    return Settings(mock_mode=True)


@pytest.fixture(scope="session")
def app(settings) -> RagSafetyApp:
    """An app with the knowledge base ingested for all three chunk strategies."""
    a = RagSafetyApp(settings=settings)
    a.ingest(list(ChunkStrategy))
    return a
