# Microsoft Foundry resource + project + model deployments.
#
# azapi is used here deliberately: the NEW Foundry resource is a
# Microsoft.CognitiveServices/accounts (kind "AIServices") with
# allowProjectManagement=true and a child ".../projects" resource. Using azapi
# with the pinned 2025-06-01 API (per Microsoft Learn, "Use Terraform to create
# Microsoft Foundry", verified 2026-09) avoids depending on azurerm provider
# versions that may not yet expose azurerm_cognitive_account_project.
#
# Everything else in this repo prefers azurerm per the ownership rule.

resource "azapi_resource" "account" {
  type                      = "Microsoft.CognitiveServices/accounts@2025-06-01"
  name                      = var.name
  parent_id                 = var.resource_group_id
  location                  = var.location
  schema_validation_enabled = false
  tags                      = var.tags

  identity {
    type = "SystemAssigned"
  }

  body = {
    kind = "AIServices"
    sku  = { name = var.sku_name }
    properties = {
      # Entra ID only (no API keys) for the data plane.
      disableLocalAuth = true
      # Marks this Cognitive Services account as a Foundry resource.
      allowProjectManagement = true
      customSubDomainName    = var.name
    }
  }

  response_export_values = ["properties.endpoint", "identity.principalId"]
}

resource "azapi_resource" "project" {
  type                      = "Microsoft.CognitiveServices/accounts/projects@2025-06-01"
  name                      = var.project_name
  parent_id                 = azapi_resource.account.id
  location                  = var.location
  schema_validation_enabled = false

  identity {
    type = "SystemAssigned"
  }

  body = {
    properties = {
      displayName = var.project_name
      description = "RAG safety-checklist project"
    }
  }

  response_export_values = ["identity.principalId", "properties.endpoints"]
}

# Model deployments (small chat, large chat, embeddings). API 2023-05-01 is the
# stable deployments API used by the Microsoft Learn sample.
#
# Cognitive Services serializes control-plane operations on an account: creating
# deployments in parallel returns 409 "Another operation is in progress on the
# resource". We therefore chain them (project -> small -> large -> embed) with
# depends_on so they are created one at a time.
locals {
  dep = var.deployments
}

resource "azapi_resource" "deployment_small" {
  type                      = "Microsoft.CognitiveServices/accounts/deployments@2023-05-01"
  name                      = local.dep["small"].name
  parent_id                 = azapi_resource.account.id
  schema_validation_enabled = false
  depends_on                = [azapi_resource.project]

  body = {
    sku = { name = local.dep["small"].sku_name, capacity = local.dep["small"].capacity }
    properties = {
      model = {
        format  = local.dep["small"].model_format
        name    = local.dep["small"].model_name
        version = local.dep["small"].model_version
      }
    }
  }
}

resource "azapi_resource" "deployment_large" {
  type                      = "Microsoft.CognitiveServices/accounts/deployments@2023-05-01"
  name                      = local.dep["large"].name
  parent_id                 = azapi_resource.account.id
  schema_validation_enabled = false
  depends_on                = [azapi_resource.deployment_small]

  body = {
    sku = { name = local.dep["large"].sku_name, capacity = local.dep["large"].capacity }
    properties = {
      model = {
        format  = local.dep["large"].model_format
        name    = local.dep["large"].model_name
        version = local.dep["large"].model_version
      }
    }
  }
}

resource "azapi_resource" "deployment_embed" {
  type                      = "Microsoft.CognitiveServices/accounts/deployments@2023-05-01"
  name                      = local.dep["embed"].name
  parent_id                 = azapi_resource.account.id
  schema_validation_enabled = false
  depends_on                = [azapi_resource.deployment_large]

  body = {
    sku = { name = local.dep["embed"].sku_name, capacity = local.dep["embed"].capacity }
    properties = {
      model = {
        format  = local.dep["embed"].model_format
        name    = local.dep["embed"].model_name
        version = local.dep["embed"].model_version
      }
    }
  }
}
