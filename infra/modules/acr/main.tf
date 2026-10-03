# Azure Container Registry for the MCP server image. Admin user disabled; the
# runtime identity pulls via the AcrPull role granted by identity_rbac.

resource "azurerm_container_registry" "this" {
  name                          = var.name
  resource_group_name           = var.resource_group_name
  location                      = var.location
  sku                           = "Standard"
  admin_enabled                 = false
  public_network_access_enabled = true
  tags                          = var.tags
}
