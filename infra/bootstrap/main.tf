data "azurerm_subscription" "current" {}
data "azuread_client_config" "current" {}

resource "random_string" "suffix" {
  length  = 5
  special = false
  upper   = false
  numeric = true
}

# --- Terraform remote-state storage ---------------------------------------
resource "azurerm_resource_group" "state" {
  name     = "rg-${var.project}-tfstate"
  location = var.location
  tags     = var.tags
}

resource "azurerm_storage_account" "state" {
  name                            = substr("st${var.project}tfstate${random_string.suffix.result}", 0, 24)
  resource_group_name             = azurerm_resource_group.state.name
  location                        = var.location
  account_tier                    = "Standard"
  account_replication_type        = "LRS"
  min_tls_version                 = "TLS1_2"
  shared_access_key_enabled       = false # Entra-ID + OIDC only
  allow_nested_items_to_be_public = false
  tags                            = var.tags

  blob_properties {
    versioning_enabled = true
    delete_retention_policy {
      days = 30
    }
  }
}

resource "azurerm_storage_container" "state" {
  name                  = var.state_container_name
  storage_account_id    = azurerm_storage_account.state.id
  container_access_type = "private"
}

# --- Pipeline app registration + service principal -------------------------
resource "azuread_application" "pipeline" {
  display_name = "${var.project}-github-pipeline"
  owners       = [data.azuread_client_config.current.object_id]
}

resource "azuread_service_principal" "pipeline" {
  client_id = azuread_application.pipeline.client_id
  owners    = [data.azuread_client_config.current.object_id]
}

# GitHub OIDC federated credentials: one per environment + pull requests.
resource "azuread_application_federated_identity_credential" "env" {
  for_each       = toset(var.environments)
  application_id = azuread_application.pipeline.id
  display_name   = "github-${each.value}"
  issuer         = "https://token.actions.githubusercontent.com"
  audiences      = ["api://AzureADTokenExchange"]
  subject        = "repo:${var.github_org}/${var.github_repo}:environment:${each.value}"
}

resource "azuread_application_federated_identity_credential" "pull_request" {
  application_id = azuread_application.pipeline.id
  display_name   = "github-pull-request"
  issuer         = "https://token.actions.githubusercontent.com"
  audiences      = ["api://AzureADTokenExchange"]
  subject        = "repo:${var.github_org}/${var.github_repo}:pull_request"
}

# --- Entra groups for the two technician personas --------------------------
resource "azuread_group" "electrical" {
  display_name     = "grp-electrical"
  security_enabled = true
  owners           = [data.azuread_client_config.current.object_id]
}

resource "azuread_group" "gas" {
  display_name     = "grp-gas"
  security_enabled = true
  owners           = [data.azuread_client_config.current.object_id]
}

# --- Deployer (pipeline SP) role assignments -------------------------------
# Contributor to create resources, and RBAC Administrator (constrained by an
# ABAC condition to only the roles this solution assigns) to let Terraform
# create those role assignments. Scoped to the subscription here; narrow to the
# target resource groups in production.
resource "azurerm_role_assignment" "contributor" {
  scope                = data.azurerm_subscription.current.id
  role_definition_name = "Contributor"
  principal_id         = azuread_service_principal.pipeline.object_id
}

resource "azurerm_role_assignment" "rbac_admin" {
  scope                = data.azurerm_subscription.current.id
  role_definition_name = "Role Based Access Control Administrator"
  principal_id         = azuread_service_principal.pipeline.object_id

  # Constrain delegated role assignments to the roles this solution uses.
  # VERIFY: keep this GUID list in sync with modules/identity_rbac.
  condition_version = "2.0"
  condition         = <<-COND
    (
      (
        !(ActionMatches{'Microsoft.Authorization/roleAssignments/write'})
      )
      OR
      (
        @Request[Microsoft.Authorization/roleAssignments:RoleDefinitionId] ForAnyOfAnyValues:GuidEquals {
          a97b65f3-24c7-4388-baec-2e87135dc908,
          a001fd3d-188f-4b5d-821b-7da978bf7442,
          64702f94-c441-49e6-a78b-ef80e0188fee,
          8ebe5a00-799e-43f5-93ac-243d3dce84a7,
          7ca78c08-252a-4471-8644-bb5ff32d4ba0,
          ba92f5b4-2d11-453d-a403-e96b0029c9fe,
          0a9a7e1f-b9d0-4cc4-a60d-0319b160aaa3,
          4633458b-17de-408a-b874-0445c86b69e6,
          7f951dda-4ed3-4680-a7ca-43fe172d538d
        }
      )
    )
  COND
}

# Let the pipeline write Terraform state via Entra ID (shared keys are disabled).
resource "azurerm_role_assignment" "state_blob" {
  scope                = azurerm_storage_account.state.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azuread_service_principal.pipeline.object_id
}
