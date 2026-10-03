# Storage for raw docs, the audit-raw blob container and the ragaudit table.
# Shared-key auth disabled: callers use Entra ID + Storage Blob/Table Data roles.

resource "azurerm_storage_account" "this" {
  name                            = var.name
  resource_group_name             = var.resource_group_name
  location                        = var.location
  account_tier                    = "Standard"
  account_replication_type        = "LRS"
  min_tls_version                 = "TLS1_2"
  shared_access_key_enabled       = false
  allow_nested_items_to_be_public = false
  tags                            = var.tags

  blob_properties {
    versioning_enabled = true
    delete_retention_policy {
      days = 7
    }
  }
}

resource "azurerm_storage_container" "raw_docs" {
  name                  = "raw-docs"
  storage_account_id    = azurerm_storage_account.this.id
  container_access_type = "private"
}

resource "azurerm_storage_container" "audit_raw" {
  name                  = "audit-raw"
  storage_account_id    = azurerm_storage_account.this.id
  container_access_type = "private"
}

# The ragaudit table is created via ARM (azapi), NOT the azurerm data-plane
# resource: shared keys are disabled on this account, so the data-plane Tables
# client cannot authenticate (403 KeyBasedAuthenticationNotPermitted). The ARM
# control-plane path is covered by the deployer's Contributor role. Runtime data
# access uses the managed identity's Storage Table Data Contributor role.
# (Blob containers above use the azurerm resources, which already go via ARM.)
resource "azapi_resource" "ragaudit" {
  type                      = "Microsoft.Storage/storageAccounts/tableServices/tables@2023-05-01"
  name                      = "ragaudit"
  parent_id                 = "${azurerm_storage_account.this.id}/tableServices/default"
  schema_validation_enabled = false
  body                      = {}
}
