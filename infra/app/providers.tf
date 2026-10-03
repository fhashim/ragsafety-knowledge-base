provider "azurerm" {
  features {}
  use_oidc            = true
  storage_use_azuread = true
  subscription_id     = var.subscription_id
}
