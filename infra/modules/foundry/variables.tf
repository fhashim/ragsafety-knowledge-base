variable "name" { type = string }
variable "project_name" { type = string }
variable "resource_group_id" { type = string }
variable "location" { type = string }
variable "sku_name" {
  type    = string
  default = "S0"
}

variable "deployments" {
  description = "Map of model deployments (small chat, large chat, embeddings)."
  type = map(object({
    name          = string
    model_format  = string
    model_name    = string
    model_version = string
    sku_name      = string
    capacity      = number
  }))
}

variable "tags" {
  type    = map(string)
  default = {}
}
