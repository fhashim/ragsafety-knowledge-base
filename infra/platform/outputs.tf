output "resource_group_name" { value = azurerm_resource_group.this.name }
output "location" { value = var.location }

output "foundry_endpoint" { value = module.foundry.endpoint }
output "foundry_id" { value = module.foundry.id }
output "foundry_project_id" { value = module.foundry.project_id }
output "deployment_names" { value = module.foundry.deployment_names }

output "search_endpoint" { value = module.search.endpoint }
output "search_name" { value = module.search.name }

output "docintel_endpoint" { value = module.document_intelligence.endpoint }
output "content_safety_endpoint" { value = module.content_safety.endpoint }

output "storage_account_name" { value = module.storage.name }

output "acr_login_server" { value = module.acr.login_server }
output "container_app_environment_id" { value = module.container_apps_env.id }

output "runtime_identity_id" { value = module.identity_rbac.identity_id }
output "runtime_identity_client_id" { value = module.identity_rbac.client_id }

output "app_insights_connection_string" {
  value     = module.monitoring.app_insights_connection_string
  sensitive = true
}

output "foundry_project_endpoint" { value = module.foundry.project_endpoint }
