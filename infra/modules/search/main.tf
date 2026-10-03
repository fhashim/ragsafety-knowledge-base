# Azure AI Search with the semantic ranker enabled and local (key) auth disabled.
# Vector + BM25 + RRF + semantic ranking are all data-plane features of this SKU;
# the index schema itself is created idempotently by Python (see ownership table).

resource "azurerm_search_service" "this" {
  name                = var.name
  resource_group_name = var.resource_group_name
  location            = var.location
  sku                 = var.sku
  # Semantic ranker: "free" (limited) or "standard". Required for reranking.
  semantic_search_sku = var.semantic_search_sku
  # Entra-ID-only data plane (no admin/query keys).
  local_authentication_enabled = false
  tags                         = var.tags

  identity {
    type = "SystemAssigned"
  }
}
