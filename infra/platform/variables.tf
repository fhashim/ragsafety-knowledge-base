variable "subscription_id" {
  type        = string
  description = "Target subscription id."
}

variable "project" {
  type    = string
  default = "ragsafety"
}

variable "env" {
  type        = string
  description = "Environment name (dev|prod)."
}

variable "location" {
  type    = string
  default = "eastus"
}

variable "unique" {
  type        = string
  description = "Short suffix to make global names unique (e.g. 01, or initials)."
  default     = "01"
}

variable "owner" {
  type    = string
  default = "platform-team"
}

variable "cost_center" {
  type    = string
  default = "field-safety"
}

variable "enable_bing_grounding" {
  type    = bool
  default = false
}

variable "bing_allowed_domains" {
  type    = list(string)
  default = ["osha.gov", "hse.gov.uk", "nfpa.org"]
}

variable "deployments" {
  description = "Foundry model deployments: small chat, large chat, embeddings."
  type = map(object({
    name          = string
    model_format  = string
    model_name    = string
    model_version = string
    sku_name      = string
    capacity      = number
  }))
  default = {
    # VERIFY: model versions and regional availability/quota before apply.
    small = { name = "gpt-4o-mini", model_format = "OpenAI", model_name = "gpt-4o-mini", model_version = "2024-07-18", sku_name = "GlobalStandard", capacity = 20 }
    large = { name = "gpt-4o", model_format = "OpenAI", model_name = "gpt-4o", model_version = "2024-11-20", sku_name = "GlobalStandard", capacity = 20 }
    embed = { name = "text-embedding-3-large", model_format = "OpenAI", model_name = "text-embedding-3-large", model_version = "1", sku_name = "Standard", capacity = 50 }
  }
}
