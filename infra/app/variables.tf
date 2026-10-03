variable "subscription_id" { type = string }
variable "env" { type = string }

variable "image_tag" {
  type        = string
  description = "Container image tag (commit SHA) to deploy."
}

variable "image_repository" {
  type    = string
  default = "ragsafety-mcp"
}

# Remote state of the platform stack (read-only).
variable "state_resource_group" { type = string }
variable "state_storage_account" { type = string }
variable "state_container" { type = string }
variable "platform_state_key" {
  type    = string
  default = "platform.tfstate"
}

variable "min_replicas" {
  type    = number
  default = 1
}
variable "max_replicas" {
  type    = number
  default = 3
}
