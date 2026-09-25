"""DEP-1: authoritative current Call<->Deal match. See docs/domain/CURRENT_MATCH_RESOLVER.md."""
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from closer_ai.domain.deal import derive_deal_id
from closer_ai.domain.matching import (
    CallDealMatch,
    CurrentMatchResult,
    MatchDecision,
    MatchDecisionConflict,
    MatchEvidence,
    append_match_decision,
    decision_from_matcher_output,
    derive_call_deal_match_id,
    derive_match_decision_id,
    resolve_current_match,
)

CALL = "call_1"
DEAL_A = derive_deal_id("agrotalento-001", "kommo", "deal-a")
DEAL_B = derive_deal_id("agrotalento-001", "kommo", "deal-b")
T10 = datetime(2026, 3, 1, 10, 0, tzinfo=UTC)
T11 = datetime(2026, 3, 1, 11, 0, tzinfo=UTC)
T12 = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)


def _row(deal_id, status, created_at=T10, call_id=CALL):
    return CallDealMatch(
        call_deal_match_id=derive_call_deal_match_id(
            call_id, deal_id, "exact_external_id", created_at
        ),
        call_id=call_id,
        deal_id=deal_id,
        matching_method="exact_external_id",
        status=status,
        confidence_level="high",
        evidence=[] if status == "unmatched" else [MatchEvidence(signal="external_id_exact", matched=True)],
        created_at=created_at,
    )


def _decision(status, deal_id=None, *, supersedes=None, created_at=T10, decided_by="automatic",
              match_ids=("cdm_x",), call_id=CALL):
    return MatchDecision(
        match_decision_id=derive_match_decision_id(
            call_id, status, deal_id, match_ids, decided_by, supersedes, created_at
        ),
        call_id=call_id,
        status=status,
        deal_id=deal_id,
        match_ids=match_ids,
        decided_by=decided_by,
        supersedes_decision_id=supersedes,
        created_at=created_at,
    )


def _history(*decisions):
    history = []
    for d in decisions:
        history = append_match_decision(history, d)
    return history


# --- Scenarios A–I ------------------------------------------------------------------------


def test_a_single_matched_decision_names_the_deal():
    d1 = _decision("matched", DEAL_A)
    result = resolve_current_match(CALL, _history(d1))
    assert result == CurrentMatchResult(
        call_id=CALL, state="matched", deal_id=DEAL_A, decision_id=d1.match_decision_id
    )


def test_b_matched_then_rejected_has_no_canonical_deal():
    d1 = _decision("matched", DEAL_A)
    d2 = _decision("rejected", supersedes=d1.match_decision_id, created_at=T11)
    result = resolve_current_match(CALL, _history(d1, d2))
    assert result.state == "rejected"
    assert result.deal_id is None


def test_c_matched_then_ambiguous_has_no_canonical_deal():
    d1 = _decision("matched", DEAL_A)
    d2 = _decision("ambiguous", supersedes=d1.match_decision_id, created_at=T11,
                   match_ids=("cdm_a", "cdm_b"))
    result = resolve_current_match(CALL, _history(d1, d2))
    assert (result.state, result.deal_id) == ("ambiguous", None)


def test_d_explicit_correction_to_another_deal():
    d1 = _decision("matched", DEAL_A)
    d2 = _decision("matched", DEAL_B, supersedes=d1.match_decision_id, created_at=T11)
    assert resolve_current_match(CALL, _history(d1, d2)).deal_id == DEAL_B


def test_e_identical_redelivery_is_idempotent():
    d1 = _decision("matched", DEAL_A)
    history = _history(d1)
    assert append_match_decision(history, d1) == history


def test_e_rerun_with_same_result_creates_no_new_logical_decision():
    d1 = _decision("matched", DEAL_A)
    rerun = _decision("matched", DEAL_A, supersedes=d1.match_decision_id, created_at=T11,
                      match_ids=("cdm_rerun",))
    history = _history(d1)
    assert append_match_decision(history, rerun) == history


def test_f_stale_concurrent_writer_is_rejected():
    d1 = _decision("matched", DEAL_A)
    first = _decision("rejected", supersedes=d1.match_decision_id, created_at=T11)
    second = _decision("matched", DEAL_B, supersedes=d1.match_decision_id, created_at=T11)
    history = _history(d1, first)
    with pytest.raises(MatchDecisionConflict, match="stale write"):
        append_match_decision(history, second)
    assert resolve_current_match(CALL, history).state == "rejected"


def test_g_equal_created_at_does_not_decide_authority():
    d1 = _decision("matched", DEAL_A, created_at=T10)
    d2 = _decision("rejected", supersedes=d1.match_decision_id, created_at=T10)
    history = _history(d1, d2)
    # order of the input list is irrelevant; the chain decides
    assert resolve_current_match(CALL, list(reversed(history))).state == "rejected"


def test_g_older_created_at_on_newer_decision_still_wins_by_chain():
    d1 = _decision("matched", DEAL_A, created_at=T12)
    d2 = _decision("rejected", supersedes=d1.match_decision_id, created_at=T10)
    assert resolve_current_match(CALL, _history(d1, d2)).state == "rejected"


def test_h_forked_history_is_conflict_never_a_winner():
    d1 = _decision("matched", DEAL_A)
    b = _decision("matched", DEAL_B, supersedes=d1.match_decision_id, created_at=T11)
    c = _decision("rejected", supersedes=d1.match_decision_id, created_at=T12)
    result = resolve_current_match(CALL, [d1, b, c])
    assert (result.state, result.deal_id, result.decision_id) == ("conflict", None, None)


def test_h_cannot_append_onto_forked_history():
    d1 = _decision("matched", DEAL_A)
    b = _decision("matched", DEAL_B, supersedes=d1.match_decision_id, created_at=T11)
    c = _decision("rejected", supersedes=d1.match_decision_id, created_at=T12)
    fix = _decision("matched", DEAL_A, supersedes=b.match_decision_id, created_at=T12,
                    decided_by="manual", match_ids=())
    with pytest.raises(MatchDecisionConflict, match="linear"):
        append_match_decision([d1, b, c], fix)


def test_i_no_history_is_no_decision_not_unmatched():
    assert resolve_current_match(CALL, []) == CurrentMatchResult(call_id=CALL, state="no_decision")


def test_i_authoritative_unmatched_is_distinct_from_no_decision():
    d1 = decision_from_matcher_output([_row(None, "unmatched")], supersedes_decision_id=None,
                                      created_at=T10)
    result = resolve_current_match(CALL, _history(d1))
    assert (result.state, result.deal_id) == ("unmatched", None)
    assert result.decision_id == d1.match_decision_id


# --- Invariants ----------------------------------------------------------------------------


def test_historical_matched_never_leaks_through_newer_non_match():
    d1 = _decision("matched", DEAL_A)
    d2 = _decision("manual_review", supersedes=d1.match_decision_id, created_at=T11)
    d3 = _decision("unmatched", supersedes=d2.match_decision_id, created_at=T12)
    for state_history in (_history(d1, d2), _history(d1, d2, d3)):
        assert resolve_current_match(CALL, state_history).deal_id is None


def test_supersession_across_calls_fails():
    other = _decision("matched", DEAL_A, call_id="call_2")
    mine = _decision("rejected", supersedes=other.match_decision_id)
    with pytest.raises(MatchDecisionConflict, match="stale write"):
        append_match_decision([], mine)
    with pytest.raises(ValueError, match="belongs to call"):
        resolve_current_match(CALL, [other])
    # a decision pointing at a head that is not in this call's history is a broken chain
    assert resolve_current_match(CALL, [mine]).state == "conflict"


def test_matched_decision_without_deal_is_invalid():
    with pytest.raises(ValidationError, match="exactly one deal_id"):
        _decision("matched", None)


@pytest.mark.parametrize("status", ["ambiguous", "rejected", "unmatched", "manual_review"])
def test_non_matched_decision_cannot_carry_a_deal(status):
    with pytest.raises(ValidationError, match="deal_id must be None"):
        _decision(status, DEAL_A)


def test_same_id_different_payload_is_hard_error():
    d1 = _decision("matched", DEAL_A)
    tampered = d1.model_copy(update={"deal_id": DEAL_B})  # bypasses validation on purpose
    with pytest.raises(ValueError, match="different payload"):
        append_match_decision(_history(d1), tampered)
    with pytest.raises(ValueError, match="different payload"):
        resolve_current_match(CALL, [d1, tampered])


def test_decision_id_is_validated():
    with pytest.raises(ValidationError, match="match_decision_id"):
        MatchDecision(
            match_decision_id="mdc_forged", call_id=CALL, status="rejected",
            match_ids=("cdm_x",), decided_by="automatic", created_at=T10,
        )


def test_automatic_decision_must_cite_candidate_rows():
    with pytest.raises(ValidationError, match="cite"):
        _decision("rejected", match_ids=())


def test_dangling_supersession_is_conflict():
    # corrupted/legacy data: every decision supersedes an id that is not in the set
    x = _decision("matched", DEAL_A, supersedes="mdc_ghost_1")
    y = _decision("rejected", supersedes="mdc_ghost_2", created_at=T11)
    assert resolve_current_match(CALL, [x, y]).state == "conflict"


def test_current_match_result_invariants():
    with pytest.raises(ValidationError):
        CurrentMatchResult(call_id=CALL, state="ambiguous", deal_id=DEAL_A, decision_id="mdc_x")
    with pytest.raises(ValidationError):
        CurrentMatchResult(call_id=CALL, state="matched", decision_id="mdc_x")
    with pytest.raises(ValidationError):
        CurrentMatchResult(call_id=CALL, state="conflict", decision_id="mdc_x")


# --- Manual authority ----------------------------------------------------------------------


def test_human_resolves_ambiguity():
    auto = _decision("ambiguous", match_ids=("cdm_a", "cdm_b"))
    human = _decision("matched", DEAL_A, supersedes=auto.match_decision_id, created_at=T11,
                      decided_by="manual", match_ids=("cdm_a",))
    result = resolve_current_match(CALL, _history(auto, human))
    assert (result.state, result.deal_id) == ("matched", DEAL_A)


def test_human_rejection_is_not_overridden_by_later_automatic_run():
    auto = _decision("matched", DEAL_A)
    human = _decision("rejected", supersedes=auto.match_decision_id, created_at=T11,
                      decided_by="manual", match_ids=())
    history = _history(auto, human)
    rerun = _decision("matched", DEAL_A, supersedes=human.match_decision_id, created_at=T12)
    with pytest.raises(MatchDecisionConflict, match="manual"):
        append_match_decision(history, rerun)
    assert resolve_current_match(CALL, history).state == "rejected"


def test_manual_decision_can_be_replaced_only_by_another_manual_decision():
    human = _decision("rejected", decided_by="manual", match_ids=())
    human2 = _decision("matched", DEAL_B, supersedes=human.match_decision_id, created_at=T11,
                       decided_by="manual", match_ids=())
    assert resolve_current_match(CALL, _history(human, human2)).deal_id == DEAL_B


def test_manual_confirmation_of_same_result_upgrades_authority():
    auto = _decision("matched", DEAL_A)
    confirm = _decision("matched", DEAL_A, supersedes=auto.match_decision_id, created_at=T11,
                        decided_by="manual", match_ids=())
    history = _history(auto, confirm)
    assert history[-1] == confirm
    rerun = _decision("rejected", supersedes=confirm.match_decision_id, created_at=T12)
    with pytest.raises(MatchDecisionConflict, match="manual"):
        append_match_decision(history, rerun)


def test_history_with_automatic_over_manual_written_elsewhere_is_conflict():
    human = _decision("rejected", decided_by="manual", match_ids=())
    auto = _decision("matched", DEAL_A, supersedes=human.match_decision_id, created_at=T11)
    # bypasses append_match_decision, e.g. a buggy future write path
    result = resolve_current_match(CALL, [human, auto])
    assert (result.state, result.deal_id) == ("conflict", None)


# --- Candidate -> decision -----------------------------------------------------------------


def test_ambiguous_matcher_batch_never_becomes_a_canonical_deal():
    rows = [_row(DEAL_A, "ambiguous"), _row(DEAL_B, "ambiguous")]
    d = decision_from_matcher_output(rows, supersedes_decision_id=None, created_at=T10)
    assert resolve_current_match(CALL, _history(d)).deal_id is None


def test_matcher_batch_with_two_matched_rows_is_refused():
    rows = [_row(DEAL_A, "matched"), _row(DEAL_B, "matched")]
    with pytest.raises(ValueError, match="ambiguity"):
        decision_from_matcher_output(rows, supersedes_decision_id=None, created_at=T10)


def test_matcher_batch_with_mixed_statuses_is_refused():
    rows = [_row(DEAL_A, "matched"), _row(DEAL_B, "rejected")]
    with pytest.raises(ValueError, match="one status"):
        decision_from_matcher_output(rows, supersedes_decision_id=None, created_at=T10)


def test_matcher_batch_with_repeated_row_is_refused():
    row = _row(DEAL_A, "ambiguous")
    with pytest.raises(ValueError, match="repeat"):
        decision_from_matcher_output([row, row], supersedes_decision_id=None, created_at=T10)


# --- Legacy --------------------------------------------------------------------------------


def test_legacy_matched_rows_without_decisions_are_not_current():
    legacy_rows = [_row(DEAL_A, "matched", T10), _row(DEAL_A, "matched", T11)]
    assert legacy_rows  # rows exist, but they are candidates/attempts, not decisions
    assert resolve_current_match(CALL, []).state == "no_decision"
