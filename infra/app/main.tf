# Reads platform outputs (endpoints, identity, ACR, CAE) so app deploys never
# re-plan the platform. No -target needed: this is a separate root + state.
data "terraform_remote_state" "platform" {
  backend = "azurerm"
  config = {
    use_oidc             = true
    use_azuread_auth     = true
    resource_group_name  = var.state_resource_group
    storage_account_name = var.state_storage_account
    container_name       = var.state_container
    key                  = var.platform_state_key
  }
}

locals {
  p     = data.terraform_remote_state.platform.outputs
  image = "${local.p.acr_login_server}/${var.image_repository}:${var.image_tag}"
}

resource "azurerm_container_app" "mcp" {
  name                         = "ca-ragsafety-mcp-${var.env}"
  resource_group_name          = local.p.resource_group_name
  container_app_environment_id = local.p.container_app_environment_id
  revision_mode                = "Single"

  identity {
    type         = "UserAssigned"
    identity_ids = [local.p.runtime_identity_id]
  }

  # Pull from ACR using the runtime managed identity (AcrPull granted in platform).
  registry {
    server   = local.p.acr_login_server
    identity = local.p.runtime_identity_id
  }

  ingress {
    external_enabled = true
    target_port      = 8000
    transport        = "http"
    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  template {
    min_replicas = var.min_replicas
    max_replicas = var.max_replicas

    container {
      name   = "mcp"
      image  = local.image
      cpu    = 0.5
      memory = "1Gi"

      env {
        name  = "RAGSAFETY_MOCK_MODE"
        value = "false"
      }
      env {
        name  = "RAGSAFETY_FOUNDRY_ENDPOINT"
        value = local.p.foundry_endpoint
      }
      env {
        name  = "RAGSAFETY_SEARCH_ENDPOINT"
        value = local.p.search_endpoint
      }
      env {
        name  = "RAGSAFETY_DOCINTEL_ENDPOINT"
        value = local.p.docintel_endpoint
      }
      env {
        name  = "RAGSAFETY_CONTENT_SAFETY_ENDPOINT"
        value = local.p.content_safety_endpoint
      }
      env {
        name  = "RAGSAFETY_STORAGE_ACCOUNT"
        value = local.p.storage_account_name
      }
      env {
        name  = "RAGSAFETY_MANAGED_IDENTITY_CLIENT_ID"
        value = local.p.runtime_identity_client_id
      }
      env {
        name  = "RAGSAFETY_CHAT_SMALL_DEPLOYMENT"
        value = lookup(local.p.deployment_names, "small", "gpt-4o-mini")
      }
      env {
        name  = "RAGSAFETY_CHAT_LARGE_DEPLOYMENT"
        value = lookup(local.p.deployment_names, "large", "gpt-4o")
      }
      env {
        name  = "RAGSAFETY_EMBEDDING_DEPLOYMENT"
        value = lookup(local.p.deployment_names, "embed", "text-embedding-3-large")
      }
      env {
        name        = "APPLICATIONINSIGHTS_CONNECTION_STRING"
        secret_name = "appinsights-connection-string"
      }
    }
  }

  secret {
    name  = "appinsights-connection-string"
    value = local.p.app_insights_connection_string
  }

  tags = {
    env        = var.env
    managed-by = "terraform"
    component  = "mcp-server"
  }
}
