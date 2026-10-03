variable "subscription_id" { type = string }

variable "project" {
  type    = string
  default = "ragsafety"
}

variable "location" {
  type    = string
  default = "eastus"
}

variable "github_org" {
  type        = string
  description = "GitHub organization or user that owns the repo."
}

variable "github_repo" {
  type        = string
  description = "GitHub repository name."
}

variable "environments" {
  type    = list(string)
  default = ["dev", "prod"]
}

variable "state_container_name" {
  type    = string
  default = "tfstate"
}

variable "tags" {
  type = map(string)
  default = {
    managed-by = "terraform"
    component  = "bootstrap"
  }
}
