output "mcp_fqdn" {
  value = azurerm_container_app.mcp.ingress[0].fqdn
}

output "mcp_url" {
  value = "https://${azurerm_container_app.mcp.ingress[0].fqdn}"
}
