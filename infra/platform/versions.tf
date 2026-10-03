terraform {
  required_version = ">= 1.9"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.40"
    }
    azapi = {
      source  = "Azure/azapi"
      version = "~> 2.5"
    }
  }

  # Remote state in Azure Storage, OIDC + Entra auth, blob-lease locking.
  # Configured per environment via `-backend-config=../envs/<env>/backend.hcl`.
  backend "azurerm" {
    use_oidc         = true
    use_azuread_auth = true
  }
}
