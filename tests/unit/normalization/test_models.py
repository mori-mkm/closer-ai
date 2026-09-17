from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from closer_ai.normalization.models import Call, Participant, TranscriptSegment


def _segment(**overrides):
    base = {
        "segment_id": "seg_1",
        "segment_index": 0,
        "speaker_id": "p1",
        "start_ts": 0.0,
        "end_ts": 5.0,
        "text": "hello",
    }
    base.update(overrides)
    return TranscriptSegment(**base)


def _call(**overrides):
    base = {
        "call_id": "call_1",
        "company_id": "synthco-001",
        "source": "synthetic",
        "source_id": "synth-call-0001",
        "occurred_at": datetime(2026, 1, 15, 14, 0, tzinfo=UTC),
        "duration_seconds": 10.0,
        "participants": [Participant(id="p1", role="closer")],
        "segments": [_segment()],
    }
    base.update(overrides)
    return Call(**base)


# --- TranscriptSegment ---


def test_segment_minimal_valid():
    seg = _segment()
    assert seg.segment_id == "seg_1"
    assert seg.text == "hello"


def test_segment_end_before_start_rejected():
    with pytest.raises(ValidationError, match="end_ts must be strictly greater"):
        _segment(start_ts=5.0, end_ts=1.0)


def test_segment_zero_length_rejected():
    with pytest.raises(ValidationError, match="end_ts must be strictly greater"):
        _segment(start_ts=3.0, end_ts=3.0)


def test_segment_negative_start_ts_rejected():
    with pytest.raises(ValidationError):
        _segment(start_ts=-1.0, end_ts=5.0)


def test_segment_empty_text_rejected():
    with pytest.raises(ValidationError, match="text must not be empty"):
        _segment(text="")


def test_segment_whitespace_only_text_rejected():
    with pytest.raises(ValidationError, match="text must not be empty"):
        _segment(text="   ")


def test_segment_is_frozen():
    seg = _segment()
    with pytest.raises(ValidationError):
        seg.text = "changed"


# --- Participant ---


def test_participant_optional_name_defaults_to_none():
    p = Participant(id="p1", role="lead")
    assert p.name is None


def test_participant_unknown_role_defaults():
    p = Participant(id="p1")
    assert p.role == "unknown"


def test_participant_invalid_role_rejected():
    with pytest.raises(ValidationError):
        Participant(id="p1", role="ceo")


# --- Call: minimal valid ---


def test_call_minimal_valid_input():
    call = _call()
    assert call.schema_version == "1.0.0"
    assert call.closer_id is None
    assert call.quality_flags == []


def test_call_is_frozen():
    call = _call()
    with pytest.raises(ValidationError):
        call.duration_seconds = 99.0


# --- Call: duration ---


def test_call_zero_duration_rejected():
    with pytest.raises(ValidationError):
        _call(duration_seconds=0.0)


def test_call_negative_duration_rejected():
    with pytest.raises(ValidationError):
        _call(duration_seconds=-5.0)


# --- Call: occurred_at ---


def test_call_naive_occurred_at_rejected():
    with pytest.raises(ValidationError, match="timezone-aware"):
        _call(occurred_at=datetime(2026, 1, 15, 14, 0))  # noqa: DTZ001 — naive datetime is the case under test


# --- Call: empty collections ---


def test_call_empty_segments_rejected():
    with pytest.raises(ValidationError, match="segments must not be empty"):
        _call(segments=[])


def test_call_empty_participants_rejected():
    with pytest.raises(ValidationError, match="participants must not be empty"):
        _call(participants=[])


# --- Call: segment_index contiguity ---


def test_call_segment_index_gap_rejected():
    segments = [_segment(segment_index=0), _segment(segment_id="seg_2", segment_index=2)]
    with pytest.raises(ValidationError, match="contiguous"):
        _call(segments=segments)


def test_call_segment_index_duplicate_rejected():
    segments = [_segment(segment_index=0), _segment(segment_id="seg_2", segment_index=0)]
    with pytest.raises(ValidationError, match="contiguous"):
        _call(segments=segments)


# --- Call: referential integrity ---


def test_call_unknown_speaker_id_rejected():
    with pytest.raises(ValidationError, match="speaker_id"):
        _call(segments=[_segment(speaker_id="not-a-participant")])


# --- Call: crosstalk / gaps allowed ---


def test_call_overlapping_segments_allowed():
    segments = [
        _segment(segment_index=0, start_ts=0.0, end_ts=5.0),
        _segment(segment_id="seg_2", segment_index=1, start_ts=3.0, end_ts=8.0),
    ]
    call = _call(segments=segments, duration_seconds=10.0)
    assert len(call.segments) == 2


def test_call_gap_between_segments_allowed():
    segments = [
        _segment(segment_index=0, start_ts=0.0, end_ts=2.0),
        _segment(segment_id="seg_2", segment_index=1, start_ts=8.0, end_ts=9.0),
    ]
    call = _call(segments=segments, duration_seconds=10.0)
    assert len(call.segments) == 2


# --- Call: duration_mismatch quality flag (soft check) ---


def test_call_segment_past_duration_sets_quality_flag_not_rejected():
    call = _call(
        segments=[_segment(start_ts=0.0, end_ts=20.0)],
        duration_seconds=10.0,
    )
    assert "duration_mismatch" in call.quality_flags


def test_call_within_duration_has_no_mismatch_flag():
    call = _call()
    assert "duration_mismatch" not in call.quality_flags


def test_call_existing_quality_flag_not_duplicated():
    call = _call(
        segments=[_segment(start_ts=0.0, end_ts=20.0)],
        duration_seconds=10.0,
        quality_flags=["duration_mismatch"],
    )
    assert call.quality_flags.count("duration_mismatch") == 1
