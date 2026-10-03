# Bootstrap run — errors, resolutions & what was created

Record of the one-time `infra/bootstrap` run (`terraform apply -var-file=my.tfvars`).

- **Subscription:** `289360a2-95c5-4597-a90c-d44981bf6268`
- **Tenant:** `a46e80fb-9d0c-4466-a175-f9e343d7dbcf`
- **GitHub repo (OIDC subject):** `fhashim/ragsafety-knowledge-base`
- **Result:** `Apply complete! Resources: 12 added, 0 changed, 1 destroyed.`

> The identifiers below (subscription, tenant, client, object and group IDs) are
> **identifiers, not credentials** — they grant nothing without an authenticated,
> authorized Entra ID principal. Auth is OIDC (no client secret was created).

---

## Errors encountered & resolutions

### 1. `403 KeyBasedAuthenticationNotPermitted` on the state storage account

```
Error: encoding Storage Account (...stragsafetytfstatec3gfc): retrieving queue
properties ...: unexpected status 403 (403 Key based authentication is not
permitted on this storage account.) with KeyBasedAuthenticationNotPermitted
  with azurerm_storage_account.state, on main.tf line 18
```

**Cause.** The account is created with `shared_access_key_enabled = false` (no
shared keys — the hardened default). Right after creating it, the azurerm
provider reads the account's **queue service properties** over the storage
**data plane**, and was doing so with **key-based auth**, which the account now
rejects.

**Resolution.** Tell the provider to use Entra ID for storage data-plane calls by
adding `storage_use_azuread = true` to the `azurerm` provider in
`infra/bootstrap/providers.tf` (the `platform` and `app` providers already had
it; `bootstrap` was missing it):

```hcl
provider "azurerm" {
  features {}
  subscription_id     = var.subscription_id
  storage_use_azuread = true   # use Entra ID, not account keys, for data-plane reads
}
```

### 2. `Inconsistent dependency lock file`

```
Error: Inconsistent dependency lock file
  - provider ... azuread: required by this configuration but no version is selected
  - provider ... azurerm: required by this configuration but no version is selected
  - provider ... random: required by this configuration but no version is selected
```

**Cause.** The provider cache (`.terraform/`) and lock file
(`.terraform.lock.hcl`) were removed, so Terraform had no selected provider
versions to apply with.

**Resolution.** Re-install the providers and rebuild the lock (state is not
touched, so the existing resources and the `random_string` suffix are kept):

```bash
terraform init -upgrade
terraform apply -var-file=my.tfvars
```

### Note on the storage account being "replaced" (1 destroyed)

The first (failed) apply left `azurerm_storage_account.state` **tainted** because
its post-create read errored. On the successful run Terraform therefore
destroyed and recreated it (`-/+`), which is why the summary shows *1 destroyed*.
The account was empty, so this was harmless; the name stayed the same because the
`random_string` suffix (`c3gfc`) was already in state.

---

## What was created

| Resource | Name / detail | ID |
| --- | --- | --- |
| Resource group | `rg-ragsafety-tfstate` | `/subscriptions/289360a2-.../resourceGroups/rg-ragsafety-tfstate` |
| Storage account (state) | `stragsafetytfstatec3gfc` (LRS, versioning + 30-day soft delete, shared keys **off**) | `.../storageAccounts/stragsafetytfstatec3gfc` |
| Blob container | `tfstate` | `.../blobServices/default/containers/tfstate` |
| App registration | `ragsafety-github-pipeline` | app object `a66bdbd0-7cdd-4205-b895-13dc330da52f` |
| — client (app) ID | | `b671616c-638c-46a3-99f3-da7b0dcd874e` |
| Service principal | (of the app) | object `7eadaff7-6ad2-4ede-afc4-9db8d709ead9` |
| Federated credential | `github-dev` → `repo:fhashim/ragsafety-knowledge-base:environment:dev` | — |
| Federated credential | `github-prod` → `repo:fhashim/ragsafety-knowledge-base:environment:prod` | — |
| Federated credential | `github-pull-request` → `repo:fhashim/ragsafety-knowledge-base:pull_request` | — |
| Entra group | `grp-electrical` | `ac287dd9-312b-4026-95d8-13eb289b319e` |
| Entra group | `grp-gas` | `8f6fedbc-c9a8-40b9-a78f-e7b0f90c4f7c` |
| Role assignment | `Contributor` → pipeline SP, scope = subscription | — |
| Role assignment | `Role Based Access Control Administrator` (ABAC-constrained) → pipeline SP, scope = subscription | — |
| Role assignment | `Storage Blob Data Contributor` → pipeline SP, scope = state storage account | — |

### Terraform outputs

| Output | Value |
| --- | --- |
| `pipeline_client_id` | `b671616c-638c-46a3-99f3-da7b0dcd874e` |
| `tenant_id` | `a46e80fb-9d0c-4466-a175-f9e343d7dbcf` |
| `subscription_id` | `289360a2-95c5-4597-a90c-d44981bf6268` |
| `state_resource_group` | `rg-ragsafety-tfstate` |
| `state_storage_account` | `stragsafetytfstatec3gfc` |
| `state_container` | `tfstate` |
| `group_ids.electrical` | `ac287dd9-312b-4026-95d8-13eb289b319e` |
| `group_ids.gas` | `8f6fedbc-c9a8-40b9-a78f-e7b0f90c4f7c` |

---

## Next steps

1. **Push outputs to GitHub** (run in `infra/bootstrap`):

   ```bash
   gh secret   set AZURE_CLIENT_ID        -b "$(terraform output -raw pipeline_client_id)"
   gh secret   set AZURE_TENANT_ID        -b "$(terraform output -raw tenant_id)"
   gh secret   set AZURE_SUBSCRIPTION_ID  -b "$(terraform output -raw subscription_id)"
   gh variable set TF_VERSION               -b "1.9.8"
   gh variable set TF_STATE_RESOURCE_GROUP  -b "$(terraform output -raw state_resource_group)"
   gh variable set TF_STATE_STORAGE_ACCOUNT -b "$(terraform output -raw state_storage_account)"
   gh variable set TF_STATE_CONTAINER       -b "$(terraform output -raw state_container)"
   ```

2. **Create GitHub Environments** `dev` and `prod` (add required reviewers to
   `prod` if you're on GitHub Pro; on a Free private repo, drop the reviewer
   requirement or make the repo public).

3. **Migrate bootstrap state to remote** (optional): add a `backend "azurerm"`
   block pointing at `stragsafetytfstatec3gfc` / `tfstate` (key e.g.
   `bootstrap/terraform.tfstate`) and run `terraform init -migrate-state`.

4. **Deploy the platform** — merge to `main` (triggers `infra.yml`) or run
   `terraform apply` on `infra/platform` locally with
   `-backend-config=../envs/dev/backend.hcl`. Update
   `infra/envs/dev/backend.hcl` so `storage_account_name` is
   `stragsafetytfstatec3gfc`.

5. **Add the two technicians** to the Entra groups (`grp-electrical`,
   `grp-gas`) so retrieval-time access boundaries apply to real users.
