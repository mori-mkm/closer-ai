import pytest
from pydantic import ValidationError

from closer_ai.domain.objection import (
    OBJECTION_SCHEMA_VERSION,
    ObjectionEvent,
    derive_objection_id,
)


def _event(**overrides):
    call_id = overrides.pop("call_id", "call_1")
    segment_id = overrides.pop("segment_id", "seg_1")
    category = overrides.pop("category", "price")
    objection_id = overrides.pop(
        "objection_id", derive_objection_id(call_id, segment_id, category)
    )
    return ObjectionEvent(
        objection_id=objection_id,
        call_id=call_id,
        segment_id=segment_id,
        category=category,
        **overrides,
    )


# --- valid construction ---


def test_event_minimal_valid():
    event = _event()
    assert event.category == "price"
    assert event.call_id == "call_1"
    assert event.segment_id == "seg_1"


def test_event_default_schema_version():
    event = _event()
    assert event.schema_version == OBJECTION_SCHEMA_VERSION


def test_event_objection_id_matches_derivation():
    event = _event()
    assert event.objection_id == derive_objection_id("call_1", "seg_1", "price")


# --- objection_id / derivation enforcement ---


def test_event_objection_id_mismatch_rejected():
    with pytest.raises(ValidationError, match="objection_id must be derive_objection_id"):
        _event(objection_id="obj_0000000000000000000000")


def test_event_objection_id_from_different_category_rejected():
    """A id derived for a different category than the one actually set must be rejected —
    guards against a caller passing mismatched fields, not just a garbage string."""
    wrong_id = derive_objection_id("call_1", "seg_1", "no_need")
    with pytest.raises(ValidationError, match="objection_id must be derive_objection_id"):
        _event(objection_id=wrong_id, category="price")


# --- category enum ---


def test_event_invalid_category_rejected():
    with pytest.raises(ValidationError):
        _event(category="not_a_real_category")


# --- call_id / segment_id emptiness ---


def test_event_empty_call_id_rejected():
    with pytest.raises(ValidationError, match="call_id must not be empty"):
        _event(call_id="")


def test_event_whitespace_only_call_id_rejected():
    with pytest.raises(ValidationError, match="call_id must not be empty"):
        _event(call_id="   ")


def test_event_empty_segment_id_rejected():
    with pytest.raises(ValidationError, match="segment_id must not be empty"):
        _event(segment_id="")


def test_event_whitespace_only_segment_id_rejected():
    with pytest.raises(ValidationError, match="segment_id must not be empty"):
        _event(segment_id="   ")


# --- immutability ---


def test_event_is_frozen():
    event = _event()
    with pytest.raises(ValidationError):
        event.category = "no_need"


# --- derive_objection_id: determinism / non-collision ---


def test_derive_objection_id_deterministic_same_input():
    a = derive_objection_id("call_1", "seg_1", "price")
    b = derive_objection_id("call_1", "seg_1", "price")
    assert a == b


def test_derive_objection_id_differs_by_call_id():
    a = derive_objection_id("call_1", "seg_1", "price")
    b = derive_objection_id("call_2", "seg_1", "price")
    assert a != b


def test_derive_objection_id_differs_by_segment_id():
    a = derive_objection_id("call_1", "seg_1", "price")
    b = derive_objection_id("call_1", "seg_2", "price")
    assert a != b


def test_derive_objection_id_differs_by_category():
    a = derive_objection_id("call_1", "seg_1", "price")
    b = derive_objection_id("call_1", "seg_1", "no_need")
    assert a != b


def test_derive_objection_id_no_ambiguous_concatenation_collision():
    a = derive_objection_id("AB", "C", "price")
    b = derive_objection_id("A", "BC", "price")
    assert a != b


def test_derive_objection_id_same_segment_same_category_is_the_dedup_key():
    """Not just a hashing property: this determinism IS the dedup rule documented in
    docs/domain/OBJECTION_MODEL.md ("IDs e dedup") — re-extraction of the same category from
    the same segment must collapse to one id."""
    first = derive_objection_id("call_1", "seg_1", "price")
    second = derive_objection_id("call_1", "seg_1", "price")
    assert first == second
