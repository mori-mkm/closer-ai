"""Deal identity (DEP-2): which canonical Deal a CRM source record (card) belongs to.

Proposal: docs/domain/DEAL_IDENTITY_RESOLUTION_PROPOSAL.md. A source record is never a Deal;
the link between them is a decision, kept as a linear append-only chain per source record with
the same currentness/authority rules as MatchDecision (docs/domain/CURRENT_MATCH_RESOLVER.md):
the head is current, `created_at` never orders, forks are "conflict", an automatic decision
never replaces a manual one.

Structure only, no business rules:
- the only automatic "linked" allowed is the founding self-link (the record's own
  `derive_deal_id`), which is structural identity, not a similarity signal. Linking a record to
  any other Deal requires a manual decision. Name, closer, pipeline or dates never link.
- "not_a_deal" (e.g. a card that is only an operational/automation action) is manual only:
  no automatic signal for it exists yet (open business decision).
- when ingestion should found a Deal, and how the matcher uses this, are out of scope.
"""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

from closer_ai.domain._chain import authority_chain_head, cas_append
from closer_ai.domain.deal import derive_deal_id

DEAL_IDENTITY_SCHEMA_VERSION = "1.0.0"

_ID_LENGTH = 24

IdentityStatus = Literal["linked", "unresolved", "ambiguous", "not_a_deal"]
IdentityDecidedBy = Literal["automatic", "manual"]
CurrentIdentityState = Literal[
    "linked", "unresolved", "ambiguous", "not_a_deal", "no_decision", "conflict"
]


class DealIdentityConflict(Exception):
    """Append refused: stale expected head, forked history, or manual authority."""


def _hash(prefix: str, parts: list[object]) -> str:
    canonical = json.dumps(parts, ensure_ascii=True, separators=(",", ":"))
    return f"{prefix}_{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:_ID_LENGTH]}"


def derive_source_record_key(company_id: str, provider: str, external_record_id: str) -> str:
    """Identity of a source record: same inputs as derive_deal_id, different namespace, so a
    record and the Deal it may found never share an id and providers never collide."""
    return _hash("srk", ["source_record", company_id, provider, external_record_id])


def derive_deal_identity_decision_id(
    source_record_key: str,
    status: str,
    deal_id: str | None,
    candidate_deal_ids: tuple[str, ...],
    decided_by: str,
    supersedes_decision_id: str | None,
    created_at: datetime,
) -> str:
    return _hash(
        "did",
        [
            "deal_identity_decision", source_record_key, status, deal_id,
            sorted(candidate_deal_ids), decided_by, supersedes_decision_id,
            created_at.astimezone(UTC).isoformat(),
        ],
    )


class DealIdentityDecision(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: str = DEAL_IDENTITY_SCHEMA_VERSION
    identity_decision_id: str
    company_id: str
    provider: str
    external_record_id: str
    status: IdentityStatus
    deal_id: str | None = None
    candidate_deal_ids: tuple[str, ...] = ()
    decided_by: IdentityDecidedBy
    supersedes_decision_id: str | None = None
    created_at: datetime

    @property
    def source_record_key(self) -> str:
        return derive_source_record_key(self.company_id, self.provider, self.external_record_id)

    @model_validator(mode="after")
    def _check_invariants(self) -> DealIdentityDecision:
        for name in ("company_id", "provider", "external_record_id"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} must not be empty")
        if self.created_at.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")
        if (self.status == "linked") != (self.deal_id is not None):
            raise ValueError("deal_id is set if and only if status is 'linked'")
        if self.deal_id is not None and not self.deal_id.strip():
            raise ValueError("deal_id must not be empty")
        candidates = self.candidate_deal_ids
        if len(set(candidates)) != len(candidates) or any(not c.strip() for c in candidates):
            raise ValueError("candidate_deal_ids must be unique, non-empty ids")
        if (self.status == "ambiguous") != (len(candidates) >= 2):
            raise ValueError("'ambiguous' needs at least two candidate deals; others none")
        if self.decided_by == "automatic":
            founding = derive_deal_id(self.company_id, self.provider, self.external_record_id)
            if self.status == "linked" and self.deal_id != founding:
                raise ValueError(
                    "an automatic decision can only link a record to the Deal it founds"
                )
            if self.status == "not_a_deal":
                raise ValueError("'not_a_deal' is a manual decision")

        expected = derive_deal_identity_decision_id(
            self.source_record_key, self.status, self.deal_id, self.candidate_deal_ids,
            self.decided_by, self.supersedes_decision_id, self.created_at,
        )
        if self.identity_decision_id != expected:
            raise ValueError(f"identity_decision_id does not match its derivation; expected {expected!r}")
        if self.supersedes_decision_id == self.identity_decision_id:
            raise ValueError("a decision cannot supersede itself")
        return self


class CurrentDealIdentity(BaseModel):
    """`deal_id` only for 'linked'; `candidate_deal_ids` only for 'ambiguous'."""

    model_config = ConfigDict(frozen=True)

    source_record_key: str
    state: CurrentIdentityState
    deal_id: str | None = None
    candidate_deal_ids: tuple[str, ...] = ()
    decision_id: str | None = None

    @model_validator(mode="after")
    def _check_invariants(self) -> CurrentDealIdentity:
        if (self.state == "linked") != (self.deal_id is not None):
            raise ValueError("deal_id is set if and only if state is 'linked'")
        if (self.state == "ambiguous") != bool(self.candidate_deal_ids):
            raise ValueError("candidate_deal_ids are set if and only if state is 'ambiguous'")
        if (self.state in ("no_decision", "conflict")) != (self.decision_id is None):
            raise ValueError("decision_id is None if and only if there is no current head")
        return self


def _check_record(source_record_key: str, decisions: list[DealIdentityDecision]) -> None:
    for decision in decisions:
        if decision.source_record_key != source_record_key:
            raise ValueError(
                f"decision {decision.identity_decision_id} belongs to another source record"
            )


def _id(d: DealIdentityDecision) -> str:
    return d.identity_decision_id


def _parent(d: DealIdentityDecision) -> str | None:
    return d.supersedes_decision_id


def _by(d: DealIdentityDecision) -> str:
    return d.decided_by


def resolve_deal_for_source_record(
    source_record_key: str, decisions: list[DealIdentityDecision]
) -> CurrentDealIdentity:
    _check_record(source_record_key, decisions)
    head, ok = authority_chain_head(decisions, _id, _parent, _by)
    if not ok:
        return CurrentDealIdentity(source_record_key=source_record_key, state="conflict")
    if head is None:
        return CurrentDealIdentity(source_record_key=source_record_key, state="no_decision")
    return CurrentDealIdentity(
        source_record_key=source_record_key,
        state=head.status,
        deal_id=head.deal_id,
        candidate_deal_ids=head.candidate_deal_ids,
        decision_id=head.identity_decision_id,
    )


def append_deal_identity_decision(
    history: list[DealIdentityDecision], decision: DealIdentityDecision
) -> list[DealIdentityDecision]:
    """Compare-and-swap append; the expected head is `decision.supersedes_decision_id`.
    Identical redelivery or a re-decision with the same result: history unchanged.
    Same id + different payload: ValueError. Stale head, fork, automatic over manual:
    DealIdentityConflict (reload and re-decide)."""
    _check_record(decision.source_record_key, history)
    return cas_append(
        history,
        decision,
        record_id=_id,
        parent_id=_parent,
        decided_by=_by,
        result=lambda d: (d.status, d.deal_id, frozenset(d.candidate_deal_ids)),
        conflict=DealIdentityConflict,
    )
