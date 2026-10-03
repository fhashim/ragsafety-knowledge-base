output "id" { value = azurerm_search_service.this.id }
output "name" { value = azurerm_search_service.this.name }
output "endpoint" { value = "https://${azurerm_search_service.this.name}.search.windows.net" }
