# One user-assigned managed identity for the runtime (app + jobs) and ALL of its
# least-privilege role assignments. Terraform owns every RBAC assignment.

resource "azurerm_user_assigned_identity" "runtime" {
  name                = var.name
  resource_group_name = var.resource_group_name
  location            = var.location
  tags                = var.tags
}

locals {
  principal_id = azurerm_user_assigned_identity.runtime.principal_id

  # role definition name => scope resource id. Scopes are the specific resources,
  # not the whole subscription/RG, to keep the grants least-privilege.
  assignments = {
    # Foundry / Cognitive Services data plane.
    "Cognitive Services OpenAI User" = var.foundry_id
    "Cognitive Services User"        = var.foundry_id
    # Foundry project authoring (agent/tool registration, evaluation).
    # VERIFY: role recently renamed to the "Foundry" family; GUID unchanged.
    "Azure AI Developer" = var.foundry_project_id
    # AI Search data + service.
    "Search Index Data Contributor" = var.search_id
    "Search Service Contributor"    = var.search_id
    # Storage: audit blob + table.
    "Storage Blob Data Contributor"  = var.storage_id
    "Storage Table Data Contributor" = var.storage_id
    # Key Vault secrets (RBAC auth).
    "Key Vault Secrets User" = var.keyvault_id
    # Pull the MCP image.
    "AcrPull" = var.acr_id
  }
}

resource "azurerm_role_assignment" "runtime" {
  for_each             = local.assignments
  scope                = each.value
  role_definition_name = each.key
  principal_id         = local.principal_id
}
