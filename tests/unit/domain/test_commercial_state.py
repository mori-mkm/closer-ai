"""Call -> current match -> Deal -> current Outcome (integration of existing resolvers only)."""
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from closer_ai.domain.commercial_state import CallCommercialState, resolve_call_commercial_state
from closer_ai.domain.deal import Deal, derive_deal_id
from closer_ai.domain.matching import (
    CallDealMatch,
    CurrentMatchResult,
    MatchDecision,
    MatchEvidence,
    derive_call_deal_match_id,
    derive_match_decision_id,
)
from closer_ai.domain.outcome import (
    CurrentOutcome,
    OutcomeAssessment,
    OutcomeEvidence,
    append_outcome_assessment,
    derive_outcome_assessment_id,
    derive_outcome_evidence_id,
)

CALL_A, CALL_B = "call_a", "call_b"
DEAL_A = derive_deal_id("agrotalento-001", "kommo", "card-a")
DEAL_B = derive_deal_id("agrotalento-001", "kommo", "card-b")
T1 = datetime(2026, 5, 1, 10, 0, tzinfo=UTC)
T2 = datetime(2026, 5, 2, 10, 0, tzinfo=UTC)
T3 = datetime(2026, 5, 3, 10, 0, tzinfo=UTC)


def decision(status, deal_id=None, *, call_id=CALL_A, supersedes=None, at=T1):
    match_ids = ("cdm_x",)
    return MatchDecision(
        match_decision_id=derive_match_decision_id(
            call_id, status, deal_id, match_ids, "automatic", supersedes, at
        ),
        call_id=call_id, status=status, deal_id=deal_id, match_ids=match_ids,
        decided_by="automatic", supersedes_decision_id=supersedes, created_at=at,
    )


def sale(deal_id):
    return OutcomeEvidence(
        evidence_id=derive_outcome_evidence_id(deal_id, "payment", "pay-1", "event:1", None,
                                               "sale", T1),
        deal_id=deal_id, source="payment", source_record_ref="pay-1", observation_key="event:1",
        raw_state=None, signal="sale", observed_at=T1,
    )


def assessment(deal_id, status, supporting=(), *, review=False, supersedes=None, at=T2):
    ids = tuple(e.evidence_id for e in supporting)
    conf = None if status == "unknown" else "high"
    effective = T1 if status in ("won", "rejected") else None
    return OutcomeAssessment(
        assessment_id=derive_outcome_assessment_id(
            deal_id, status, ids, ids, conf, review, "rule", "p1", effective, at, supersedes
        ),
        deal_id=deal_id, status=status, supporting_evidence_ids=ids, eligible_evidence_ids=ids,
        confidence_level=conf, needs_human_review=review, decision_method="rule",
        policy_version="p1", effective_at=effective, decided_at=at,
        supersedes_assessment_id=supersedes,
    )


def appended(deal_id, status, *, review=False):
    evidence = [sale(deal_id)] if status == "won" else []
    a = assessment(deal_id, status, evidence, review=review)
    return append_outcome_assessment([], a, evidence=evidence, dispositions=[])


def assert_no_deal(state):
    assert state.deal_id is None
    assert state.current_outcome is None
    assert state.is_consumable is False


# --- match side: nothing but "matched" yields a deal -------------------------------------------


def test_1_no_match_decision():
    state = resolve_call_commercial_state(CALL_A, [], appended(DEAL_A, "won"))
    assert state.current_match.state == "no_decision"
    assert_no_deal(state)


@pytest.mark.parametrize("status", ["unmatched", "ambiguous", "manual_review", "rejected"])
def test_2_3_4_non_matched_decisions_yield_no_deal(status):
    state = resolve_call_commercial_state(CALL_A, [decision(status)], appended(DEAL_A, "won"))
    assert state.current_match.state == status
    assert_no_deal(state)


def test_2_explicit_unmatched_is_distinct_from_no_decision():
    unmatched = resolve_call_commercial_state(CALL_A, [decision("unmatched")], [])
    none = resolve_call_commercial_state(CALL_A, [], [])
    assert unmatched.current_match.state != none.current_match.state


def test_5_match_conflict_yields_no_deal():
    root = decision("matched", DEAL_A)
    fork_1 = decision("matched", DEAL_B, supersedes=root.match_decision_id, at=T2)
    fork_2 = decision("rejected", supersedes=root.match_decision_id, at=T3)
    state = resolve_call_commercial_state(CALL_A, [root, fork_1, fork_2], appended(DEAL_A, "won"))
    assert state.current_match.state == "conflict"
    assert_no_deal(state)


def test_11_matched_then_rejected_never_returns_old_deal_outcome():
    first = decision("matched", DEAL_A)
    second = decision("rejected", supersedes=first.match_decision_id, at=T2)
    state = resolve_call_commercial_state(CALL_A, [first, second], appended(DEAL_A, "won"))
    assert state.current_match.state == "rejected"
    assert_no_deal(state)


def test_12_corrected_match_uses_only_the_new_deal():
    first = decision("matched", DEAL_A)
    second = decision("matched", DEAL_B, supersedes=first.match_decision_id, at=T2)
    outcomes = appended(DEAL_A, "won") + appended(DEAL_B, "unknown")
    state = resolve_call_commercial_state(CALL_A, [first, second], outcomes)
    assert state.deal_id == DEAL_B
    assert state.current_outcome.deal_id == DEAL_B
    assert state.current_outcome.status == "unknown"


def test_14_candidate_rows_without_decision_yield_no_deal():
    candidate = CallDealMatch(
        call_deal_match_id=derive_call_deal_match_id(CALL_A, DEAL_A, "exact_external_id", T1),
        call_id=CALL_A, deal_id=DEAL_A, matching_method="exact_external_id", status="matched",
        confidence_level="high", evidence=[MatchEvidence(signal="external_id_exact", matched=True)],
        created_at=T1,
    )
    assert candidate.status == "matched"  # a candidate row, not a decision
    state = resolve_call_commercial_state(CALL_A, [], appended(DEAL_A, "won"))
    assert_no_deal(state)


# --- outcome side: passed through unchanged -----------------------------------------------------


def test_6_matched_deal_without_assessment_is_no_assessment():
    state = resolve_call_commercial_state(CALL_A, [decision("matched", DEAL_A)], [])
    assert state.deal_id == DEAL_A
    assert state.current_outcome.state == "no_assessment"
    assert state.current_outcome.status is None
    assert state.is_consumable is False


def test_7_matched_deal_with_available_won():
    state = resolve_call_commercial_state(
        CALL_A, [decision("matched", DEAL_A)], appended(DEAL_A, "won")
    )
    assert (state.current_outcome.state, state.current_outcome.status) == ("available", "won")
    assert state.is_consumable is True


def test_8_available_unknown_is_a_valid_consumable_outcome():
    state = resolve_call_commercial_state(
        CALL_A, [decision("matched", DEAL_A)], appended(DEAL_A, "unknown")
    )
    assert (state.current_outcome.state, state.current_outcome.status) == ("available", "unknown")
    assert state.is_consumable is True


def test_9_review_pending_is_preserved_and_not_consumable():
    state = resolve_call_commercial_state(
        CALL_A, [decision("matched", DEAL_A)], appended(DEAL_A, "unknown", review=True)
    )
    assert state.current_outcome.state == "review_pending"
    assert state.current_outcome.canonical is not None
    assert state.is_consumable is False


def test_10_outcome_history_conflict_stays_conflict():
    root = assessment(DEAL_A, "unknown", at=T1)
    fork_1 = assessment(DEAL_A, "unknown", review=True, supersedes=root.assessment_id, at=T2)
    fork_2 = assessment(DEAL_A, "unknown", supersedes=root.assessment_id, at=T3)
    state = resolve_call_commercial_state(
        CALL_A, [decision("matched", DEAL_A)], [root, fork_1, fork_2]
    )
    assert state.deal_id == DEAL_A
    assert state.current_outcome.state == "conflict"
    assert state.is_consumable is False


def test_13_legacy_deal_outcome_is_never_a_fallback():
    legacy = Deal(
        deal_id=DEAL_A, company_id="agrotalento-001", source="kommo", external_id="card-a",
        current_stage="negotiation", outcome="won", created_at=T1, closed_at=T2,
    )
    assert legacy.outcome == "won"
    state = resolve_call_commercial_state(CALL_A, [decision("matched", legacy.deal_id)], [])
    assert state.current_outcome.state == "no_assessment"
    assert state.current_outcome.status is None


# --- isolation --------------------------------------------------------------------------------


def test_mixed_calls_do_not_contaminate_each_other():
    decisions = [decision("matched", DEAL_A, call_id=CALL_A),
                 decision("rejected", call_id=CALL_B)]
    outcomes = appended(DEAL_A, "won")
    a = resolve_call_commercial_state(CALL_A, decisions, outcomes)
    b = resolve_call_commercial_state(CALL_B, decisions, outcomes)
    assert a.deal_id == DEAL_A and a.current_outcome.status == "won"
    assert_no_deal(b)


def test_mixed_deals_do_not_contaminate_each_other():
    decisions = [decision("matched", DEAL_A, call_id=CALL_A),
                 decision("matched", DEAL_B, call_id=CALL_B)]
    outcomes = appended(DEAL_A, "won") + appended(DEAL_B, "unknown", review=True)
    a = resolve_call_commercial_state(CALL_A, decisions, outcomes)
    b = resolve_call_commercial_state(CALL_B, decisions, outcomes)
    assert (a.current_outcome.deal_id, a.current_outcome.state) == (DEAL_A, "available")
    assert (b.current_outcome.deal_id, b.current_outcome.state) == (DEAL_B, "review_pending")


def test_other_deal_forked_history_does_not_affect_this_deal():
    root = assessment(DEAL_B, "unknown", at=T1)
    forks = [assessment(DEAL_B, "unknown", review=True, supersedes=root.assessment_id, at=T2),
             assessment(DEAL_B, "unknown", supersedes=root.assessment_id, at=T3)]
    state = resolve_call_commercial_state(
        CALL_A, [decision("matched", DEAL_A)], appended(DEAL_A, "won") + [root, *forks]
    )
    assert state.current_outcome.state == "available"


# --- result type invariants -------------------------------------------------------------------


def test_result_rejects_outcome_without_matched_deal():
    with pytest.raises(ValidationError, match="if and only if"):
        CallCommercialState(
            current_match=CurrentMatchResult(call_id=CALL_A, state="no_decision"),
            current_outcome=CurrentOutcome(deal_id=DEAL_A, state="no_assessment"),
        )


def test_result_rejects_outcome_of_another_deal():
    matched = CurrentMatchResult(call_id=CALL_A, state="matched", deal_id=DEAL_A,
                                 decision_id="mdc_x")
    with pytest.raises(ValidationError, match="belong to the deal"):
        CallCommercialState(
            current_match=matched,
            current_outcome=CurrentOutcome(deal_id=DEAL_B, state="no_assessment"),
        )


def test_result_requires_outcome_when_matched():
    matched = CurrentMatchResult(call_id=CALL_A, state="matched", deal_id=DEAL_A,
                                 decision_id="mdc_x")
    with pytest.raises(ValidationError, match="if and only if"):
        CallCommercialState(current_match=matched)
