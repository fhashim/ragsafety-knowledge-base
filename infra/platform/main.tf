locals {
  base = "${var.project}-${var.env}"
  # Global-unique names: lowercase alphanumeric, length-bounded.
  alnum   = lower("${var.project}${var.env}${var.unique}")
  st_name = substr(replace("st${local.alnum}", "/[^a-z0-9]/", ""), 0, 24)
  acr_nm  = substr(replace("acr${local.alnum}", "/[^a-z0-9]/", ""), 0, 50)
  kv_name = substr("kv-${local.base}-${var.unique}", 0, 24)

  tags = {
    env         = var.env
    owner       = var.owner
    cost-center = var.cost_center
    managed-by  = "terraform"
    application = var.project
  }
}

resource "azurerm_resource_group" "this" {
  name     = "rg-${local.base}"
  location = var.location
  tags     = local.tags
}

module "monitoring" {
  source              = "../modules/monitoring"
  name                = local.base
  resource_group_name = azurerm_resource_group.this.name
  location            = var.location
  tags                = local.tags
}

module "keyvault" {
  source              = "../modules/keyvault"
  name                = local.kv_name
  resource_group_name = azurerm_resource_group.this.name
  location            = var.location
  tags                = local.tags
}

module "storage" {
  source              = "../modules/storage"
  name                = local.st_name
  resource_group_name = azurerm_resource_group.this.name
  location            = var.location
  tags                = local.tags
}

module "acr" {
  source              = "../modules/acr"
  name                = local.acr_nm
  resource_group_name = azurerm_resource_group.this.name
  location            = var.location
  tags                = local.tags
}

module "search" {
  source              = "../modules/search"
  name                = "srch-${local.base}"
  resource_group_name = azurerm_resource_group.this.name
  location            = var.location
  tags                = local.tags
}

module "document_intelligence" {
  source              = "../modules/document_intelligence"
  name                = "di-${local.base}"
  resource_group_name = azurerm_resource_group.this.name
  location            = var.location
  tags                = local.tags
}

module "content_safety" {
  source              = "../modules/content_safety"
  name                = "cs-${local.base}"
  resource_group_name = azurerm_resource_group.this.name
  location            = var.location
  tags                = local.tags
}

module "foundry" {
  source            = "../modules/foundry"
  name              = "aif-${local.base}"
  project_name      = "proj-${local.base}"
  resource_group_id = azurerm_resource_group.this.id
  location          = var.location
  deployments       = var.deployments
  tags              = local.tags
}

module "bing_grounding" {
  source             = "../modules/bing_grounding"
  enabled            = var.enable_bing_grounding
  name               = "bing-${local.base}"
  resource_group_id  = azurerm_resource_group.this.id
  foundry_account_id = module.foundry.id
  allowed_domains    = var.bing_allowed_domains
  tags               = local.tags
}

module "container_apps_env" {
  source                     = "../modules/container_apps_env"
  name                       = "cae-${local.base}"
  resource_group_name        = azurerm_resource_group.this.name
  location                   = var.location
  log_analytics_workspace_id = module.monitoring.log_analytics_workspace_id
  tags                       = local.tags
}

module "identity_rbac" {
  source                   = "../modules/identity_rbac"
  name                     = "id-${local.base}"
  resource_group_name      = azurerm_resource_group.this.name
  location                 = var.location
  foundry_id               = module.foundry.id
  foundry_project_id       = module.foundry.project_id
  search_id                = module.search.id
  storage_id               = module.storage.id
  keyvault_id              = module.keyvault.id
  acr_id                   = module.acr.id
  document_intelligence_id = module.document_intelligence.id
  deployer_principal_id    = var.deployer_principal_id
  tags                     = local.tags
}
