# infra/app

A small, separate root for the MCP **Container App** so image deploys don't
re-plan the whole platform (no `-target`). It reads platform outputs via
`terraform_remote_state` and takes `image_tag` (the commit SHA).

```bash
terraform init -backend-config=../envs/dev/backend.hcl   # use key dev/app.tfstate
terraform apply \
  -var-file=../envs/dev/dev.tfvars \
  -var image_tag=$GITHUB_SHA \
  -var state_resource_group=$TF_STATE_RESOURCE_GROUP \
  -var state_storage_account=$TF_STATE_STORAGE_ACCOUNT \
  -var state_container=$TF_STATE_CONTAINER \
  -var platform_state_key=dev/platform.tfstate
```
> Use a distinct state `key` for this root (e.g. `dev/app.tfstate`) so it never
> collides with the platform state.
