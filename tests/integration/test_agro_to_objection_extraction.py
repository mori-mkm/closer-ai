"""Cross-module integration: Agro raw call -> Canonical Call -> ObjectionExtractor ->
ObjectionEvent.

This is the pipeline TD-14 broke silently: a `Call` produced by the Agro parser must carry a
correctly-resolved `role="lead"` participant for `RuleBasedObjectionExtractor` to detect
anything at all — a fully valid `Call` with an unresolved lead produces zero
`ObjectionEvent`s with no error. Uses only real contracts end to end (no mocked `Call`/
`ObjectionEvent`); the negative tests assert that "no objection" and "lead role unresolved"
stay distinguishable via `Call.quality_flags`, never conflated.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from closer_ai.ai.objection_extraction import RuleBasedObjectionExtractor
from closer_ai.ingestion.agro.parser import normalize_agro_call

COMPANY_ID = "agrotalento-001"

_extractor = RuleBasedObjectionExtractor()


def _two_party_raw_call(**overrides: Any) -> dict[str, Any]:
    raw: dict[str, Any] = {
        "meeting_id": "zoom-integration-0001",
        "occurred_at": datetime(2026, 2, 3, 13, 0, tzinfo=UTC),
        "duration_seconds": 60.0,
        "closer": "Joao",
        "participants": [
            {"label": "Joao", "role": "closer"},
            {"label": "Maria", "role": "lead"},
        ],
        "transcript": [
            {
                "speaker": "Joao",
                "start": 0.0,
                "end": 5.0,
                "text": "Como você está pensando em seguir?",
            },
            {"speaker": "Maria", "start": 5.5, "end": 10.0, "text": "Está muito caro para mim."},
        ],
    }
    raw.update(overrides)
    return raw


# --- positive path: explicit lead role, full pipeline produces a grounded ObjectionEvent ---


def test_agro_call_with_explicit_lead_role_produces_objection_event_end_to_end():
    call, _ = normalize_agro_call(_two_party_raw_call(), company_id=COMPANY_ID)

    lead = next(p for p in call.participants if p.role == "lead")
    assert lead.name == "Maria"
    assert "unresolved_lead" not in call.quality_flags

    events = _extractor.extract(call)
    assert len(events) == 1
    event = events[0]
    assert event.category == "price"
    assert event.call_id == call.call_id

    segment = next(s for s in call.segments if s.segment_id == event.segment_id)
    assert segment.speaker_id == lead.id
    assert segment.text == "Está muito caro para mim."


def test_agro_call_with_explicit_lead_role_is_deterministic_end_to_end():
    raw = _two_party_raw_call()
    call_a, _ = normalize_agro_call(raw, company_id=COMPANY_ID)
    call_b, _ = normalize_agro_call(raw, company_id=COMPANY_ID)
    events_a = _extractor.extract(call_a)
    events_b = _extractor.extract(call_b)
    assert [e.objection_id for e in events_a] == [e.objection_id for e in events_b]
    assert [e.objection_id for e in events_a] != []


# --- negative path (TD-14): unresolved lead must never be confused with "no objection" ---


def test_agro_call_without_explicit_lead_role_yields_no_events_but_flags_unresolved_lead():
    raw = _two_party_raw_call(
        participants=[{"label": "Joao"}, {"label": "Maria"}],  # no explicit role
    )
    call, _ = normalize_agro_call(raw, company_id=COMPANY_ID)

    maria = next(p for p in call.participants if p.name == "Maria")
    assert maria.role == "unknown"  # never silently promoted to lead

    events = _extractor.extract(call)
    assert events == []
    assert "unresolved_lead" in call.quality_flags


def test_agro_call_multi_party_ambiguous_does_not_fabricate_two_leads():
    """closer + 2 unresolved participants must never both become role='lead' just because
    there are exactly two non-closer participants (multi-party safety, Phase 9)."""
    raw = _two_party_raw_call(
        participants=[{"label": "Joao"}, {"label": "Maria"}, {"label": "Pedro"}],
        transcript=[
            {"speaker": "Joao", "start": 0.0, "end": 5.0, "text": "Vamos começar."},
            {"speaker": "Maria", "start": 5.0, "end": 10.0, "text": "Está muito caro."},
            {"speaker": "Pedro", "start": 10.0, "end": 15.0, "text": "Não tenho orçamento."},
        ],
    )
    call, _ = normalize_agro_call(raw, company_id=COMPANY_ID)
    assert not any(p.role == "lead" for p in call.participants)

    events = _extractor.extract(call)
    assert events == []
    assert "unresolved_lead" in call.quality_flags
