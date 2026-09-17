"""Adversarial tests for `RuleBasedObjectionExtractor`. Cases mirror the Evaluator's
design-phase report (see docs/agents/tasks/objection-event-v0.md): false-positive traps get
priority over recall gaps, since a v0 meant to gate future CRM/Deal linkage should never
fabricate an objection.
"""
from __future__ import annotations

from synthetic_objection_calls import (
    call_ambiguous_phrasing_not_detected,
    call_closer_only_objection_like_language,
    call_minimal_valid,
    call_multi_objection_different_categories,
    call_no_objection,
    call_objection_split_across_segments,
    call_same_category_repeated_different_segments,
    call_same_category_twice_in_one_segment,
    call_single_objection,
)

from closer_ai.ai.objection_extraction import RuleBasedObjectionExtractor
from closer_ai.domain.objection import derive_objection_id

_extractor = RuleBasedObjectionExtractor()


def test_no_objection_returns_empty_list():
    """Highest priority: must not fabricate an objection when there isn't one."""
    call = call_no_objection()
    assert _extractor.extract(call) == []


def test_single_objection_detected():
    call = call_single_objection()
    events = _extractor.extract(call)
    assert len(events) == 1
    event = events[0]
    assert event.category == "price"
    assert event.call_id == call.call_id
    assert event.segment_id == call.segments[1].segment_id


def test_multi_objection_different_categories_detected():
    call = call_multi_objection_different_categories()
    events = _extractor.extract(call)
    assert len(events) == 2
    assert {e.category for e in events} == {"timing_priority", "trust_authority"}


def test_same_category_different_segments_yields_two_distinct_events():
    call = call_same_category_repeated_different_segments()
    events = _extractor.extract(call)
    assert len(events) == 2
    assert all(e.category == "price" for e in events)
    assert len({e.objection_id for e in events}) == 2
    assert len({e.segment_id for e in events}) == 2


def test_same_category_twice_in_one_segment_collapses_to_one_event():
    call = call_same_category_twice_in_one_segment()
    events = _extractor.extract(call)
    assert len(events) == 1
    assert events[0].category == "price"


def test_closer_only_objection_language_yields_no_event():
    """Keyword hit lives only in a closer segment (role-play/quoting) — must not fire, since
    extraction is restricted to role='lead' segments."""
    call = call_closer_only_objection_like_language()
    assert _extractor.extract(call) == []


def test_ambiguous_phrasing_not_detected_documents_recall_gap():
    """Known v0 limitation: 'vou pensar' is not in `_KEYWORDS` (only 'preciso pensar' is).
    Documents current behavior — not a bug, a recall boundary flagged in advance."""
    call = call_ambiguous_phrasing_not_detected()
    assert _extractor.extract(call) == []


def test_objection_split_across_segments_not_detected():
    """Known v0 limitation: single-segment evidence means a keyword phrase split across a
    segment boundary is invisible to the extractor (deferred edge case, see
    docs/domain/OBJECTION_MODEL.md)."""
    call = call_objection_split_across_segments()
    assert _extractor.extract(call) == []


def test_minimal_valid_call_no_crash_no_fabrication():
    call = call_minimal_valid()
    assert _extractor.extract(call) == []


def test_every_event_segment_id_grounds_to_a_real_lead_segment():
    """Evidence grounding exercised directly against the reference extractor: every emitted
    event's segment_id must resolve to a real segment on the source call, spoken by a
    role='lead' participant."""
    calls = (
        call_single_objection(),
        call_multi_objection_different_categories(),
        call_same_category_repeated_different_segments(),
        call_same_category_twice_in_one_segment(),
    )
    for call in calls:
        lead_ids = {p.id for p in call.participants if p.role == "lead"}
        segment_by_id = {s.segment_id: s for s in call.segments}
        events = _extractor.extract(call)
        assert events, f"expected at least one event for {call.source_id}"
        for event in events:
            assert event.segment_id in segment_by_id
            assert segment_by_id[event.segment_id].speaker_id in lead_ids


def test_event_objection_id_matches_derivation_rule():
    call = call_single_objection()
    event = _extractor.extract(call)[0]
    expected_id = derive_objection_id(call.call_id, event.segment_id, event.category)
    assert event.objection_id == expected_id


def test_extract_is_idempotent():
    """Re-running extraction on the same call must produce identical events (same ids), not
    duplicate or drifting output."""
    call = call_multi_objection_different_categories()
    first = _extractor.extract(call)
    second = _extractor.extract(call)
    assert [e.objection_id for e in first] == [e.objection_id for e in second]
