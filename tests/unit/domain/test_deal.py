from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from closer_ai.domain.deal import Deal, StageEvent, derive_deal_id, derive_stage_event_id
from closer_ai.normalization.models import Call

_CREATED_AT = datetime(2026, 1, 10, 12, 0, tzinfo=UTC)


def _deal(**overrides):
    company_id = overrides.pop("company_id", "agrotalento-001")
    source = overrides.pop("source", "kommo")
    external_id = overrides.pop("external_id", "deal-1")
    deal_id = overrides.pop("deal_id", derive_deal_id(company_id, source, external_id))
    current_stage = overrides.pop("current_stage", "qualification")
    outcome = overrides.pop("outcome", "open")
    created_at = overrides.pop("created_at", _CREATED_AT)
    return Deal(
        deal_id=deal_id,
        company_id=company_id,
        source=source,
        external_id=external_id,
        current_stage=current_stage,
        outcome=outcome,
        created_at=created_at,
        **overrides,
    )


def _stage_event(**overrides):
    deal_id = overrides.pop("deal_id", derive_deal_id("agrotalento-001", "kommo", "deal-1"))
    stage = overrides.pop("stage", "qualification")
    occurred_at = overrides.pop("occurred_at", _CREATED_AT)
    source = overrides.pop("source", "kommo")
    stage_event_id = overrides.pop(
        "stage_event_id", derive_stage_event_id(deal_id, stage, occurred_at, source)
    )
    return StageEvent(
        stage_event_id=stage_event_id,
        deal_id=deal_id,
        stage=stage,
        occurred_at=occurred_at,
        source=source,
        **overrides,
    )


# --- basic validity / ids ---


def test_deal_minimal_valid():
    deal = _deal()
    assert deal.outcome == "open"
    assert deal.closed_at is None


def test_deal_id_matches_derivation():
    deal = _deal()
    assert deal.deal_id == derive_deal_id("agrotalento-001", "kommo", "deal-1")


def test_deal_is_deterministic():
    assert _deal() == _deal()


def test_deal_metadata_and_non_identity_fields_do_not_affect_id():
    a = _deal(owner_id="closer-1", pipeline_id="pipe-1", metadata={"x": 1})
    b = _deal(owner_id="closer-2", pipeline_id="pipe-2", metadata={"x": 2})
    assert a.deal_id == b.deal_id


def test_deal_frozen():
    deal = _deal()
    with pytest.raises(ValidationError):
        deal.current_stage = "proposal"  # type: ignore[misc]


# --- outcome semantics: invariant 5, 6, 11 ---


def test_deal_open_does_not_require_closed_at():
    deal = _deal(outcome="open")
    assert deal.closed_at is None


def test_deal_unknown_does_not_require_closed_at():
    deal = _deal(outcome="unknown")
    assert deal.closed_at is None


@pytest.mark.parametrize("outcome", ["won", "lost"])
def test_deal_terminal_outcome_requires_closed_at(outcome):
    with pytest.raises(ValidationError):
        _deal(outcome=outcome, closed_at=None)


@pytest.mark.parametrize("outcome", ["won", "lost"])
def test_deal_terminal_outcome_with_closed_at_is_valid(outcome):
    deal = _deal(outcome=outcome, closed_at=_CREATED_AT + timedelta(days=5))
    assert deal.outcome == outcome


@pytest.mark.parametrize("outcome", ["open", "unknown"])
def test_deal_non_terminal_outcome_rejects_closed_at(outcome):
    with pytest.raises(ValidationError):
        _deal(outcome=outcome, closed_at=_CREATED_AT + timedelta(days=1))


def test_deal_closed_at_before_created_at_rejected():
    with pytest.raises(ValidationError):
        _deal(outcome="won", closed_at=_CREATED_AT - timedelta(days=1))


def test_deal_open_is_not_lost_by_default():
    # regression guard for the exact bug the task warns about: OPEN must never be
    # silently treated as LOST just because closed_at/value are unset
    deal = _deal(outcome="open")
    assert deal.outcome != "lost"
    assert deal.outcome != "unknown"


def test_deal_outcome_has_no_default_value():
    with pytest.raises(ValidationError):
        Deal(
            deal_id=derive_deal_id("agrotalento-001", "kommo", "deal-1"),
            company_id="agrotalento-001",
            source="kommo",
            external_id="deal-1",
            current_stage="qualification",
            created_at=_CREATED_AT,
        )  # type: ignore[call-arg]


def test_deal_value_requires_currency():
    with pytest.raises(ValidationError):
        _deal(value=1000.0, currency=None)


def test_deal_value_must_not_be_negative():
    with pytest.raises(ValidationError):
        _deal(value=-1.0, currency="BRL")


def test_deal_value_with_currency_is_valid():
    deal = _deal(value=1000.0, currency="BRL")
    assert deal.value == 1000.0


# --- Call never has commercial outcome (invariant 11, cross-module regression guard) ---


def test_call_has_no_outcome_field():
    assert "outcome" not in Call.model_fields
    assert "closed_at" not in Call.model_fields
    assert "value" not in Call.model_fields


# --- no nesting / no circular objects (invariant 12) ---


def test_deal_has_no_call_ids_field():
    assert "call_ids" not in Deal.model_fields


def test_deal_fields_contain_no_nested_call_object():
    for field in Deal.model_fields.values():
        assert field.annotation is not Call


# --- StageEvent: invariants 7, 8 ---


def test_stage_event_id_matches_derivation():
    event = _stage_event()
    assert event.stage_event_id == derive_stage_event_id(event.deal_id, "qualification", _CREATED_AT, "kommo")


def test_stage_event_frozen():
    event = _stage_event()
    with pytest.raises(ValidationError):
        event.stage = "proposal"  # type: ignore[misc]


def test_stage_events_share_the_same_deal_id():
    deal_id = derive_deal_id("agrotalento-001", "kommo", "deal-1")
    history = [
        _stage_event(deal_id=deal_id, stage="created", occurred_at=_CREATED_AT),
        _stage_event(deal_id=deal_id, stage="qualification", occurred_at=_CREATED_AT + timedelta(days=1)),
        _stage_event(deal_id=deal_id, stage="proposal", occurred_at=_CREATED_AT + timedelta(days=3)),
    ]
    assert {event.deal_id for event in history} == {deal_id}


def test_stage_history_preserves_bounce_back_as_distinct_events():
    # re-entering the same stage later must not collapse into the same event
    deal_id = derive_deal_id("agrotalento-001", "kommo", "deal-1")
    first = _stage_event(deal_id=deal_id, stage="negotiation", occurred_at=_CREATED_AT)
    later = _stage_event(
        deal_id=deal_id, stage="negotiation", occurred_at=_CREATED_AT + timedelta(days=10)
    )
    assert first.stage_event_id != later.stage_event_id


def test_stage_event_exact_redelivery_is_idempotent():
    deal_id = derive_deal_id("agrotalento-001", "kommo", "deal-1")
    a = _stage_event(deal_id=deal_id, stage="proposal", occurred_at=_CREATED_AT)
    b = _stage_event(deal_id=deal_id, stage="proposal", occurred_at=_CREATED_AT)
    assert a.stage_event_id == b.stage_event_id


def test_stage_event_id_stable_across_equivalent_utc_offsets():
    # same instant, different offset representation, must hash identically
    from datetime import timezone

    deal_id = derive_deal_id("agrotalento-001", "kommo", "deal-1")
    utc_dt = datetime(2026, 1, 10, 15, 0, tzinfo=UTC)
    minus3_dt = utc_dt.astimezone(timezone(timedelta(hours=-3)))  # same instant, different offset
    id_utc = derive_stage_event_id(deal_id, "proposal", utc_dt, "kommo")
    id_minus3 = derive_stage_event_id(deal_id, "proposal", minus3_dt, "kommo")
    assert id_utc == id_minus3


def test_stage_event_rejects_naive_occurred_at():
    with pytest.raises(ValidationError):
        _stage_event(occurred_at=datetime(2026, 1, 10, 12, 0))  # noqa: DTZ001 - naive on purpose
