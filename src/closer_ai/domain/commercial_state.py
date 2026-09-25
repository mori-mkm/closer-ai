"""Call -> authoritative current match -> Deal -> current Outcome.

Integration only: composes `matching.resolve_current_match` and `outcome.resolve_current_outcome`
without re-deciding anything. matching and outcome do not import each other; this module is the
only place that knows about both.

Rules this composition guarantees (see docs/domain/CURRENT_MATCH_RESOLVER.md and
docs/decisions/ADR_001-outcome-contract-v0.md):

- A deal exists for the call only when the current match state is "matched". Every other state
  (no_decision, unmatched, ambiguous, rejected, manual_review, conflict) yields no deal and the
  outcome resolver is not called. Historical matched decisions never leak: currentness is
  resolved by resolve_current_match.
- The outcome is the one of the deal named by the current match, resolved only from that deal's
  OutcomeAssessments. Outcome states (available, review_pending, no_assessment, conflict) are
  passed through unchanged.
- `Deal.outcome` (legacy CRM projection) is never read; there is no fallback to it.

Inputs may contain records of other calls/deals: selection by call_id / deal_id happens here,
explicitly, because both resolvers reject foreign records instead of filtering them.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, model_validator

from closer_ai.domain.matching import CurrentMatchResult, MatchDecision, resolve_current_match
from closer_ai.domain.outcome import CurrentOutcome, OutcomeAssessment, resolve_current_outcome


class CallCommercialState(BaseModel):
    """`current_outcome` is set if and only if the call has a canonical deal (state "matched"),
    and it always belongs to that deal."""

    model_config = ConfigDict(frozen=True)

    current_match: CurrentMatchResult
    current_outcome: CurrentOutcome | None = None

    @model_validator(mode="after")
    def _check_invariants(self) -> CallCommercialState:
        matched = self.current_match.state == "matched"
        if matched != (self.current_outcome is not None):
            raise ValueError("an outcome exists if and only if the current match is 'matched'")
        if self.current_outcome is not None and (
            self.current_outcome.deal_id != self.current_match.deal_id
        ):
            raise ValueError("the outcome must belong to the deal of the current match")
        return self

    @property
    def deal_id(self) -> str | None:
        return self.current_match.deal_id

    @property
    def is_consumable(self) -> bool:
        return self.current_outcome is not None and self.current_outcome.is_consumable


def resolve_call_commercial_state(
    call_id: str,
    match_decisions: list[MatchDecision],
    outcome_assessments: list[OutcomeAssessment],
) -> CallCommercialState:
    current_match = resolve_current_match(
        call_id, [d for d in match_decisions if d.call_id == call_id]
    )
    if current_match.state != "matched" or current_match.deal_id is None:
        return CallCommercialState(current_match=current_match)
    deal_id = current_match.deal_id
    current_outcome = resolve_current_outcome(
        deal_id, [a for a in outcome_assessments if a.deal_id == deal_id]
    )
    return CallCommercialState(current_match=current_match, current_outcome=current_outcome)
