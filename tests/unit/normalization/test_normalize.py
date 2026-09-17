import pytest
from pydantic import ValidationError
from synthetic_calls import raw_call

from closer_ai.normalization.ids import derive_call_id, derive_segment_id
from closer_ai.normalization.normalize import normalize_call


def test_normalize_call_produces_valid_call():
    call = normalize_call(raw_call())
    assert call.company_id == "synthco-001"
    assert len(call.segments) == 3
    assert len(call.participants) == 2


def test_normalize_call_id_matches_derivation_rule():
    call = normalize_call(raw_call())
    expected = derive_call_id("synthco-001", "synthetic", "synth-call-0001")
    assert call.call_id == expected


def test_normalize_segment_ids_match_derivation_rule():
    call = normalize_call(raw_call())
    for index, segment in enumerate(call.segments):
        assert segment.segment_id == derive_segment_id(call.call_id, index)
        assert segment.segment_index == index


def test_normalize_call_is_idempotent():
    raw = raw_call()
    first = normalize_call(raw)
    second = normalize_call(raw)
    assert first == second
    assert first.call_id == second.call_id


def test_normalize_call_different_source_id_no_collision():
    a = normalize_call(raw_call(source_id="synth-call-0001"))
    b = normalize_call(raw_call(source_id="synth-call-0002"))
    assert a.call_id != b.call_id


def test_normalize_call_closer_id_optional():
    call = normalize_call(raw_call(closer_id=None))
    assert call.closer_id is None


def test_normalize_call_missing_participant_name_allowed():
    raw = raw_call()
    raw["participants"][1]["name"] = None
    call = normalize_call(raw)
    assert call.participants[1].name is None


def test_normalize_call_unknown_role_participant():
    raw = raw_call()
    raw["participants"].append({"id": "participant-other", "role": "unknown"})
    raw["segments"].append(
        {"speaker_id": "participant-other", "start_ts": 20.0, "end_ts": 25.0, "text": "..."}
    )
    call = normalize_call(raw)
    assert call.participants[-1].role == "unknown"


def test_normalize_call_rejects_end_before_start():
    raw = raw_call()
    raw["segments"][0]["end_ts"] = 0.0
    raw["segments"][0]["start_ts"] = 5.0
    with pytest.raises(ValidationError):
        normalize_call(raw)


def test_normalize_call_rejects_empty_segments():
    raw = raw_call(segments=[])
    with pytest.raises(ValidationError):
        normalize_call(raw)


def test_normalize_call_rejects_negative_duration():
    raw = raw_call(duration_seconds=-1.0)
    with pytest.raises(ValidationError):
        normalize_call(raw)


def test_normalize_call_flags_duration_mismatch():
    raw = raw_call(duration_seconds=5.0)
    call = normalize_call(raw)
    assert "duration_mismatch" in call.quality_flags
