"""Audit clients.

Every query writes one :class:`AuditRecord`. In mock mode records go to local
files that mirror the Azure layout:

* ``audit_local/ragaudit.jsonl`` — one row per query (stands in for the
  ``ragaudit`` Table, PartitionKey=date, RowKey=trace_id);
* ``audit_local/audit-raw/<date>/<trace_id>.json`` — the full redacted record
  (stands in for the ``audit-raw`` blob container).

Free-text fields are PII-redacted before writing (mirrors the Content Safety PII
redaction applied to logs in Azure mode).
"""

from __future__ import annotations

import json

from ..schema import AuditRecord
from ..settings import Settings
from ..util import redact_pii
from .base import AuditClient


def _redact(record: AuditRecord) -> AuditRecord:
    r = record.model_copy(deep=True)
    r.original_query = redact_pii(r.original_query)
    r.rewritten_query = redact_pii(r.rewritten_query)
    return r


class LocalAuditClient(AuditClient):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.base = settings.audit_dir

    def write(self, record: AuditRecord) -> None:
        record = _redact(record)
        self.base.mkdir(parents=True, exist_ok=True)
        table_file = self.base / f"{self.settings.audit_table}.jsonl"
        with table_file.open("a", encoding="utf-8") as fh:
            fh.write(record.model_dump_json() + "\n")
        blob_dir = self.base / self.settings.audit_blob_container / record.date
        blob_dir.mkdir(parents=True, exist_ok=True)
        (blob_dir / f"{record.trace_id}.json").write_text(
            json.dumps(record.model_dump(), indent=2), encoding="utf-8"
        )


class AzureAuditClient(AuditClient):
    """Azure Table Storage + blob audit sink. Imported lazily."""

    def __init__(self, settings: Settings) -> None:  # pragma: no cover - real-Azure only
        self.settings = settings
        self._cred = None

    def _credential(self):  # pragma: no cover
        if self._cred is None:
            from azure.identity import DefaultAzureCredential

            self._cred = DefaultAzureCredential(
                managed_identity_client_id=self.settings.managed_identity_client_id or None
            )
        return self._cred

    def write(self, record: AuditRecord) -> None:  # pragma: no cover
        record = _redact(record)
        from azure.data.tables import TableClient

        account = self.settings.storage_account
        table = TableClient(
            endpoint=f"https://{account}.table.core.windows.net",
            table_name=self.settings.audit_table,
            credential=self._credential(),
        )
        entity = {
            "PartitionKey": record.date,
            "RowKey": record.trace_id,
            **{
                k: (json.dumps(v) if isinstance(v, list) else v)
                for k, v in record.model_dump().items()
                if k not in ("date", "trace_id")
            },
        }
        table.upsert_entity(entity)

        from azure.storage.blob import BlobClient

        blob = BlobClient(
            account_url=f"https://{account}.blob.core.windows.net",
            container_name=self.settings.audit_blob_container,
            blob_name=f"{record.date}/{record.trace_id}.json",
            credential=self._credential(),
        )
        blob.upload_blob(json.dumps(record.model_dump(), indent=2), overwrite=True)
