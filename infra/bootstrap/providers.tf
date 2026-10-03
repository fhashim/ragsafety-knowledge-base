provider "azurerm" {
  features {}
  subscription_id = var.subscription_id
  # The state storage account disables shared keys, so the provider must use
  # Entra ID (not account keys) for its storage data-plane reads (queue/table/
  # static-website properties). Without this it hits KeyBasedAuthenticationNotPermitted.
  storage_use_azuread = true
}

provider "azuread" {}
