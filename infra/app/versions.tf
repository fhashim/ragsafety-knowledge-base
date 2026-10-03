terraform {
  required_version = ">= 1.9"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.40"
    }
  }

  # Separate state key per environment (see ../envs/<env>/backend.hcl, which the
  # app job overrides with an app-specific key, e.g. app.tfstate).
  backend "azurerm" {
    use_oidc         = true
    use_azuread_auth = true
  }
}
