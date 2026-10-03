output "pipeline_client_id" {
  description = "AZURE_CLIENT_ID GitHub secret."
  value       = azuread_application.pipeline.client_id
}

output "tenant_id" {
  description = "AZURE_TENANT_ID GitHub secret."
  value       = data.azuread_client_config.current.tenant_id
}

output "subscription_id" {
  description = "AZURE_SUBSCRIPTION_ID GitHub secret."
  value       = var.subscription_id
}

output "state_resource_group" {
  description = "TF_STATE_RESOURCE_GROUP GitHub variable."
  value       = azurerm_resource_group.state.name
}

output "state_storage_account" {
  description = "TF_STATE_STORAGE_ACCOUNT GitHub variable."
  value       = azurerm_storage_account.state.name
}

output "state_container" {
  description = "TF_STATE_CONTAINER GitHub variable."
  value       = azurerm_storage_container.state.name
}

output "group_ids" {
  description = "Entra group object ids for grp-electrical and grp-gas."
  value = {
    electrical = azuread_group.electrical.object_id
    gas        = azuread_group.gas.object_id
  }
}
