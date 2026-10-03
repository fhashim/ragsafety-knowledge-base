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

variable "github_subject_prefix" {
  type        = string
  default     = ""
  description = <<-DESC
    Override for the OIDC subject prefix. Leave empty to use the standard
    "repo:<org>/<repo>". Set it when the repo has "use_immutable_subject" enabled
    (GitHub injects numeric ids), e.g.
    "repo:fhashim@46088636/ragsafety-knowledge-base@1402801162".
    Read the exact value from:
      gh api repos/<org>/<repo>/actions/oidc/customization/sub  (sub_claim_prefix)
  DESC
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
