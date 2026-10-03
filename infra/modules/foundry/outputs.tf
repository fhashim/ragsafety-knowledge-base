output "id" { value = azapi_resource.account.id }
output "project_id" { value = azapi_resource.project.id }

output "endpoint" {
  value = try(azapi_resource.account.output.properties.endpoint, "")
}

output "principal_id" {
  value = try(azapi_resource.account.output.identity.principalId, "")
}

output "deployment_names" {
  value = { for k, d in var.deployments : k => d.name }
}
