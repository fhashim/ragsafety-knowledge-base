# infra/bootstrap

Run **once, locally, by an admin** with LOCAL state. Creates the foundations the
pipeline needs:

- Terraform remote-state storage account + container (versioning + 30-day soft
  delete, shared keys disabled);
- the pipeline app registration + service principal;
- GitHub OIDC federated credentials for `dev`, `prod` and pull requests;
- Entra groups `grp-electrical` and `grp-gas`;
- the deployer's role assignments (Contributor + RBAC Administrator constrained
  by an ABAC condition to this solution's roles; Storage Blob Data Contributor
  on the state container).

## Admin permissions required
Application Administrator (or Cloud Application Administrator), Groups
Administrator, and Owner or User Access Administrator on the subscription.

## Run
```bash
terraform init
terraform apply -var-file=terraform.tfvars   # from terraform.tfvars.example
```

## Push outputs to GitHub
```bash
gh secret   set AZURE_CLIENT_ID        -b "$(terraform output -raw pipeline_client_id)"
gh secret   set AZURE_TENANT_ID        -b "$(terraform output -raw tenant_id)"
gh secret   set AZURE_SUBSCRIPTION_ID  -b "$(terraform output -raw subscription_id)"
gh variable set TF_STATE_RESOURCE_GROUP  -b "$(terraform output -raw state_resource_group)"
gh variable set TF_STATE_STORAGE_ACCOUNT -b "$(terraform output -raw state_storage_account)"
gh variable set TF_STATE_CONTAINER       -b "$(terraform output -raw state_container)"
```

## Migrate state to remote (after apply)
Add a backend block (or `backend.hcl`) pointing at the new storage account and
run `terraform init -migrate-state`.

## az CLI fallback (service principal + federated credentials)
```bash
az ad app create --display-name ragsafety-github-pipeline
# then: az ad sp create --id <appId>; az ad app federated-credential create ...
```
See the root README for the full fallback.
