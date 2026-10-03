output "connection_id" {
  value = var.enabled ? azapi_resource.connection[0].id : ""
}
