# Grounding with Bing Search, behind a feature flag (count = enabled ? 1 : 0).
#
# azapi is required: there is no azurerm resource for the Grounding-with-Bing
# account or for the Foundry connection that exposes it to the agent.
#
# VERIFY: the Grounding with Bing resource type/API and the connection shape
# change frequently. Confirm against Microsoft Learn before enabling. The
# domain allow-list is enforced on the connection so the agent can only cite the
# configured regulator domains.

resource "azapi_resource" "bing" {
  count                     = var.enabled ? 1 : 0
  type                      = "Microsoft.Bing/accounts@2020-06-10" # VERIFY: current API/type
  name                      = var.name
  parent_id                 = var.resource_group_id
  location                  = "global"
  schema_validation_enabled = false
  tags                      = var.tags

  body = {
    kind = "Bing.Grounding" # VERIFY: current kind for Grounding with Bing Search
    sku  = { name = "G1" }  # VERIFY: current SKU
  }
}

# Connection on the Foundry account that makes the Bing grounding tool available
# to the agent, restricted to the allow-listed regulator domains.
resource "azapi_resource" "connection" {
  count                     = var.enabled ? 1 : 0
  type                      = "Microsoft.CognitiveServices/accounts/connections@2025-06-01"
  name                      = "bing-grounding"
  parent_id                 = var.foundry_account_id
  schema_validation_enabled = false

  body = {
    properties = {
      category      = "GroundingWithBingSearch" # VERIFY: current category
      authType      = "ApiKey"                  # VERIFY: prefer managed identity if supported
      target        = try(azapi_resource.bing[0].output.properties.endpoint, "https://api.bing.microsoft.com/")
      isSharedToAll = false
      metadata = {
        allowedDomains = join(",", var.allowed_domains)
      }
    }
  }
}
