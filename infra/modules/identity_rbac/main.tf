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

# Data-plane roles for the CI pipeline service principal, so the ingest and
# deploy jobs can create the Search index, embed + upload documents, parse with
# Document Intelligence, push the image, and register the Foundry agent. These
# were previously granted ad hoc; declaring them here makes them reproducible
# IaC. Gated on deployer_principal_id (empty => skip). Every role GUID is within
# the deployer's RBAC-Administrator ABAC allow-list (infra/bootstrap), so the
# pipeline can create these assignments for itself.
locals {
  deployer_assignments = var.deployer_principal_id == "" ? {} : {
    "Cognitive Services OpenAI User" = var.foundry_id               # embeddings
    "Cognitive Services User"        = var.document_intelligence_id # layout/OCR parse
    "Search Service Contributor"     = var.search_id                # create index schema
    "Search Index Data Contributor"  = var.search_id                # upload documents
    "AcrPush"                        = var.acr_id                   # push the MCP image
    "Azure AI Developer"             = var.foundry_project_id       # register agent + MCP tool
  }
}

resource "azurerm_role_assignment" "deployer" {
  for_each             = local.deployer_assignments
  scope                = each.value
  role_definition_name = each.key
  principal_id         = var.deployer_principal_id
}
