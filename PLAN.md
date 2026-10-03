# PLAN.md — RAG Safety-Checklist Prototype on Microsoft Foundry

> **Status:** living plan. Checked boxes track what is built. This is a teaching
> artifact: every decision below is written to be explained, not just executed.

## 0. What this is

A plug-and-play GitHub repo for a Retrieval-Augmented Generation (RAG) prototype
used by an energy company's field technicians. A technician describes a
maintenance task and receives a **grounded, cited, pre-task safety checklist**
(PPE, clearance distances, permits, isolation steps, stop-work conditions).

It is equal parts **RAG engineering** demo (chunking, hybrid retrieval,
reranking, OCR, tables) and **platform engineering** demo (Terraform IaC via
CI/CD, tracing, cost, eval gates, guardrails, audit, per-user access, MCP).

The whole system runs locally with `MOCK_MODE=true` — deterministic fake
embeddings, a stub LLM, an in-memory hybrid index, and local-file audit — so
tests, ingestion, ablations, and all seven demos run with **no Azure
credentials**. The same code paths call real Azure when `MOCK_MODE=false`.

## 1. Key verified facts (checked 2026-10-03)

Azure/Foundry and the Terraform providers changed a lot; these were verified
against Microsoft Learn, the Terraform Registry, and PyPI. Anything I could not
fully verify is marked `# VERIFY:` in code and collected in the final report.

| Thing | Decision | Source |
|---|---|---|
| Foundry shape | **New Foundry resource** = `Microsoft.CognitiveServices/accounts` kind `AIServices` with `project_management_enabled`, plus a `projects` child. NOT the old hub/ML-workspace model. | MS Learn *Use Terraform to create Microsoft Foundry* (2026-09-21) |
| Foundry in azurerm | `azurerm_cognitive_account` (kind `AIServices`) + `azurerm_cognitive_account_project` + `azurerm_cognitive_deployment` are GA. **We prefer azurerm** per the ownership rule. | MS Learn (AzureRM tab) |
| azurerm version | pin `~> 4.40` (5.x exists; 4.x is the long-tested line for these resources). `# VERIFY:` bump to 5.x once validated. | Registry |
| azapi | `~> 2.5`; used only where azurerm cannot express a property (Bing grounding connection, some preview props). Every use commented. | MS Learn AzAPI tab |
| azuread | `~> 3.0`; bootstrap stack only (Entra groups, app registration, federated creds). | Registry |
| Foundry RBAC role | **Azure AI Developer** recently renamed to **Foundry** role family; role IDs unchanged. We keep the GUID + note. | MS Learn RBAC note |
| Model deployment | `azurerm_cognitive_deployment` with `model { format="OpenAI" }`; SKU `GlobalStandard`. | MS Learn |

Python package versions (latest on PyPI 2026-10-03; pinned in `requirements*.txt`):
`mcp 2.3.0`, `azure-ai-projects 2.7.0`, `azure-ai-evaluation 1.18.7`,
`azure-search-documents 12.0.0`, `azure-ai-documentintelligence 1.0.2`,
`azure-ai-contentsafety 1.0.0`, `azure-identity 1.26.0`,
`azure-data-tables 12.7.0`, `azure-storage-blob 12.31.0`,
`azure-monitor-opentelemetry 1.8.10`, `openai 3.24.0`,
`pydantic-settings 2.15.0`, `reportlab 5.0.1`.
All Azure SDK imports are **lazy / guarded** so mock mode never needs them.

## 2. Architecture

```
Technician ─▶ App (query flow)
                 1 guardrail_in   (Content Safety: Prompt Shields, harm, off-topic)
                 2 rewrite        (small chat model: typos, acronyms, slot extraction)
                 3 clarify        (ask if equipment/voltage/task missing)
                 4 retrieve       (AI Search hybrid: vector + BM25 + RRF, security filter)
                 5 rerank         (semantic ranker)
                 6 generate       (strong chat model → strict JSON checklist)
                 7 guardrail_out  (groundedness, citations, PII redaction)
                 8 audit          (Table Storage + blob, OTel spans, cost)
```

- **Foundry project** hosts 3 deployments: small chat (rewrite/intent/clarify),
  strong chat (final checklist), embeddings.
- **Document Intelligence** (layout) parses PDFs → Markdown (headings + tables),
  OCRs the poster PNG.
- **AI Search** stores vector + BM25 fields, hybrid+RRF, semantic ranker,
  `allowed_groups` security-trimming filter.
- **Grounding with Bing** (feature-flagged) via the Foundry agent, allow-listed
  to regulator domains; web content labeled separately; internal policy wins.
- **Content Safety** guards input and output.
- **OpenTelemetry (GenAI conventions)** → App Insights (console exporter in mock).
- **Cost** from `config/pricing.yaml`, aggregated by `scripts/cost_report.py`.
- **Audit** to Table `ragaudit` (PK=date, RK=trace_id) + blob `audit-raw`.
- **MCP server** (FastMCP) in Azure Container Apps, registered as a Foundry agent
  tool; forwards and enforces user identity + group claims.

## 3. Terraform / Python ownership split

Terraform owns **all** control-plane, identities, RBAC. Python owns only
data-plane Terraform can't reliably manage:

| Concern | Owner | Why |
|---|---|---|
| RG, Foundry, deployments, Search, DocIntel, Content Safety, Storage, ACR, ACA env, Key Vault, Log Analytics/App Insights, UAMI, **all RBAC** | Terraform | control-plane |
| Bing grounding connection | Terraform (azapi, flagged) | control-plane, not in azurerm |
| AI Search **index schema** | Python (idempotent `create_or_update`) | schema is code; churns with chunking strategy; no stable TF path |
| Document ingestion (parse/chunk/embed/index) | Python | data-plane |
| Foundry **agent + MCP tool registration** | Python | data-plane SDK |
| Evaluation | Python | data-plane |
| MCP **Container App** (`infra/app`) | Terraform | control-plane, separate root for fast image deploys |

## 4. Repo layout

```
PLAN.md  README.md  Makefile  .env.example  .gitignore  pyproject.toml
requirements.txt  requirements-dev.txt
config/            settings via pydantic-settings; pricing.yaml; eval_thresholds.yaml;
                   personas.yaml; bing_allowlist.yaml
src/ragsafety/     core app package (settings, flow, stages, clients w/ mock+azure)
  clients/         llm, embeddings, search, docintel, contentsafety, audit, tracing (mock+real)
  pipeline/        parse, chunk, enrich, embed_index, retrieve, rerank, generate
  flow.py          orchestrates the 8 stages + spans
  guardrails.py    input/output checks
  schema.py        pydantic models (Checklist, Chunk, AuditRecord, …)
  security.py      allowed_groups resolution + search filter
  mcp_server/      MCP server (MCPServer) + Dockerfile
scripts/           generate_data.py, build_index.py, ingest.py, register_agent.py,
                   cost_report.py
data/              generated PDFs/PNG (committed), parsed/ chunks/ artifacts
eval/              golden_set.jsonl, run_eval.py, ablation.py
demos/             7 demo scripts
tests/             pytest (mock mode)
infra/bootstrap/   run-once admin stack (state SA, app reg, OIDC, groups, RBAC)
infra/modules/     identity_rbac, monitoring, keyvault, storage, foundry, search,
                   document_intelligence, content_safety, bing_grounding, acr,
                   container_apps_env
infra/platform/    shared platform root (remote state per env)
infra/app/         MCP Container App root (image_tag var; reads platform remote state)
infra/envs/dev|prod/  *.tfvars + backend.hcl
.github/workflows/ ci, infra, drift, ingest, eval-gate, deploy, destroy
results/           ablation.md (generated)
```

## 5. Build phases (verify each before moving on)

- [x] **P0 Scaffolding** — repo skeleton, pyproject, settings, Makefile, .env.example, logging, tracing (console), schema models. Test: `make test` collects.
- [x] **P1 Mock clients** — deterministic embeddings, stub LLM, in-memory hybrid index (BM25 + cosine + RRF + mock rerank), local audit. Unit tests.
- [x] **P2 Synthetic data** — `generate_data.py` builds 4 PDFs + 1 PNG with the planted traps; commit outputs.
- [x] **P3 Ingestion** — parse (mock DocIntel → markdown/tables/OCR), 3 chunkers, enrich metadata, embed+index. Tests prove trap behaviour.
- [x] **P4 Query flow** — guardrails, rewrite, clarify, retrieve+filter, rerank, generate JSON checklist, output guardrail, audit. Security-trim tests.
- [x] **P5 Eval + ablation** — golden set (~40), `run_eval.py` (thresholds), `ablation.py` → `results/ablation.md`.
- [x] **P6 MCP server** — FastMCP tools + Dockerfile; identity/group forwarding; smoke test.
- [x] **P7 Terraform** — bootstrap, modules, platform, app, envs; `fmt`/`validate`/`tflint`(/checkov). All green.
- [x] **P8 CI/CD** — 7 workflows; actionlint-clean.
- [x] **P9 Demos + README** — 7 demos; extensive README; final report.

## 6. Assumptions

1. **No Azure access from here.** Real Azure paths are written and documented but
   exercised only via mock. Marked `# VERIFY:` where they couldn't be run.
2. **Two personas** Priya (`grp-electrical`) / Marcus (`grp-gas`); shared HSE
   visible to both. Enforced at retrieval via `allowed_groups` filter, never
   prompt-only. Mock mode simulates groups via `config/personas.yaml`.
3. **Safety hard rule:** never invent a distance/voltage/threshold. If unsupported
   by a source → emit a stop-work instruction to contact a supervisor.
4. **Pricing/quotas** in `config/pricing.yaml` are placeholders to re-verify.
5. One index per chunking strategy (plus a `strategy` field) for clean ablation.
6. Python 3.11+ (built/tested on 3.12). Terraform ≥1.9 (tested 1.16).

## 7. Definition of done (from the brief)

`make setup && make demo` + `make test` + `make tf-check` (fmt/validate/tflint on
bootstrap, platform, app) all pass; 7 demos print labeled output;
`results/ablation.md` shows measurable differences; workflows valid (actionlint);
every root module has a README snippet + example tfvars; final report lists
`# VERIFY:` items and remaining manual steps.
