"""Central configuration via pydantic-settings.

All configuration flows through :class:`Settings`. Environment variables use the
``RAGSAFETY_`` prefix (see ``.env.example``). Static data that is not
per-environment (pricing, personas, eval thresholds, the mock concept lexicon)
lives in ``config/*.yaml`` and is loaded by the helpers at the bottom.
"""

from __future__ import annotations

import functools
from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo root = two levels up from this file (src/ragsafety/settings.py -> repo).
REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = REPO_ROOT / "config"
DATA_DIR = REPO_ROOT / "data"


class ChunkStrategy(str, Enum):
    FIXED_NO_OVERLAP = "fixed_no_overlap"
    FIXED_OVERLAP = "fixed_overlap"
    SECTION_AWARE = "section_aware"


class RetrievalMode(str, Enum):
    VECTOR = "vector"
    BM25 = "bm25"
    HYBRID = "hybrid"
    HYBRID_RERANK = "hybrid_rerank"


class Settings(BaseSettings):
    """Runtime settings. In mock mode the Azure endpoint fields are unused."""

    model_config = SettingsConfigDict(
        env_prefix="RAGSAFETY_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- mode ---
    mock_mode: bool = True
    log_level: str = "INFO"
    # When true, skip the console span exporter (keeps demo output readable).
    quiet_tracing: bool = False

    # --- chunking / retrieval ---
    chunk_strategy: ChunkStrategy = ChunkStrategy.SECTION_AWARE
    chunk_size_tokens: int = 320
    chunk_overlap_tokens: int = 64
    retrieval_mode: RetrievalMode = RetrievalMode.HYBRID_RERANK
    top_k: int = 5

    # --- feature flags ---
    enable_bing_grounding: bool = False

    # --- MCP client (used by the web explorer to call the deployed server) ---
    # URL of the running MCP server, including the /mcp path. For the Azure
    # Container App this is https://<app>.<region>.azurecontainerapps.io/mcp.
    mcp_url: str = "http://127.0.0.1:8000/mcp"
    # Static bearer token for the MCP endpoint (optional). If set it takes
    # precedence over AAD token acquisition.
    mcp_bearer_token: str = ""
    # Entra ID scope to acquire an access token for via DefaultAzureCredential
    # (e.g. "api://<app-client-id>/.default"). Used when no static token is set.
    mcp_aad_scope: str = ""
    # Extra headers as a JSON object string, e.g. '{"X-Functions-Key": "..."}'.
    mcp_headers_json: str = ""
    mcp_timeout_seconds: float = 60.0

    # --- active persona ---
    persona: str = "priya"

    # --- Foundry ---
    foundry_endpoint: str = ""
    foundry_project_endpoint: str = ""
    chat_small_deployment: str = "gpt-4o-mini"
    chat_large_deployment: str = "gpt-4o"
    embedding_deployment: str = "text-embedding-3-large"
    embedding_dim: int = 256

    # --- AI Search ---
    search_endpoint: str = ""
    search_index_prefix: str = "ragsafety"

    # --- Document Intelligence ---
    docintel_endpoint: str = ""

    # --- Content Safety ---
    content_safety_endpoint: str = ""

    # --- Storage / audit ---
    storage_account: str = ""
    audit_table: str = "ragaudit"
    audit_blob_container: str = "audit-raw"

    # --- Observability ---
    applicationinsights_connection_string: str = Field(
        default="", alias="APPLICATIONINSIGHTS_CONNECTION_STRING"
    )

    # --- Runtime identity ---
    managed_identity_client_id: str = ""

    def index_name(self, strategy: ChunkStrategy | None = None) -> str:
        """Per-strategy index name so ablations compare like with like."""
        return self.index_name_from_strategy((strategy or self.chunk_strategy).value)

    def index_name_from_strategy(self, strategy: str) -> str:
        return f"{self.search_index_prefix}-{strategy.replace('_', '-')}"

    @property
    def audit_dir(self) -> Path:
        """Local audit sink used in mock mode (mirrors Table + blob)."""
        return REPO_ROOT / "audit_local"


@functools.lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


# --------------------------------------------------------------------------- #
# Static YAML config loaders (cached).                                        #
# --------------------------------------------------------------------------- #
@functools.cache
def _load_yaml(name: str) -> dict[str, Any]:
    path = CONFIG_DIR / name
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def load_personas() -> dict[str, Any]:
    return _load_yaml("personas.yaml")


def load_pricing() -> dict[str, Any]:
    return _load_yaml("pricing.yaml")


def load_eval_thresholds() -> dict[str, Any]:
    return _load_yaml("eval_thresholds.yaml")


def load_concepts() -> dict[str, list[str]]:
    """Concept lexicon used by the mock embedding model (see clients/embeddings)."""
    return _load_yaml("concepts.yaml")


def load_bing_allowlist() -> list[str]:
    data = _load_yaml("bing_allowlist.yaml")
    return list(data.get("allowed_domains", []))
