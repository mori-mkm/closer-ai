from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from closer_ai.domain.deal import derive_deal_id
from closer_ai.domain.matching import (
    CallDealMatch,
    MatchEvidence,
    derive_call_deal_match_id,
)

_CREATED_AT = datetime(2026, 2, 1, 9, 0, tzinfo=UTC)
_DEAL_ID = derive_deal_id("agrotalento-001", "kommo", "deal-1")
_OTHER_DEAL_ID = derive_deal_id("agrotalento-001", "kommo", "deal-2")


def _evidence(**overrides):
    return MatchEvidence(
        signal=overrides.pop("signal", "email_exact"),
        matched=overrides.pop("matched", True),
        **overrides,
    )


def _match(**overrides):
    call_id = overrides.pop("call_id", "call_1")
    deal_id = overrides.pop("deal_id", _DEAL_ID)
    matching_method = overrides.pop("matching_method", "exact_email")
    created_at = overrides.pop("created_at", _CREATED_AT)
    status = overrides.pop("status", "matched")
    confidence_level = overrides.pop("confidence_level", "high")
    evidence = overrides.pop("evidence", [_evidence()] if status != "unmatched" else [])
    match_id = overrides.pop(
        "call_deal_match_id",
        derive_call_deal_match_id(call_id, deal_id, matching_method, created_at),
    )
    return CallDealMatch(
        call_deal_match_id=match_id,
        call_id=call_id,
        deal_id=deal_id,
        matching_method=matching_method,
        status=status,
        confidence_level=confidence_level,
        evidence=evidence,
        created_at=created_at,
        **overrides,
    )


# --- MatchEvidence ---


def test_evidence_score_range_enforced():
    with pytest.raises(ValidationError):
        _evidence(score=1.5)
    with pytest.raises(ValidationError):
        _evidence(score=-0.1)


def test_evidence_never_needs_raw_pii_field():
    # structural guard: MatchEvidence has no field meant to hold a raw compared value
    assert set(MatchEvidence.model_fields) == {"signal", "matched", "score", "detail"}


# --- id determinism ---


def test_call_deal_match_id_matches_derivation():
    match = _match()
    assert match.call_deal_match_id == derive_call_deal_match_id(
        "call_1", _DEAL_ID, "exact_email", _CREATED_AT
    )


def test_call_deal_match_is_deterministic():
    assert _match() == _match()


def test_call_deal_match_different_created_at_is_a_new_attempt():
    from datetime import timedelta

    a = _match(created_at=_CREATED_AT)
    b_created_at = _CREATED_AT + timedelta(days=1)
    b = _match(
        created_at=b_created_at,
        call_deal_match_id=derive_call_deal_match_id(
            "call_1", _DEAL_ID, "exact_email", b_created_at
        ),
    )
    assert a.call_deal_match_id != b.call_deal_match_id


# --- deterministic methods vs heuristic confidence (invariant: auditable confidence) ---


@pytest.mark.parametrize(
    "method", ["exact_external_id", "exact_email", "exact_phone", "manual"]
)
def test_deterministic_methods_require_high_confidence_and_no_score(method):
    match = _match(matching_method=method, confidence_level="high", confidence_score=None)
    assert match.confidence_score is None


@pytest.mark.parametrize(
    "method", ["exact_external_id", "exact_email", "exact_phone", "manual"]
)
def test_deterministic_methods_reject_non_high_confidence(method):
    with pytest.raises(ValidationError):
        _match(matching_method=method, confidence_level="medium")


@pytest.mark.parametrize(
    "method", ["exact_external_id", "exact_email", "exact_phone", "manual"]
)
def test_deterministic_methods_reject_a_confidence_score(method):
    with pytest.raises(ValidationError):
        _match(matching_method=method, confidence_level="high", confidence_score=0.9)


def test_heuristic_method_carries_graded_score():
    match = _match(
        matching_method="name_and_datetime",
        confidence_level="medium",
        confidence_score=0.62,
        status="manual_review",
    )
    assert match.confidence_score == 0.62


def test_heuristic_confidence_score_range_enforced():
    with pytest.raises(ValidationError):
        _match(
            matching_method="name_only",
            confidence_level="low",
            confidence_score=1.5,
            status="manual_review",
        )


# --- status semantics ---


def test_unmatched_requires_deal_id_none():
    match = _match(
        status="unmatched",
        deal_id=None,
        evidence=[],
        matching_method="name_only",
        confidence_level="low",
    )
    assert match.deal_id is None


def test_unmatched_with_deal_id_rejected():
    with pytest.raises(ValidationError):
        _match(
            status="unmatched",
            deal_id=_DEAL_ID,
            matching_method="name_only",
            confidence_level="low",
        )


def test_non_unmatched_status_requires_deal_id():
    with pytest.raises(ValidationError):
        _match(
            status="rejected",
            deal_id=None,
            matching_method="name_only",
            confidence_level="low",
        )


def test_non_unmatched_status_requires_evidence():
    with pytest.raises(ValidationError):
        _match(
            status="rejected",
            evidence=[],
            matching_method="name_only",
            confidence_level="low",
        )


def test_rejected_candidate_is_representable():
    match = _match(
        status="rejected",
        matching_method="name_only",
        confidence_level="low",
        evidence=[_evidence(signal="name_similarity", matched=False, score=0.2)],
    )
    assert match.status == "rejected"


def test_manual_match_is_representable():
    match = _match(
        matching_method="manual",
        status="matched",
        confidence_level="high",
        evidence=[_evidence(signal="human_decision", matched=True, detail="reviewed by ops")],
    )
    assert match.matching_method == "manual"


# --- ambiguity: the critical invariant ---


def test_ambiguous_candidates_are_separate_rows_not_a_silent_winner():
    created_at = _CREATED_AT
    a = _match(
        call_id="call_A",
        deal_id=_DEAL_ID,
        matching_method="name_and_datetime",
        status="ambiguous",
        confidence_level="medium",
        confidence_score=0.65,
        evidence=[_evidence(signal="name_similarity", score=0.65)],
        created_at=created_at,
        call_deal_match_id=derive_call_deal_match_id(
            "call_A", _DEAL_ID, "name_and_datetime", created_at
        ),
    )
    b = _match(
        call_id="call_A",
        deal_id=_OTHER_DEAL_ID,
        matching_method="name_and_datetime",
        status="ambiguous",
        confidence_level="medium",
        confidence_score=0.62,
        evidence=[_evidence(signal="name_similarity", score=0.62)],
        created_at=created_at,
        call_deal_match_id=derive_call_deal_match_id(
            "call_A", _OTHER_DEAL_ID, "name_and_datetime", created_at
        ),
    )
    assert a.call_id == b.call_id == "call_A"
    assert a.deal_id != b.deal_id
    assert a.status == b.status == "ambiguous"
    assert a.call_deal_match_id != b.call_deal_match_id  # both preserved, no row discarded


def test_call_with_no_deal_association_is_representable_without_any_match_row():
    # a Call simply has no CallDealMatch at all — nothing in normalization.Call references
    # matching, so "call exists without a deal" requires no special-case object
    from closer_ai.normalization.models import Call

    assert "deal_id" not in Call.model_fields
    assert "matched" not in Call.model_fields


def test_deal_can_have_multiple_matched_calls():
    created_at = _CREATED_AT
    first = _match(
        call_id="call_1",
        deal_id=_DEAL_ID,
        created_at=created_at,
        call_deal_match_id=derive_call_deal_match_id(
            "call_1", _DEAL_ID, "exact_email", created_at
        ),
    )
    second = _match(
        call_id="call_2",
        deal_id=_DEAL_ID,
        created_at=created_at,
        call_deal_match_id=derive_call_deal_match_id(
            "call_2", _DEAL_ID, "exact_email", created_at
        ),
    )
    assert first.deal_id == second.deal_id == _DEAL_ID
    assert first.call_id != second.call_id
    assert first.call_deal_match_id != second.call_deal_match_id


def test_call_deal_match_frozen():
    match = _match()
    with pytest.raises(ValidationError):
        match.status = "rejected"  # type: ignore[misc]


def test_call_deal_match_rejects_naive_created_at():
    with pytest.raises(ValidationError):
        _match(created_at=datetime(2026, 2, 1, 9, 0))  # noqa: DTZ001 - naive on purpose
