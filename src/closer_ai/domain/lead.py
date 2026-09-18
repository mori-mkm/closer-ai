"""Lead contract — the person/company associated with a Deal, sourced from a CRM contact.

Design decisions worth knowing:

- Frozen, same semantics as Call/ObjectionEvent: "frozen" means "immutable snapshot", not
  "never changes in the product". A CRM re-sync produces a new Lead instance with the same
  `lead_id` but different mutable fields (name/email/phone changed) — whether storage keeps
  full history or "latest wins" is a future storage-layer decision, not this contract's.
- `company_id` reuses the tenant identifier already on `closer_ai.normalization.Call`, not a
  new `tenant_id` concept — one multi-tenancy identifier for the whole codebase.
- `source` + `external_id` (not just `external_id`) mirrors `Call.source`/`Call.source_id`:
  "which system" and "id within that system" are different facts, and conflating them would
  make `derive_lead_id` ambiguous across sources that happen to reuse id ranges.
- `company_name` (not `company`, which was the original brainstormed name): the lead's own
  employer, deliberately renamed to not collide with `company_id`, the tenant. If you're
  tempted to read "company" here as the tenant, that's the confusion this rename exists to
  prevent.
- No identifying field (name/email/phone) is required. Whether a Lead has "enough" identifying
  information to be usable for matching is `CallDealMatch`'s concern (a signal can only match
  against a field that exists) — Lead's job is to hold whatever the source gave it, not to
  gatekeep completeness.
- `lead_id` is deterministic, derived only from (company_id, source, external_id) — the same
  technique `closer_ai.normalization.ids` and `closer_ai.domain.objection` use (sha256 over
  json.dumps of a list). PII (name/email/phone/company_name/metadata) never enters the hash:
  the same external identity always maps to the same id regardless of how many times the CRM
  record is re-synced or how its name/email changed. Reimplemented locally rather than
  importing normalization's private `_hash` — normalization/** is a read-only dependency for
  other domain modules (same reasoning documented in objection.py).
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

LEAD_SCHEMA_VERSION = "1.0.0"

_ID_LENGTH = 24


def derive_lead_id(company_id: str, source: str, external_id: str) -> str:
    """Deterministic id for a Lead. Same technique as normalization/ids.py: sha256 over
    json.dumps of a list (element boundaries unambiguous, unlike concatenation)."""
    canonical = json.dumps(
        ["lead", company_id, source, external_id], ensure_ascii=True, separators=(",", ":")
    )
    return f"lead_{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:_ID_LENGTH]}"


class Lead(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: str = LEAD_SCHEMA_VERSION
    lead_id: str
    company_id: str
    source: str
    external_id: str
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    company_name: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_invariants(self) -> Lead:
        if not self.company_id.strip():
            raise ValueError("company_id must not be empty")
        if not self.source.strip():
            raise ValueError("source must not be empty")
        if not self.external_id.strip():
            raise ValueError("external_id must not be empty")

        expected_id = derive_lead_id(self.company_id, self.source, self.external_id)
        if self.lead_id != expected_id:
            raise ValueError(
                "lead_id must be derive_lead_id(company_id, source, external_id); "
                f"expected {expected_id!r}, got {self.lead_id!r}"
            )
        return self
