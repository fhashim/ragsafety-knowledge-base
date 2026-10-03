# Azure AI Content Safety for Prompt Shields, harm categories and groundedness.
# Entra-ID-only; custom subdomain required for token auth.

resource "azurerm_cognitive_account" "this" {
  name                          = var.name
  resource_group_name           = var.resource_group_name
  location                      = var.location
  kind                          = "ContentSafety"
  sku_name                      = var.sku_name
  custom_subdomain_name         = var.name
  local_auth_enabled            = false
  public_network_access_enabled = true
  tags                          = var.tags

  identity {
    type = "SystemAssigned"
  }
}
