"""Canonical Outcome v0 — structural core. Contract: docs/domain/OUTCOME_CONTRACT_V0_PROPOSAL.md
(rev. 2) and docs/decisions/ADR_001-outcome-contract-v0.md.

What this module is: the three append-only records (OutcomeEvidence, EvidenceDisposition,
OutcomeAssessment), their deterministic ids and invariants, evidence eligibility, the linear
assessment chain with compare-and-swap, human authority and canonical outcome resolution.

What it deliberately is NOT: the commercial policy that turns CRM/closer/payment signals into
a status (proposal §7.3 strength table, §9.2 selection, §9.3 reversal modifier, §9.4 review
criteria). That depends on open business decisions D-G1/D-G2/D-G5/D-G6 and is not encoded
here. Assessments are built by a caller (a future rule policy or a human) and validated here.

Distinctions kept on purpose:
- raw observation: OutcomeEvidence.raw_state / source_record_ref / observation_key;
- eligible evidence: evidence of the deal with no disposition (resolve_eligible_evidence);
- supporting evidence: OutcomeAssessment.supporting_evidence_ids (subset of eligible);
- automatic candidate: an assessment with decision_method="rule";
- authoritative canonical decision: derived from the chain (latest "human", else the head),
  always one whole stored assessment — never a status patched onto another record.

Invariant placement: the part of I12 that needs no other record (supporting ⊆ eligible) is
checked in the model; everything needing the evidence set or the chain is checked on append.

`Deal.outcome` (deal.py) is the legacy CRM projection, not the canonical outcome, and is never
read here. Linking a Call to an outcome goes through matching.resolve_current_match: only
state "matched" yields a deal_id; this module only ever sees deal_ids.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

from closer_ai.domain._chain import linear_chain

OUTCOME_SCHEMA_VERSION = "1.0.0"

_ID_LENGTH = 24

OutcomeStatus = Literal["won", "rejected", "open", "unknown"]
OutcomeEvidenceSource = Literal[
    "crm_status", "crm_note", "closer_report", "payment", "post_sale", "automation", "human",
    "other",
]
OutcomeSignal = Literal[
    "sale", "rejection", "active", "deferral", "no_contact", "reversal", "unclassified"
]
DispositionKind = Literal["invalidated", "remapped"]
DispositionDecidedBy = Literal["human", "mapping"]
DecisionMethod = Literal["rule", "human"]
OutcomeConfidence = Literal["high", "medium", "low"]
CurrentOutcomeState = Literal["available", "review_pending", "no_assessment", "conflict"]

# I4: minimum supporting signal per status; I6: what can never support "rejected".
_REQUIRED_SIGNALS: dict[str, frozenset[str]] = {
    "won": frozenset({"sale"}),
    "rejected": frozenset({"rejection"}),
    "open": frozenset({"active", "deferral"}),
}
_NEVER_SUPPORTS_REJECTED: frozenset[str] = frozenset({"no_contact", "reversal"})
_TERMINAL: frozenset[str] = frozenset({"won", "rejected"})


class OutcomeConflict(Exception):
    """Append refused: stale expected head, stale eligible set, or non-linear history.
    The caller reloads and recomputes (a human decision goes back to the human)."""


def _ts(moment: datetime | None) -> str | None:
    return None if moment is None else moment.astimezone(UTC).isoformat()


def _hash(prefix: str, parts: list[object]) -> str:
    canonical = json.dumps(parts, ensure_ascii=True, separators=(",", ":"))
    return f"{prefix}_{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:_ID_LENGTH]}"


def raw_state_digest(raw_state: str | None) -> str:
    """Lowercase hex sha256 of the exact UTF-8 bytes; "" when there is no raw state."""
    if raw_state is None:
        return ""
    return hashlib.sha256(raw_state.encode("utf-8")).hexdigest()


def derive_outcome_evidence_id(
    deal_id: str,
    source: str,
    source_record_ref: str,
    observation_key: str,
    raw_state: str | None,
    signal: str,
    observed_at: datetime,
) -> str:
    return _hash(
        "oev",
        [
            "outcome_evidence", deal_id, source, source_record_ref, observation_key,
            raw_state_digest(raw_state), signal, _ts(observed_at),
        ],
    )


def derive_evidence_disposition_id(
    evidence_id: str,
    kind: str,
    replacement_evidence_id: str | None,
    decided_by: str,
    mapping_version: str | None,
    decided_at: datetime,
) -> str:
    return _hash(
        "odp",
        [
            "evidence_disposition", evidence_id, kind, replacement_evidence_id, decided_by,
            mapping_version, _ts(decided_at),
        ],
    )


def derive_outcome_assessment_id(
    deal_id: str,
    status: str,
    supporting_evidence_ids: tuple[str, ...],
    eligible_evidence_ids: tuple[str, ...],
    confidence_level: str | None,
    needs_human_review: bool,
    decision_method: str,
    policy_version: str | None,
    effective_at: datetime | None,
    decided_at: datetime,
    supersedes_assessment_id: str | None,
) -> str:
    return _hash(
        "oas",
        [
            "outcome_assessment", deal_id, status, sorted(supporting_evidence_ids),
            sorted(eligible_evidence_ids), confidence_level, needs_human_review,
            decision_method, policy_version, _ts(effective_at), _ts(decided_at),
            supersedes_assessment_id,
        ],
    )


def _require_tz(name: str, moment: datetime | None) -> None:
    if moment is not None and moment.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware")


def _require_text(name: str, value: str) -> None:
    if not value.strip():
        raise ValueError(f"{name} must not be empty")


def _check_id(name: str, actual: str, expected: str) -> None:
    if actual != expected:
        raise ValueError(f"{name} does not match its derivation; expected {expected!r}")


class OutcomeEvidence(BaseModel):
    """One observation from one source, attributed to a deal. Append-only (§7.1)."""

    model_config = ConfigDict(frozen=True)

    schema_version: str = OUTCOME_SCHEMA_VERSION
    evidence_id: str
    deal_id: str
    source: OutcomeEvidenceSource
    source_record_ref: str
    observation_key: str
    raw_state: str | None = None
    signal: OutcomeSignal
    observed_at: datetime

    @model_validator(mode="after")
    def _check_invariants(self) -> OutcomeEvidence:
        _require_text("deal_id", self.deal_id)
        _require_text("source_record_ref", self.source_record_ref)
        _require_text("observation_key", self.observation_key)
        _require_tz("observed_at", self.observed_at)
        if self.source == "crm_status" and self.raw_state is None:
            raise ValueError("raw_state is required for source='crm_status'")
        if self.source == "crm_note" and self.raw_state is not None:
            raise ValueError("free-text sources never store raw text; raw_state must be None")
        _check_id(
            "evidence_id",
            self.evidence_id,
            derive_outcome_evidence_id(
                self.deal_id, self.source, self.source_record_ref, self.observation_key,
                self.raw_state, self.signal, self.observed_at,
            ),
        )
        return self


class EvidenceDisposition(BaseModel):
    """Append-only correction of one evidence's eligibility; nothing is deleted (§7.2)."""

    model_config = ConfigDict(frozen=True)

    schema_version: str = OUTCOME_SCHEMA_VERSION
    disposition_id: str
    evidence_id: str
    kind: DispositionKind
    replacement_evidence_id: str | None = None
    decided_by: DispositionDecidedBy
    mapping_version: str | None = None
    decided_at: datetime

    @model_validator(mode="after")
    def _check_invariants(self) -> EvidenceDisposition:
        _require_text("evidence_id", self.evidence_id)
        _require_tz("decided_at", self.decided_at)
        if (self.kind == "remapped") != (self.replacement_evidence_id is not None):
            raise ValueError("replacement_evidence_id is required if and only if kind='remapped'")
        if self.replacement_evidence_id == self.evidence_id:
            raise ValueError("an evidence cannot be remapped to itself")
        if self.kind == "invalidated" and self.decided_by != "human":
            raise ValueError("only a human can invalidate evidence")
        if (self.decided_by == "mapping") != (self.mapping_version is not None):
            raise ValueError("mapping_version is required if and only if decided_by='mapping'")
        _check_id(
            "disposition_id",
            self.disposition_id,
            derive_evidence_disposition_id(
                self.evidence_id, self.kind, self.replacement_evidence_id, self.decided_by,
                self.mapping_version, self.decided_at,
            ),
        )
        return self


class OutcomeAssessment(BaseModel):
    """One whole outcome decision bundle for a deal (§8.2). decision_method="rule" records are
    candidates; which record is authoritative is derived from the chain (§8.3)."""

    model_config = ConfigDict(frozen=True)

    schema_version: str = OUTCOME_SCHEMA_VERSION
    assessment_id: str
    deal_id: str
    status: OutcomeStatus
    supporting_evidence_ids: tuple[str, ...]
    eligible_evidence_ids: tuple[str, ...]
    confidence_level: OutcomeConfidence | None
    needs_human_review: bool
    decision_method: DecisionMethod
    policy_version: str | None = None
    effective_at: datetime | None = None
    decided_at: datetime
    supersedes_assessment_id: str | None = None

    @model_validator(mode="after")
    def _check_invariants(self) -> OutcomeAssessment:
        _require_text("deal_id", self.deal_id)
        _require_tz("decided_at", self.decided_at)
        _require_tz("effective_at", self.effective_at)
        for name in ("supporting_evidence_ids", "eligible_evidence_ids"):
            ids = getattr(self, name)
            if len(set(ids)) != len(ids) or any(not i.strip() for i in ids):
                raise ValueError(f"{name} must be unique, non-empty ids")
        if not set(self.supporting_evidence_ids) <= set(self.eligible_evidence_ids):
            raise ValueError("supporting_evidence_ids must be a subset of eligible_evidence_ids")
        if self.status != "unknown" and not self.supporting_evidence_ids:
            raise ValueError(f"status={self.status!r} needs at least one supporting evidence")
        if (self.confidence_level is None) != (self.status == "unknown"):
            raise ValueError("confidence_level is None if and only if status is 'unknown'")
        if (self.effective_at is not None) != (self.status in _TERMINAL):
            raise ValueError("effective_at is required if and only if status is won/rejected")
        if self.effective_at is not None and self.effective_at > self.decided_at:
            raise ValueError("effective_at must not be after decided_at")
        if (self.decision_method == "rule") != (self.policy_version is not None):
            raise ValueError("policy_version is required if and only if decision_method='rule'")
        if self.decision_method == "human":
            if self.needs_human_review:
                raise ValueError("a human decision never needs human review")
            if self.confidence_level not in ("high", None):
                raise ValueError("a human decision has confidence 'high' (or None if unknown)")
        _check_id(
            "assessment_id",
            self.assessment_id,
            derive_outcome_assessment_id(
                self.deal_id, self.status, self.supporting_evidence_ids,
                self.eligible_evidence_ids, self.confidence_level, self.needs_human_review,
                self.decision_method, self.policy_version, self.effective_at,
                self.decided_at, self.supersedes_assessment_id,
            ),
        )
        if self.supersedes_assessment_id == self.assessment_id:
            raise ValueError("an assessment cannot supersede itself")
        return self


class CurrentOutcome(BaseModel):
    """Canonical outcome of a deal. `canonical` is a whole stored assessment (or None for
    no_assessment/conflict); only state "available" may be consumed by analytics (I16)."""

    model_config = ConfigDict(frozen=True)

    deal_id: str
    state: CurrentOutcomeState
    canonical: OutcomeAssessment | None = None

    @model_validator(mode="after")
    def _check_invariants(self) -> CurrentOutcome:
        if (self.canonical is None) != (self.state in ("no_assessment", "conflict")):
            raise ValueError("canonical is set if and only if state is available/review_pending")
        return self

    @property
    def status(self) -> OutcomeStatus | None:
        return None if self.canonical is None else self.canonical.status

    @property
    def is_consumable(self) -> bool:
        return self.state == "available"


# --- append-only stores (pure functions, no storage) ------------------------------------------


def _append_unique(records: list, record, record_id: str) -> list:
    existing = next((r for r in records if getattr(r, record_id) == getattr(record, record_id)), None)
    if existing is None:
        return [*records, record]
    if existing != record:
        raise ValueError(f"same {record_id} with different payload: {getattr(record, record_id)}")
    return list(records)


def append_outcome_evidence(
    evidence: list[OutcomeEvidence], new: OutcomeEvidence
) -> list[OutcomeEvidence]:
    """Identical redelivery is a no-op; same id + different payload is a hard error."""
    return _append_unique(evidence, new, "evidence_id")


def append_evidence_disposition(
    dispositions: list[EvidenceDisposition],
    new: EvidenceDisposition,
    evidence: list[OutcomeEvidence],
) -> list[EvidenceDisposition]:
    """I14: the evidence exists; at most one disposition per evidence; a remap replacement is
    the same observation with a different signal. Identical redelivery is a no-op."""
    result = _append_unique(dispositions, new, "disposition_id")
    if result == list(dispositions):
        return result
    _index_dispositions(_index_evidence(evidence), result)
    return result


def _index_evidence(evidence: Iterable[OutcomeEvidence]) -> dict[str, OutcomeEvidence]:
    by_id: dict[str, OutcomeEvidence] = {}
    for item in evidence:
        seen = by_id.get(item.evidence_id)
        if seen is not None and seen != item:
            raise ValueError(f"same evidence_id with different payload: {item.evidence_id}")
        by_id[item.evidence_id] = item
    return by_id


def _index_dispositions(
    by_evidence_id: dict[str, OutcomeEvidence], dispositions: Iterable[EvidenceDisposition]
) -> dict[str, EvidenceDisposition]:
    by_target: dict[str, EvidenceDisposition] = {}
    for disposition in dispositions:
        target = by_evidence_id.get(disposition.evidence_id)
        if target is None:
            raise ValueError(f"disposition {disposition.disposition_id} targets unknown evidence")
        seen = by_target.get(disposition.evidence_id)
        if seen is not None and seen != disposition:
            raise ValueError(f"evidence {disposition.evidence_id} already has a disposition")
        if disposition.kind == "remapped":
            replacement = by_evidence_id.get(disposition.replacement_evidence_id or "")
            if replacement is None:
                raise ValueError("remap replacement evidence is unknown")
            same_observation = (
                replacement.deal_id, replacement.source, replacement.source_record_ref,
                replacement.observation_key, replacement.raw_state, replacement.observed_at,
            ) == (
                target.deal_id, target.source, target.source_record_ref,
                target.observation_key, target.raw_state, target.observed_at,
            )
            if not same_observation or replacement.signal == target.signal:
                raise ValueError(
                    "a remap replacement must be the same observation with a different signal"
                )
        by_target[disposition.evidence_id] = disposition
    return by_target


def resolve_eligible_evidence(
    deal_id: str, evidence: list[OutcomeEvidence], dispositions: list[EvidenceDisposition]
) -> tuple[OutcomeEvidence, ...]:
    """Evidence of `deal_id` with no disposition, ordered by evidence_id. The only evidence a
    decision may be made on — never "all evidence ever observed". Evidence or dispositions of
    another deal are an error, not silently filtered."""
    for item in evidence:
        if item.deal_id != deal_id:
            raise ValueError(f"evidence {item.evidence_id} belongs to another deal")
    by_id = _index_evidence(evidence)
    disposed = _index_dispositions(by_id, dispositions)
    return tuple(sorted((e for eid, e in by_id.items() if eid not in disposed),
                        key=lambda e: e.evidence_id))


# --- assessment chain -------------------------------------------------------------------------


def _assessment_chain(
    deal_id: str, assessments: list[OutcomeAssessment]
) -> list[OutcomeAssessment] | None:
    for assessment in assessments:
        if assessment.deal_id != deal_id:
            raise ValueError(f"assessment {assessment.assessment_id} belongs to another deal")
    return linear_chain(
        assessments, lambda a: a.assessment_id, lambda a: a.supersedes_assessment_id
    )


def _authoritative(chain: list[OutcomeAssessment]) -> OutcomeAssessment:
    """Latest human assessment in the chain, else the head (§8.3). Not `head.decision_method`:
    rule records after a human decision are candidates and do not take authority away."""
    return next((a for a in reversed(chain) if a.decision_method == "human"), chain[-1])


def resolve_current_outcome(deal_id: str, assessments: list[OutcomeAssessment]) -> CurrentOutcome:
    chain = _assessment_chain(deal_id, assessments)
    if chain is None:
        return CurrentOutcome(deal_id=deal_id, state="conflict")
    if not chain:
        return CurrentOutcome(deal_id=deal_id, state="no_assessment")
    state: CurrentOutcomeState = "review_pending" if chain[-1].needs_human_review else "available"
    return CurrentOutcome(deal_id=deal_id, state=state, canonical=_authoritative(chain))


def append_outcome_assessment(
    assessments: list[OutcomeAssessment],
    new: OutcomeAssessment,
    *,
    evidence: list[OutcomeEvidence],
    dispositions: list[EvidenceDisposition],
) -> list[OutcomeAssessment]:
    """Compare-and-swap append (§10.1) plus the cross-record invariants (§12). The expected head
    is `new.supersedes_assessment_id`. Returns the history unchanged for an identical
    redelivery. Raises OutcomeConflict (reload and recompute) or ValueError (invalid record)."""
    chain = _assessment_chain(new.deal_id, assessments)
    if chain is None:
        raise OutcomeConflict("assessment history is not a linear chain; manual repair required")

    existing = next((a for a in chain if a.assessment_id == new.assessment_id), None)
    if existing is not None:
        if existing != new:
            raise ValueError(f"same assessment_id with different payload: {new.assessment_id}")
        return list(assessments)

    head = chain[-1] if chain else None
    actual_head = head.assessment_id if head is not None else None
    if new.supersedes_assessment_id != actual_head:
        raise OutcomeConflict(
            f"stale write: expected head {new.supersedes_assessment_id!r}, actual head "
            f"{actual_head!r}; reload and recompute"
        )

    eligible = {e.evidence_id: e for e in resolve_eligible_evidence(new.deal_id, evidence, dispositions)}
    if set(new.eligible_evidence_ids) != set(eligible):
        raise OutcomeConflict("stale eligible evidence set; reload and recompute")

    supporting = [eligible[i] for i in new.supporting_evidence_ids]
    required = _REQUIRED_SIGNALS.get(new.status)
    if required is not None and not any(e.signal in required for e in supporting):
        raise ValueError(f"status={new.status!r} needs supporting evidence with {sorted(required)}")
    if new.status == "rejected" and any(
        e.signal in _NEVER_SUPPORTS_REJECTED or e.source == "automation" for e in supporting
    ):
        raise ValueError("no_contact, reversal and automation evidence never support 'rejected'")

    becomes_canonical = new.decision_method == "human" or not any(
        a.decision_method == "human" for a in chain
    )
    if becomes_canonical and new.decision_method == "rule" and head is not None:
        _check_leaving_terminal(head, new, eligible)
    return [*assessments, new]


def _check_leaving_terminal(
    previous: OutcomeAssessment, new: OutcomeAssessment, eligible: dict[str, OutcomeEvidence]
) -> None:
    """I9: a rule assessment that becomes canonical and leaves won/rejected needs new evidence
    observed after the previous effective_at, or removal of previous supporting evidence."""
    cutoff = previous.effective_at  # set for every won/rejected assessment (I7)
    if cutoff is None or new.status == previous.status:
        return
    seen_before = set(previous.eligible_evidence_ids)
    has_new_evidence = any(
        eid not in seen_before and e.observed_at > cutoff for eid, e in eligible.items()
    )
    lost_support = any(i not in eligible for i in previous.supporting_evidence_ids)
    if not (has_new_evidence or lost_support):
        raise ValueError(
            f"leaving {previous.status!r} needs new evidence, removed support, or a human decision"
        )
