# ragsafety — developer entrypoints. Everything below runs in MOCK_MODE (no Azure).
.DEFAULT_GOAL := help
SHELL := /bin/bash

PYTHON ?= python3.12
VENV   := .venv
PY     := $(VENV)/bin/python
PIP    := $(VENV)/bin/pip
export RAGSAFETY_MOCK_MODE ?= true
export PYTHONPATH := src

TF_ROOTS := bootstrap platform app

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------- Python ----
$(VENV)/bin/python:
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --quiet --upgrade pip

.PHONY: setup
setup: $(VENV)/bin/python ## Create venv, install deps, generate synthetic data
	$(PIP) install --quiet -r requirements-dev.txt
	$(PY) scripts/generate_data.py

.PHONY: data
data: ## (Re)generate the synthetic knowledge base (PDFs/PNG + layout sidecars)
	$(PY) scripts/generate_data.py

.PHONY: test
test: ## Run the unit/integration test suite (mock mode)
	$(PY) -m pytest -q

.PHONY: lint
lint: ## Ruff lint
	$(VENV)/bin/ruff check src scripts eval demos tests

.PHONY: fmt
fmt: ## Ruff format + autofix
	$(VENV)/bin/ruff check --fix src scripts eval demos tests
	$(VENV)/bin/ruff format src scripts eval demos tests

.PHONY: ingest
ingest: ## Parse -> chunk -> embed -> index (mock: in-memory)
	$(PY) scripts/ingest.py --strategy section_aware

.PHONY: eval
eval: ## Run the eval gate against the golden set
	$(PY) eval/run_eval.py

.PHONY: ablation
ablation: ## Run the chunking x retrieval ablation -> results/ablation.md
	$(PY) eval/ablation.py

.PHONY: demo
demo: data ## Run all seven demos (mock mode)
	@for d in demos/demo*_*.py; do $(PY) $$d; done

.PHONY: mcp
mcp: ## Run the MCP server locally (streamable-http on :8000)
	$(PY) -m ragsafety.mcp_server.server

.PHONY: cost
cost: ## Aggregate cost per user/day from the audit sink
	$(PY) scripts/cost_report.py

# ------------------------------------------------------------- Terraform ----
.PHONY: tf-fmt
tf-fmt: ## terraform fmt -check across all of infra/
	terraform fmt -check -recursive infra

.PHONY: tf-validate
tf-validate: ## terraform init -backend=false && validate on every root
	@set -e; for r in $(TF_ROOTS); do \
		echo "== validate infra/$$r =="; \
		terraform -chdir=infra/$$r init -backend=false -no-color >/dev/null; \
		terraform -chdir=infra/$$r validate -no-color; \
	done

.PHONY: tf-lint
tf-lint: ## tflint (azurerm ruleset) on every root
	@tflint --init --config=$(CURDIR)/.tflint.hcl >/dev/null
	@set -e; for r in $(TF_ROOTS); do \
		echo "== tflint infra/$$r =="; \
		tflint --chdir=infra/$$r --config=$(CURDIR)/.tflint.hcl; \
	done

.PHONY: tf-checkov
tf-checkov: ## checkov security scan (documented suppressions)
	checkov -d infra --config-file infra/.checkov.yaml

.PHONY: tf-check
tf-check: tf-fmt tf-validate tf-lint ## fmt + validate + tflint on bootstrap/platform/app

# -------------------------------------------------------------- Workflows ----
.PHONY: actionlint
actionlint: ## Lint GitHub Actions workflows
	actionlint

# ------------------------------------------------------------------ Misc ----
.PHONY: clean
clean: ## Remove caches, local audit, terraform scratch
	rm -rf .pytest_cache .ruff_cache audit_local **/__pycache__ \
		infra/*/.terraform infra/*/.terraform.lock.hcl
