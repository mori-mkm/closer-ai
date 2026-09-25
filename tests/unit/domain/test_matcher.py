"""ExactExternalIdMatcher: Call -> source record -> Deal Identity -> canonical Deal candidate.
No fallback to Deal.external_id; the matcher never decides identity nor the current match."""
from datetime import UTC, datetime

import pytest
from synthetic_calls import raw_call

from closer_ai.domain.commercial_state import resolve_call_commercial_state
from closer_ai.domain.deal import Deal, derive_deal_id
from closer_ai.domain.deal_identity import (
    DealIdentityDecision,
    derive_deal_identity_decision_id,
    derive_source_record_key,
    found_deal,
)
from closer_ai.domain.matching import (
    CallDealMatcher,
    ExactExternalIdMatcher,
    append_match_decision,
    decision_from_matcher_output,
    resolve_current_match,
)
from closer_ai.domain.outcome import (
    OutcomeAssessment,
    OutcomeEvidence,
    append_outcome_assessment,
    derive_outcome_assessment_id,
    derive_outcome_evidence_id,
)
from closer_ai.normalization.normalize import normalize_call

CO = "synthco-001"
CRM = "kommo"
T1 = datetime(2026, 1, 10, 12, 0, tzinfo=UTC)
T2 = datetime(2026, 1, 11, 12, 0, tzinfo=UTC)
MATCHER = ExactExternalIdMatcher(provider=CRM)


def call(source_id="card-a", **overrides):
    return normalize_call(raw_call(source_id=source_id, **overrides))


def deal(external_id, source=CRM, company_id=CO):
    return Deal(
        deal_id=derive_deal_id(company_id, source, external_id), company_id=company_id,
        source=source, external_id=external_id, current_stage="negotiation", outcome="open",
        created_at=T1,
    )


def key(record, provider=CRM, company_id=CO):
    return derive_source_record_key(company_id, provider, record)


def identity(record, status, deal_id=None, *, candidates=(), by="manual", supersedes=None,
             provider=CRM, at=T1):
    k = key(record, provider)
    return DealIdentityDecision(
        identity_decision_id=derive_deal_identity_decision_id(
            k, status, deal_id, candidates, by, supersedes, at
        ),
        company_id=CO, provider=provider, external_record_id=record, status=status,
        deal_id=deal_id, candidate_deal_ids=candidates, decided_by=by,
        supersedes_decision_id=supersedes, created_at=at,
    )


def founded(record, provider=CRM):
    d = deal(record, source=provider)
    _, history = found_deal(d, [], decided_by="automatic", decided_at=T1)
    return d, history


def only(results):
    assert len(results) == 1
    return results[0]


def test_implements_protocol():
    assert isinstance(MATCHER, CallDealMatcher)


def test_provider_is_required():
    with pytest.raises(ValueError):
        ExactExternalIdMatcher(provider=" ")


# --- 1, 2: linked identity yields the canonical Deal -------------------------------------------


def test_1_2_founded_record_yields_founded_deal_candidate():
    deal_a, history = founded("card-a")
    result = only(MATCHER.match(call("card-a"), [deal_a], history))
    assert (result.status, result.deal_id) == ("matched", deal_a.deal_id)
    evidence = result.evidence[0]
    assert evidence.signal == "external_id_exact" and evidence.matched
    assert key("card-a") in evidence.detail and history[0].identity_decision_id in evidence.detail


def test_8_second_record_linked_to_same_deal_yields_that_deal_not_a_new_one():
    deal_x, history_a = founded("card-a")
    link_b = identity("card-b", "linked", deal_x.deal_id)
    result = only(MATCHER.match(call("card-b"), [deal_x], history_a + [link_b]))
    assert (result.status, result.deal_id) == ("matched", deal_x.deal_id)


def test_9_record_linked_to_x_never_yields_y():
    deal_x, history_a = founded("card-a")
    deal_y, history_b = founded("card-b")
    result = only(MATCHER.match(call("card-a"), [deal_x, deal_y], history_a + history_b))
    assert result.deal_id == deal_x.deal_id


def test_11_human_identity_decision_is_respected():
    deal_x, _ = founded("card-x")
    deal_y = deal("card-a")  # a Deal whose external_id equals the call's source_id
    human = identity("card-a", "linked", deal_x.deal_id, by="manual")
    result = only(MATCHER.match(call("card-a"), [deal_x, deal_y], [human]))
    assert result.deal_id == deal_x.deal_id


# --- 3-7, 16: non-linked identity yields no candidate ------------------------------------------


X = derive_deal_id(CO, CRM, "card-x")
Y = derive_deal_id(CO, CRM, "card-y")


@pytest.mark.parametrize(
    "decisions, state",
    [
        ([], "no_decision"),
        ([identity("card-a", "unresolved")], "unresolved"),
        ([identity("card-a", "ambiguous", candidates=(X, Y))], "ambiguous"),
        ([identity("card-a", "not_a_deal")], "not_a_deal"),
    ],
)
def test_3_to_6_non_linked_identity_yields_unmatched(decisions, state):
    candidates = [deal("card-a"), deal("card-x"), deal("card-y")]
    result = only(MATCHER.match(call("card-a"), candidates, decisions))
    assert (result.status, result.deal_id) == ("unmatched", None)
    assert f"identity={state}" in result.evidence[0].detail
    assert result.evidence[0].matched is False


def test_7_16_identity_fork_yields_unmatched():
    root = identity("card-a", "unresolved")
    fork_x = identity("card-a", "linked", X, supersedes=root.identity_decision_id, at=T2)
    fork_y = identity("card-a", "linked", Y, supersedes=root.identity_decision_id,
                      at=datetime(2026, 1, 12, tzinfo=UTC))
    result = only(MATCHER.match(call("card-a"), [deal("card-x"), deal("card-y")],
                                [root, fork_x, fork_y]))
    assert result.status == "unmatched"
    assert "identity=conflict" in result.evidence[0].detail


def test_12_legacy_equal_external_id_without_identity_is_not_a_fallback():
    legacy = deal("card-a")  # legacy semantics would have matched this
    result = only(MATCHER.match(call("card-a"), [legacy], []))
    assert (result.status, result.deal_id) == ("unmatched", None)


def test_linked_deal_not_among_candidates_yields_unmatched():
    _, history = founded("card-a")
    result = only(MATCHER.match(call("card-a"), [], history))
    assert result.status == "unmatched"
    assert "not among candidates" in result.evidence[0].detail


def test_13_call_without_record_reference_yields_unmatched():
    blank = call("card-a").model_copy(update={"source_id": "  "})
    deal_a, history = founded("card-a")
    result = only(MATCHER.match(blank, [deal_a], history))
    assert result.status == "unmatched"


# --- 10, 14, 15: isolation --------------------------------------------------------------------


def test_10_same_record_id_in_other_provider_does_not_collide():
    pipedrive_deal, pipedrive_history = founded("card-a", provider="pipedrive")
    result = only(MATCHER.match(call("card-a"), [pipedrive_deal], pipedrive_history))
    assert result.status == "unmatched"  # the matcher is configured for kommo


def test_other_company_record_does_not_collide():
    other = deal("card-a", company_id="synthco-002")
    other_found = found_deal(other, [], decided_by="automatic", decided_at=T1)[1]
    result = only(MATCHER.match(call("card-a"), [other], other_found))
    assert result.status == "unmatched"


def test_14_mixed_calls_are_isolated():
    deal_a, history_a = founded("card-a")
    deal_b, history_b = founded("card-b")
    everything = history_a + history_b
    assert only(MATCHER.match(call("card-a"), [deal_a, deal_b], everything)).deal_id == deal_a.deal_id
    assert only(MATCHER.match(call("card-b"), [deal_a, deal_b], everything)).deal_id == deal_b.deal_id


def test_15_other_record_identity_history_does_not_contaminate():
    deal_a, history_a = founded("card-a")
    noise = [identity("card-z", "not_a_deal"),
             identity("card-z", "unresolved", by="automatic", at=T2)]
    result = only(MATCHER.match(call("card-a"), [deal_a], history_a + noise))
    assert result.deal_id == deal_a.deal_id


def test_duplicate_candidate_deals_do_not_produce_false_ambiguity():
    deal_a, history = founded("card-a")
    result = only(MATCHER.match(call("card-a"), [deal_a, deal_a], history))
    assert result.status == "matched"


# --- 17-20: downstream contracts unchanged ----------------------------------------------------


def test_17_18_matcher_output_is_a_candidate_until_decided():
    deal_a, history = founded("card-a")
    c = call("card-a")
    rows = MATCHER.match(c, [deal_a], history)
    assert resolve_current_match(c.call_id, []).state == "no_decision"  # candidate != decision
    first = decision_from_matcher_output(rows, supersedes_decision_id=None, created_at=T1)
    decisions = append_match_decision([], first)
    assert resolve_current_match(c.call_id, decisions).deal_id == deal_a.deal_id
    # a later non-match decision is authoritative; the historical match never leaks back
    later = decision_from_matcher_output(
        MATCHER.match(c, [deal_a], []), supersedes_decision_id=first.match_decision_id,
        created_at=T2,
    )
    decisions = append_match_decision(decisions, later)
    assert resolve_current_match(c.call_id, decisions).deal_id is None


def test_19_20_call_deal_outcome_slice_still_works_and_matcher_creates_no_outcome():
    deal_a, history = founded("card-a")
    c = call("card-a")
    rows = MATCHER.match(c, [deal_a], history)
    assert all(type(r).__name__ == "CallDealMatch" for r in rows)  # no outcome records
    decisions = append_match_decision(
        [], decision_from_matcher_output(rows, supersedes_decision_id=None, created_at=T1)
    )
    sale = OutcomeEvidence(
        evidence_id=derive_outcome_evidence_id(deal_a.deal_id, "payment", "p1", "e1", None,
                                               "sale", T1),
        deal_id=deal_a.deal_id, source="payment", source_record_ref="p1", observation_key="e1",
        signal="sale", observed_at=T1,
    )
    ids = (sale.evidence_id,)
    won = OutcomeAssessment(
        assessment_id=derive_outcome_assessment_id(
            deal_a.deal_id, "won", ids, ids, "high", False, "human", None, T1, T2, None
        ),
        deal_id=deal_a.deal_id, status="won", supporting_evidence_ids=ids,
        eligible_evidence_ids=ids, confidence_level="high", needs_human_review=False,
        decision_method="human", effective_at=T1, decided_at=T2,
    )
    assessments = append_outcome_assessment([], won, evidence=[sale], dispositions=[])
    state = resolve_call_commercial_state(c.call_id, decisions, assessments)
    assert (state.deal_id, state.current_outcome.status, state.is_consumable) == (
        deal_a.deal_id, "won", True,
    )
