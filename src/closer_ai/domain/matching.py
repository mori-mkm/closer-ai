"""CallDealMatch + MatchEvidence — Call<->Deal matching evidence, never a silent decision.

A CallDealMatch means "the evidence available suggests this call belongs to this deal", never
"the algorithm is certain". One row = one (call, candidate deal, method, attempt) tuple, not a
single mutable "current belief" per call — multiple rows can and do exist for the same call
(ties, different methods, re-runs over time). CallDealMatch rows are candidates/attempts, never
the authoritative answer: "what's the accepted match for this call right now" is answered only
by `resolve_current_match` over the call's `MatchDecision` chain (bottom of this module, see
docs/domain/CURRENT_MATCH_RESOLVER.md). Never "latest row by created_at with status='matched'"
— that resurrects a match a later decision rejected, made ambiguous or replaced.

Design decisions worth knowing:

- `deal_id` is optional. `status='unmatched'` means no candidate deal was found at all — there
  is no deal to reference, so `deal_id` must be `None` in that case (and required, non-empty,
  for every other status). `matching_method` still applies to an unmatched row: it records
  which strategy was tried and found nothing (e.g. "tried exact_email, no deal has that email").
- `MatchMethod` is one flat closed enum, not a nested deterministic/heuristic/manual taxonomy.
  The "reliability tier" a nested taxonomy would encode is already expressed by
  `confidence_level` below — a parallel "method_class" field would be redundant, and redundant
  fields drift (e.g. someone marks `exact_email` as medium confidence, which shouldn't be
  possible if it's deterministic by definition).
- Confidence is `confidence_level` (HIGH/MEDIUM/LOW, always required) + `confidence_score`
  (float, optional), not a bare float. A bare float alone isn't auditable without an
  externally-tracked threshold table that can drift from the code; worse, deterministic methods
  (exact_email, exact_phone, exact_external_id, manual) don't have a real graded score at all —
  forcing them to report a fabricated constant (e.g. always 1.0) would repeat exactly the
  reason domain/objection.py's ObjectionEvent doesn't have a confidence field in v0 ("a constant
  with no signal"). Deterministic/manual methods are enforced to have `confidence_level='high'`
  and `confidence_score=None`; heuristic methods carry a real score in [0, 1] plus an
  independently-supplied level. The numeric score->level band mapping (e.g. >=0.85 high,
  0.6-0.85 medium, <0.6 low) is a matching-algorithm calibration concern, not hardcoded here —
  baking exact cutoffs into a frozen domain-layer validator would force a schema version bump
  every time the algorithm is retuned against a golden set.
- `status='matched'` requiring `confidence_level='high'` is deliberately NOT enforced by this
  model's validator, even though it is the intended policy. Embedding that rule here would be
  the same class of calibration/risk decision the paragraph above already avoids hardcoding —
  just at the status level instead of the score level. Instead, it's the matching algorithm's
  (write path's) responsibility to never emit `status='matched'` for anything below high
  confidence, routing anything else to `manual_review` instead. This mirrors how "never
  silently prefer the higher-scoring candidate under AMBIGUOUS" is also a write-path
  responsibility, not something a single row's validator can see (a row has no visibility into
  its sibling candidate rows). AMBIGUOUS itself is represented as multiple rows — one
  CallDealMatch per candidate deal, same call_id, same created_at (same batch run), different
  deal_id/confidence_score, all status='ambiguous' — never a single "winner" row with the
  losing candidates silently discarded.
- `MatchEvidence.detail` is a free-text, non-PII note (e.g. "89% name similarity", "within 15
  min of call start"), never the raw compared value (never a real email/phone/name). This is a
  documented caller convention, not something this schema can enforce — nothing stops a
  careless caller from putting a raw email in `detail`; there is no reliable general-purpose PII
  detector in scope here. Treat it as a real, open gap, not a solved one.
- `MatchMethod` (the method that ultimately produced this row) and `EvidenceSignal` (the
  individual signals that support it) are two different enums on purpose, not redundant: a
  `name_and_datetime` match is typically composed of `name_similarity` + `datetime_proximity`
  evidence entries. One describes the outcome, the other describes the inputs that led there.
- `call_deal_match_id` includes `created_at` in its hash, for the same reason
  `stage_event_id` does (see deal.py's module docstring) — this is an attempt-log entity, not
  an extracted fact. Two attempts at matching the same (call, candidate deal, method) at
  different times are distinct records by this design's own definition ("one row = one
  attempt"); an exact redelivery of the same attempt collapses to the same id. `created_at` is
  canonicalized to UTC via the same `_canonical_timestamp` convention deal.py establishes,
  before it ever reaches `json.dumps`.
"""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, model_validator

from closer_ai.domain._chain import authority_chain_head, cas_append
from closer_ai.domain.deal import Deal
from closer_ai.normalization.models import Call

MATCHING_SCHEMA_VERSION = "1.0.0"

_ID_LENGTH = 24

MatchMethod = Literal[
    "exact_external_id",
    "exact_email",
    "exact_phone",
    "name_and_datetime",
    "name_only",
    "manual",
    "other",
]

_DETERMINISTIC_METHODS: frozenset[str] = frozenset(
    {"exact_external_id", "exact_email", "exact_phone", "manual"}
)

MatchStatus = Literal["matched", "ambiguous", "rejected", "unmatched", "manual_review"]

ConfidenceLevel = Literal["high", "medium", "low"]

EvidenceSignal = Literal[
    "external_id_exact",
    "email_exact",
    "phone_exact",
    "name_similarity",
    "datetime_proximity",
    "human_decision",
    "other",
]


def _canonical_timestamp(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat()


def derive_call_deal_match_id(
    call_id: str, deal_id: str | None, matching_method: str, created_at: datetime
) -> str:
    """Deterministic id for a CallDealMatch attempt. `deal_id` may be None (unmatched) — see
    the module docstring for why created_at is part of the hash."""
    canonical = json.dumps(
        ["call_deal_match", call_id, deal_id, matching_method, _canonical_timestamp(created_at)],
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return f"cdm_{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:_ID_LENGTH]}"


class MatchEvidence(BaseModel):
    model_config = ConfigDict(frozen=True)

    signal: EvidenceSignal
    matched: bool
    score: float | None = None
    detail: str | None = None

    @model_validator(mode="after")
    def _check_invariants(self) -> MatchEvidence:
        if self.score is not None and not (0.0 <= self.score <= 1.0):
            raise ValueError("score must be between 0.0 and 1.0")
        return self


class CallDealMatch(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: str = MATCHING_SCHEMA_VERSION
    call_deal_match_id: str
    call_id: str
    deal_id: str | None = None
    matching_method: MatchMethod
    status: MatchStatus
    confidence_level: ConfidenceLevel
    confidence_score: float | None = None
    evidence: list[MatchEvidence] = Field(default_factory=list)
    created_at: datetime

    @model_validator(mode="after")
    def _check_invariants(self) -> CallDealMatch:
        if not self.call_id.strip():
            raise ValueError("call_id must not be empty")
        if self.created_at.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")

        if self.status == "unmatched":
            if self.deal_id is not None:
                raise ValueError("deal_id must be None when status is 'unmatched'")
        else:
            if self.deal_id is None or not self.deal_id.strip():
                raise ValueError(f"deal_id is required when status is {self.status!r}")
            if not self.evidence:
                raise ValueError(f"evidence must not be empty when status is {self.status!r}")

        if self.matching_method in _DETERMINISTIC_METHODS:
            if self.confidence_level != "high":
                raise ValueError(
                    f"matching_method={self.matching_method!r} is deterministic and must "
                    "have confidence_level='high'"
                )
            if self.confidence_score is not None:
                raise ValueError(
                    f"matching_method={self.matching_method!r} is deterministic and must not "
                    "carry a confidence_score (no graded signal to report)"
                )
        elif self.confidence_score is not None and not (0.0 <= self.confidence_score <= 1.0):
            raise ValueError("confidence_score must be between 0.0 and 1.0")

        expected_id = derive_call_deal_match_id(
            self.call_id, self.deal_id, self.matching_method, self.created_at
        )
        if self.call_deal_match_id != expected_id:
            raise ValueError(
                "call_deal_match_id must be derive_call_deal_match_id(call_id, deal_id, "
                f"matching_method, created_at); expected {expected_id!r}, got "
                f"{self.call_deal_match_id!r}"
            )
        return self


@runtime_checkable
class CallDealMatcher(Protocol):
    """Provider-agnostic seam for Call<->Deal matching, same pattern as
    `closer_ai.ai.objection_extraction.ObjectionExtractor`: callers depend on this interface,
    never on a concrete implementation. A future name/email/phone-heuristic or CRM-backed
    matcher implements this same signature.

    Returns a list, not a single result: an AMBIGUOUS outcome is multiple CallDealMatch rows
    (one per tied candidate, see matching.py's module docstring) — a single-result return type
    would make that representation impossible. An UNMATCHED outcome is a single row with
    `deal_id=None`, not an empty list, so "no match" and "not evaluated yet" are never
    confused.
    """

    def match(self, call: Call, candidates: list[Deal]) -> list[CallDealMatch]:
        ...


class ExactExternalIdMatcher:
    """Deterministic reference implementation of `CallDealMatcher`.

    The only signal used is `call.source_id == deal.external_id` (both already required,
    non-PII fields on Call/Deal today) — e.g. a CRM/Zoom integration that stamps the same
    identifier on both the meeting and the deal record. No email/phone comparison: `Call`'s
    `Participant` (normalization/models.py) does not carry email or phone at all, so any
    email/phone-based matching would need to invent a field this codebase doesn't have yet
    (exactly the "não depender de payload hipotético do Kommo" restriction this task set) or
    reach into `AgroParseResult.metadata`, which is not part of the canonical `Call` this
    matcher receives. Extending to `exact_email`/`exact_phone`/heuristic methods is future
    work once a real source of that data on `Call` (or a richer input beyond `Call` alone) is
    decided — deliberately not guessed at here.
    """

    def match(self, call: Call, candidates: list[Deal]) -> list[CallDealMatch]:
        created_at = datetime.now(UTC)
        # dedupe by deal_id first: a caller passing the same deal twice (e.g. a duplicated
        # join upstream) is not two distinct candidates and must never look like ambiguity —
        # that would be exactly the "false ambiguity from a caller bug" failure mode, the
        # mirror image of the "silently pick a winner" one this whole contract exists to
        # prevent.
        seen_deal_ids: set[str] = set()
        matches: list[Deal] = []
        for deal in candidates:
            if deal.external_id == call.source_id and deal.deal_id not in seen_deal_ids:
                seen_deal_ids.add(deal.deal_id)
                matches.append(deal)

        if not matches:
            return [
                CallDealMatch(
                    call_deal_match_id=derive_call_deal_match_id(
                        call.call_id, None, "exact_external_id", created_at
                    ),
                    call_id=call.call_id,
                    deal_id=None,
                    matching_method="exact_external_id",
                    status="unmatched",
                    confidence_level="high",
                    evidence=[],
                    created_at=created_at,
                )
            ]

        status: MatchStatus = "matched" if len(matches) == 1 else "ambiguous"
        return [
            CallDealMatch(
                call_deal_match_id=derive_call_deal_match_id(
                    call.call_id, deal.deal_id, "exact_external_id", created_at
                ),
                call_id=call.call_id,
                deal_id=deal.deal_id,
                matching_method="exact_external_id",
                status=status,
                confidence_level="high",
                evidence=[MatchEvidence(signal="external_id_exact", matched=True)],
                created_at=created_at,
            )
            for deal in matches
        ]


# --- Current authoritative match (DEP-1) -------------------------------------------------------
#
# CallDealMatch rows above are candidates/attempts. The authoritative answer for a call is a
# linear, append-only chain of MatchDecision records: each decision names the head it replaces
# (`supersedes_decision_id`, compare-and-swap), the current result is the chain head, and
# `created_at` never orders anything. Full rationale: docs/domain/CURRENT_MATCH_RESOLVER.md.

MatchDecidedBy = Literal["automatic", "manual"]

CurrentMatchState = Literal[
    "matched", "ambiguous", "rejected", "unmatched", "manual_review", "no_decision", "conflict"
]


class MatchDecisionConflict(Exception):
    """Append refused: stale expected head, forked history, or manual authority."""


def derive_match_decision_id(
    call_id: str,
    status: str,
    deal_id: str | None,
    match_ids: tuple[str, ...],
    decided_by: str,
    supersedes_decision_id: str | None,
    created_at: datetime,
) -> str:
    """Deterministic id over every content field, so same id + different payload can only mean
    a bug, never a legitimate redelivery. `created_at` is hashed for uniqueness only; it never
    decides which decision is current."""
    canonical = json.dumps(
        [
            "match_decision",
            call_id,
            status,
            deal_id,
            sorted(match_ids),
            decided_by,
            supersedes_decision_id,
            _canonical_timestamp(created_at),
        ],
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return f"mdc_{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:_ID_LENGTH]}"


class MatchDecision(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: str = MATCHING_SCHEMA_VERSION
    match_decision_id: str
    call_id: str
    status: MatchStatus
    deal_id: str | None = None
    match_ids: tuple[str, ...] = ()
    decided_by: MatchDecidedBy
    supersedes_decision_id: str | None = None
    created_at: datetime

    @model_validator(mode="after")
    def _check_invariants(self) -> MatchDecision:
        if not self.call_id.strip():
            raise ValueError("call_id must not be empty")
        if self.created_at.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")
        if self.status == "matched":
            if self.deal_id is None or not self.deal_id.strip():
                raise ValueError("a matched decision must name exactly one deal_id")
        elif self.deal_id is not None:
            raise ValueError(f"deal_id must be None when status is {self.status!r}")
        if len(set(self.match_ids)) != len(self.match_ids) or any(
            not m.strip() for m in self.match_ids
        ):
            raise ValueError("match_ids must be unique, non-empty ids")
        if self.decided_by == "automatic" and not self.match_ids:
            raise ValueError("an automatic decision must cite the CallDealMatch rows it came from")

        expected_id = derive_match_decision_id(
            self.call_id,
            self.status,
            self.deal_id,
            self.match_ids,
            self.decided_by,
            self.supersedes_decision_id,
            self.created_at,
        )
        if self.match_decision_id != expected_id:
            raise ValueError(
                f"match_decision_id must be derive_match_decision_id(...); expected "
                f"{expected_id!r}, got {self.match_decision_id!r}"
            )
        if self.supersedes_decision_id == self.match_decision_id:
            raise ValueError("a decision cannot supersede itself")
        return self


class CurrentMatchResult(BaseModel):
    """`deal_id` is set only for state 'matched' — the only state with a canonical deal."""

    model_config = ConfigDict(frozen=True)

    call_id: str
    state: CurrentMatchState
    deal_id: str | None = None
    decision_id: str | None = None

    @model_validator(mode="after")
    def _check_invariants(self) -> CurrentMatchResult:
        if (self.state == "matched") != (self.deal_id is not None):
            raise ValueError("deal_id is set if and only if state is 'matched'")
        if (self.state in ("no_decision", "conflict")) != (self.decision_id is None):
            raise ValueError("decision_id is None if and only if there is no current head")
        return self


def _chain_head(
    call_id: str, decisions: list[MatchDecision]
) -> tuple[MatchDecision | None, bool]:
    """(head, ok). ok=False means the history is not one linear chain (fork, dangling
    supersession, several roots, cycle, automatic over manual) — never repaired by picking a
    winner."""
    _check_call(call_id, decisions)
    return authority_chain_head(
        decisions,
        lambda d: d.match_decision_id,
        lambda d: d.supersedes_decision_id,
        lambda d: d.decided_by,
    )


def _check_call(call_id: str, decisions: list[MatchDecision]) -> None:
    for decision in decisions:
        if decision.call_id != call_id:
            raise ValueError(
                f"decision {decision.match_decision_id} belongs to call {decision.call_id!r}, "
                f"not {call_id!r}"
            )


def resolve_current_match(call_id: str, decisions: list[MatchDecision]) -> CurrentMatchResult:
    """The authoritative current match result for `call_id`. Currentness is resolved first
    (chain head), status is interpreted second. CallDealMatch rows are never consulted: rows
    without any decision (legacy history, or matcher output nobody decided on) resolve to
    'no_decision', never to whatever the latest matched row says."""
    head, ok = _chain_head(call_id, decisions)
    if not ok:
        return CurrentMatchResult(call_id=call_id, state="conflict")
    if head is None:
        return CurrentMatchResult(call_id=call_id, state="no_decision")
    return CurrentMatchResult(
        call_id=call_id,
        state=head.status,
        deal_id=head.deal_id,
        decision_id=head.match_decision_id,
    )


def append_match_decision(
    history: list[MatchDecision], decision: MatchDecision
) -> list[MatchDecision]:
    """Compare-and-swap append. Returns the new history (unchanged for an idempotent
    redelivery or a no-op re-decision); raises MatchDecisionConflict for a stale expected
    head, a forked history, or an automatic decision over a manual one; ValueError for
    same id + different payload or a decision from another call."""
    _check_call(decision.call_id, history)
    return cas_append(
        history,
        decision,
        record_id=lambda d: d.match_decision_id,
        parent_id=lambda d: d.supersedes_decision_id,
        decided_by=lambda d: d.decided_by,
        result=lambda d: (d.status, d.deal_id),
        conflict=MatchDecisionConflict,
    )


def decision_from_matcher_output(
    rows: list[CallDealMatch], *, supersedes_decision_id: str | None, created_at: datetime
) -> MatchDecision:
    """Automatic decision for one matcher batch (e.g. one ExactExternalIdMatcher.match call).
    A candidate becomes canonical only through a decision, and only as a single matched row;
    an ambiguous batch stays ambiguous."""
    if not rows:
        raise ValueError("a matcher batch has at least one row")
    if len({row.call_id for row in rows}) != 1 or len({row.status for row in rows}) != 1:
        raise ValueError("a matcher batch must share one call_id and one status")
    if len({row.call_deal_match_id for row in rows}) != len(rows):
        raise ValueError("a matcher batch must not repeat the same CallDealMatch row")
    status = rows[0].status
    if status == "matched" and len(rows) != 1:
        raise ValueError("several matched rows in one batch is ambiguity, not a match")
    if status == "ambiguous" and len(rows) < 2:
        raise ValueError("an ambiguous batch needs at least two candidate rows")

    call_id = rows[0].call_id
    deal_id = rows[0].deal_id if status == "matched" else None
    match_ids = tuple(sorted(row.call_deal_match_id for row in rows))
    return MatchDecision(
        match_decision_id=derive_match_decision_id(
            call_id, status, deal_id, match_ids, "automatic", supersedes_decision_id, created_at
        ),
        call_id=call_id,
        status=status,
        deal_id=deal_id,
        match_ids=match_ids,
        decided_by="automatic",
        supersedes_decision_id=supersedes_decision_id,
        created_at=created_at,
    )
