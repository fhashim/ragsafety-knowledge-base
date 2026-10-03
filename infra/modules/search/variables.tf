variable "name" { type = string }
variable "resource_group_name" { type = string }
variable "location" { type = string }
variable "sku" {
  type    = string
  default = "standard"
}
variable "semantic_search_sku" {
  type    = string
  default = "standard"
}
variable "tags" {
  type    = map(string)
  default = {}
}
