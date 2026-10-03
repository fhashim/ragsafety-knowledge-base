# infra/platform

The shared platform. One remote state per environment
(`-backend-config=../envs/<env>/backend.hcl`, key `…/platform.tfstate`).

Composes the modules: `monitoring`, `keyvault`, `storage`, `acr`, `search`,
`document_intelligence`, `content_safety`, `foundry`, `bing_grounding`
(flagged), `container_apps_env`, and `identity_rbac` (the runtime UAMI + all
RBAC). All control-plane, identities and RBAC live here.

## Plan / apply (local)
```bash
terraform init -backend-config=../envs/dev/backend.hcl
terraform plan  -var-file=../envs/dev/dev.tfvars -out tfplan
terraform apply tfplan
```
In CI the same runs under OIDC (`ARM_USE_OIDC=true`). Outputs (endpoints,
deployment names, identity client id — all non-secret; the App Insights
connection string is `sensitive`) feed the ingest and app-deploy jobs.
