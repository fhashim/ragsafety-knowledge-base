variable "enabled" {
  type    = bool
  default = false
}
variable "name" { type = string }
variable "resource_group_id" { type = string }
variable "foundry_account_id" { type = string }
variable "allowed_domains" {
  type    = list(string)
  default = []
}
variable "tags" {
  type    = map(string)
  default = {}
}
