"""Deal + StageEvent contracts — the commercial opportunity and its stage history.

Design decisions worth knowing:

- Deal is the sole owner of commercial outcome. Call (closer_ai.normalization.Call) never has
  one — a Deal can have zero, one, or many Calls, and the sale exists exactly once, on the
  Deal, never duplicated per call.
- No `call_ids` field. Deal <-> Call membership lives entirely in `CallDealMatch`
  (matching.py), queried as "rows for this deal_id with status='matched'", never a list on
  Deal. A list here would be a second source of truth that can silently drift from
  CallDealMatch (a match gets rejected on review, the list isn't updated) — and on a frozen
  model, appending to it would mean re-minting the whole Deal snapshot every time a new call is
  ingested, pure churn for no structural benefit. Same reasoning as not nesting `Call` objects
  inside Deal: prefer a reference-based query over an embedded/cached list.
- Stage and DealOutcome are orthogonal axes, not one funnel ending in won/lost. `Stage` never
  contains "won"/"lost" — those live only in `DealOutcome`. This matches how Kommo/Pipedrive
  actually model it (won/lost is an independent status flag, not a pipeline stage node — a deal
  can sit at "negotiation" forever after being marked lost), and matches
  docs/architecture/DATA_MODEL.md's own Deal tree, which already lists Stage and Outcome as
  sibling nodes, not one sequence.
- Neither `current_stage` nor `outcome` has a default value. Every caller must state both
  explicitly. This is the concrete mechanism behind "OPEN must never silently become LOST, and
  UNKNOWN must never silently become OPEN": there is no fallback value that could paper over a
  caller who forgot to set outcome, which matters a lot given how many Agro deals are
  long-lived and OPEN.
- `DealOutcome` has no `STALE` value. "This OPEN deal looks abandoned" needs a
  time-since-last-activity threshold that is an undefined product decision (see
  docs/context/OPEN_QUESTIONS.md) and depends on Agro's actual sales-cycle length, which isn't
  documented anywhere yet. That's a derived label `analytics/` can compute later from
  `created_at` + `outcome='open'`, not a state this contract should invent now.
- `closed_at is not None` if and only if `outcome` is terminal (`won`/`lost`). This is enforced,
  not a convention: a "closed" deal with no close date is a data-quality problem to surface at
  ingestion, and an `open`/`unknown` deal with a `closed_at` set is a contradiction. There is no
  path through this validator where closing a deal skips stating an explicit terminal outcome.
- `DealOutcome` stays a `Literal` field on Deal, not its own entity — it has no independent
  identity, lifecycle, or audit-trail requirement stated anywhere (nobody asked "outcome
  changed from WON back to OPEN, show me why"). Promote it only if that requirement appears
  (chargebacks, reopened deals).
- Cross-entity invariant this file cannot enforce: `Deal.current_stage` should always equal the
  `stage` of the StageEvent with the latest `occurred_at` for that `deal_id`. A Deal has no
  visibility into its own StageEvent history (by design — no nesting), so this has to be
  guaranteed at the future write path (whoever persists a new Deal snapshot does it atomically
  with the StageEvent that justifies the change), not by this model in isolation. Tracked as a
  known limitation, not silently assumed away.
- `stage_event_id` deliberately includes a timestamp in its hash — a deviation from
  `derive_call_id`/`derive_objection_id`, which don't. StageEvent is a log-of-what-happened
  entity ("stage X was entered at time T"), not an extracted-fact entity — the same stage
  re-entered at a genuinely later time is a new, distinct event (a bounce-back is real signal,
  not a duplicate), while an exact redelivery of the identical (deal_id, stage, occurred_at,
  source) tuple (e.g. a retried CRM webhook) must collapse to the same id. `occurred_at` is
  canonicalized through `_canonical_timestamp` (UTC + `.isoformat()`) before hashing — two
  equivalent instants expressed with different UTC offsets must hash identically, or that
  idempotency guarantee breaks on a serialization technicality. `json.dumps` cannot serialize a
  `datetime` directly, which is the other reason this goes through a string first.
"""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

DEAL_SCHEMA_VERSION = "1.0.0"

_ID_LENGTH = 24

Stage = Literal["created", "qualification", "proposal", "negotiation", "other"]
DealOutcome = Literal["open", "won", "lost", "unknown"]

_TERMINAL_OUTCOMES: frozenset[str] = frozenset({"won", "lost"})


def _canonical_timestamp(moment: datetime) -> str:
    """UTC-normalized ISO 8601 string for use inside a deterministic-id hash input. Every id
    function in this codebase that hashes a timestamp goes through this, never
    `moment.isoformat()` directly, so two equivalent instants in different offsets always
    produce the same id."""
    return moment.astimezone(UTC).isoformat()


def derive_deal_id(company_id: str, source: str, external_id: str) -> str:
    """Deterministic id for a Deal. Same technique as normalization/ids.py and
    domain/lead.py: sha256 over json.dumps of a list, no PII in the input."""
    canonical = json.dumps(
        ["deal", company_id, source, external_id], ensure_ascii=True, separators=(",", ":")
    )
    return f"deal_{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:_ID_LENGTH]}"


def derive_stage_event_id(deal_id: str, stage: str, occurred_at: datetime, source: str) -> str:
    """Deterministic id for a StageEvent. Includes occurred_at (canonicalized to UTC) —
    see the module docstring for why this deviates from derive_call_id/derive_deal_id."""
    canonical = json.dumps(
        ["stage_event", deal_id, stage, _canonical_timestamp(occurred_at), source],
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return f"se_{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:_ID_LENGTH]}"


class Deal(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: str = DEAL_SCHEMA_VERSION
    deal_id: str
    company_id: str
    source: str
    external_id: str
    lead_id: str | None = None
    owner_id: str | None = None
    pipeline_id: str | None = None
    current_stage: Stage
    outcome: DealOutcome
    created_at: datetime
    closed_at: datetime | None = None
    value: float | None = None
    currency: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_invariants(self) -> Deal:
        if not self.company_id.strip():
            raise ValueError("company_id must not be empty")
        if not self.source.strip():
            raise ValueError("source must not be empty")
        if not self.external_id.strip():
            raise ValueError("external_id must not be empty")
        if self.created_at.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")
        if self.closed_at is not None and self.closed_at.tzinfo is None:
            raise ValueError("closed_at must be timezone-aware")

        expected_id = derive_deal_id(self.company_id, self.source, self.external_id)
        if self.deal_id != expected_id:
            raise ValueError(
                "deal_id must be derive_deal_id(company_id, source, external_id); "
                f"expected {expected_id!r}, got {self.deal_id!r}"
            )

        is_terminal = self.outcome in _TERMINAL_OUTCOMES
        if is_terminal and self.closed_at is None:
            raise ValueError(f"outcome={self.outcome!r} is terminal and requires closed_at")
        if not is_terminal and self.closed_at is not None:
            raise ValueError(f"closed_at is set but outcome={self.outcome!r} is not terminal")
        if self.closed_at is not None and self.closed_at < self.created_at:
            raise ValueError("closed_at must not be before created_at")

        if self.value is not None:
            if self.value < 0:
                raise ValueError("value must not be negative")
            if self.currency is None or not self.currency.strip():
                raise ValueError("currency is required when value is set")

        return self


class StageEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: str = DEAL_SCHEMA_VERSION
    stage_event_id: str
    deal_id: str
    stage: Stage
    occurred_at: datetime
    source: str
    external_stage_id: str | None = None

    @model_validator(mode="after")
    def _check_invariants(self) -> StageEvent:
        if not self.deal_id.strip():
            raise ValueError("deal_id must not be empty")
        if not self.source.strip():
            raise ValueError("source must not be empty")
        if self.occurred_at.tzinfo is None:
            raise ValueError("occurred_at must be timezone-aware")

        expected_id = derive_stage_event_id(self.deal_id, self.stage, self.occurred_at, self.source)
        if self.stage_event_id != expected_id:
            raise ValueError(
                "stage_event_id must be derive_stage_event_id(deal_id, stage, occurred_at, "
                f"source); expected {expected_id!r}, got {self.stage_event_id!r}"
            )
        return self
