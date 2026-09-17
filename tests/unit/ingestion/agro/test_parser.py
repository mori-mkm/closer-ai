import pytest
from synthetic_agro_calls import (
    agro_raw_call,
    agro_raw_call_empty_transcript,
    agro_raw_call_incomplete_metadata,
    agro_raw_call_inconsistent_timestamps,
    agro_raw_call_missing_transcript,
    agro_raw_call_unresolved_speaker,
)

from closer_ai.ingestion.agro.parser import AgroParseError, normalize_agro_call, parse_agro_call
from closer_ai.normalization.ids import derive_call_id, derive_segment_id

COMPANY_ID = "agrotalento-001"


# --- normal case ---


def test_parse_agro_call_normal_case_produces_valid_input():
    result = parse_agro_call(agro_raw_call(), company_id=COMPANY_ID)
    assert result.raw_input["company_id"] == COMPANY_ID
    assert result.raw_input["source"] == "agro_zoom"
    assert result.raw_input["source_id"] == "zoom-agro-0001"
    assert len(result.raw_input["participants"]) == 2
    assert len(result.raw_input["segments"]) == 3
    assert result.quality_flags == []


def test_parse_agro_call_preserves_segment_order():
    result = parse_agro_call(agro_raw_call(), company_id=COMPANY_ID)
    texts = [segment["text"] for segment in result.raw_input["segments"]]
    assert texts == [
        "Oi Bruno, tudo bem? Vamos falar do plano.",
        "Tudo bem! Fiquei com uma dúvida sobre o prazo.",
        "Boa pergunta, deixa eu explicar como funciona.",
    ]


def test_parse_agro_call_resolves_closer_id():
    result = parse_agro_call(agro_raw_call(), company_id=COMPANY_ID)
    closer_participant = next(
        p for p in result.raw_input["participants"] if p["role"] == "closer"
    )
    assert result.raw_input["closer_id"] == closer_participant["id"]


def test_parse_agro_call_metadata_traceability():
    result = parse_agro_call(agro_raw_call(), company_id=COMPANY_ID)
    assert result.metadata["meeting_id"] == "zoom-agro-0001"
    assert result.metadata["transcript_source"] == "zoom_vtt"
    assert result.metadata["zoom_summary"]
    assert result.metadata["raw_metadata"]["recording_id"] == "rec-0001"


def test_parse_agro_call_is_deterministic():
    raw = agro_raw_call()
    first = parse_agro_call(raw, company_id=COMPANY_ID)
    second = parse_agro_call(raw, company_id=COMPANY_ID)
    assert first.raw_input == second.raw_input


# --- case 2: incomplete metadata ---


def test_parse_agro_call_incomplete_metadata_flagged_not_raised():
    result = parse_agro_call(agro_raw_call_incomplete_metadata(), company_id=COMPANY_ID)
    assert result.quality_flags == ["metadata_incomplete"]
    assert len(result.raw_input["segments"]) == 3
    assert result.metadata["topic"] is None


# --- case 3: unresolved speaker ---


def test_parse_agro_call_unresolved_speaker_synthesizes_participant():
    baseline = parse_agro_call(agro_raw_call(), company_id=COMPANY_ID)
    result = parse_agro_call(agro_raw_call_unresolved_speaker(), company_id=COMPANY_ID)
    assert "unresolved_speaker" in result.quality_flags
    assert len(result.raw_input["participants"]) == len(baseline.raw_input["participants"]) + 1
    assert len(result.raw_input["segments"]) == 4


# --- case 4: missing / empty transcript ---


def test_parse_agro_call_missing_transcript_raises():
    with pytest.raises(AgroParseError):
        parse_agro_call(agro_raw_call_missing_transcript(), company_id=COMPANY_ID)


def test_parse_agro_call_empty_transcript_raises():
    with pytest.raises(AgroParseError):
        parse_agro_call(agro_raw_call_empty_transcript(), company_id=COMPANY_ID)


def test_parse_agro_call_missing_meeting_id_raises():
    raw = agro_raw_call()
    del raw["meeting_id"]
    with pytest.raises(AgroParseError):
        parse_agro_call(raw, company_id=COMPANY_ID)


def test_parse_agro_call_missing_occurred_at_raises():
    with pytest.raises(AgroParseError):
        parse_agro_call(agro_raw_call(occurred_at=None), company_id=COMPANY_ID)


# --- case 5: inconsistent timestamps / missing duration ---


def test_parse_agro_call_inconsistent_timestamps_flags_and_estimates_duration():
    result = parse_agro_call(agro_raw_call_inconsistent_timestamps(), company_id=COMPANY_ID)
    assert "missing_duration" in result.quality_flags
    assert "missing_timestamp" in result.quality_flags
    assert "transcript_parse_error" in result.quality_flags
    # inverted-timestamp entry and missing-start entry are dropped; 2 valid segments remain
    assert len(result.raw_input["segments"]) == 2
    assert result.raw_input["duration_seconds"] == 45.0


# --- integration: parser -> normalize_call -> Call ---


def test_normalize_agro_call_produces_canonical_call_with_deterministic_ids():
    call, result = normalize_agro_call(agro_raw_call(), company_id=COMPANY_ID)
    expected_call_id = derive_call_id(COMPANY_ID, "agro_zoom", "zoom-agro-0001")
    assert call.call_id == expected_call_id
    for index, segment in enumerate(call.segments):
        assert segment.segment_id == derive_segment_id(call.call_id, index)
        assert segment.segment_index == index
    assert result.metadata["meeting_id"] == "zoom-agro-0001"
