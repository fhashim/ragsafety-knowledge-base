variable "name" { type = string }
variable "resource_group_name" { type = string }
variable "location" { type = string }
variable "foundry_id" { type = string }
variable "foundry_project_id" { type = string }
variable "search_id" { type = string }
variable "storage_id" { type = string }
variable "keyvault_id" { type = string }
variable "acr_id" { type = string }
variable "tags" {
  type    = map(string)
  default = {}
}
