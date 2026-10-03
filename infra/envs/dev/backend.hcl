# Remote state backend for dev. Values come from the bootstrap outputs /
# GitHub variables (TF_STATE_*). Use a distinct `key` per root module.
resource_group_name  = "rg-ragsafety-tfstate"
storage_account_name = "stragsafetytfstatec3gfc"
container_name       = "tfstate"
key                  = "dev/platform.tfstate"
