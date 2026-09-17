import pytest
from synthetic_agro_calls import (
    agro_raw_call,
    agro_raw_call_closer_not_resolved,
    agro_raw_call_empty_transcript,
    agro_raw_call_incomplete_metadata,
    agro_raw_call_inconsistent_timestamps,
    agro_raw_call_missing_participants,
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


def test_parse_agro_call_duration_none_is_recoverable():
    """Ausência de duration_seconds é o caso recuperável: vira missing_duration + estimativa."""
    result = parse_agro_call(agro_raw_call(duration_seconds=None), company_id=COMPANY_ID)
    assert "missing_duration" in result.quality_flags
    assert result.raw_input["duration_seconds"] == 30.0  # max end_ts dos 3 segmentos base


@pytest.mark.parametrize("bad_duration", [0, 0.0, -1, -120])
def test_parse_agro_call_duration_present_but_invalid_raises_agro_parse_error(bad_duration):
    """duration_seconds fornecida porém inválida (<=0) NÃO é recuperável: deve virar
    AgroParseError, nunca um pydantic.ValidationError cru vazando de normalize_call()."""
    with pytest.raises(AgroParseError):
        parse_agro_call(agro_raw_call(duration_seconds=bad_duration), company_id=COMPANY_ID)


def test_parse_agro_call_duration_invalid_error_message_is_clean():
    with pytest.raises(AgroParseError) as exc_info:
        parse_agro_call(agro_raw_call(duration_seconds=-1), company_id=COMPANY_ID)
    message = str(exc_info.value)
    assert "zoom-agro-0001" in message
    assert "pydantic" not in message.lower()
    assert "validation error" not in message.lower()


def test_normalize_agro_call_duration_invalid_raises_agro_parse_error_not_pydantic():
    """Guarda de regressão: a tradução precisa valer também através do wrapper de
    conveniência, não só de parse_agro_call() isoladamente."""
    with pytest.raises(AgroParseError):
        normalize_agro_call(agro_raw_call(duration_seconds=-1), company_id=COMPANY_ID)


# --- missing_participants ---


def test_parse_agro_call_missing_participants_reconstructed_from_transcript():
    result = parse_agro_call(agro_raw_call_missing_participants(), company_id=COMPANY_ID)
    assert "missing_participants" in result.quality_flags
    assert len(result.raw_input["participants"]) == 2
    assert len(result.raw_input["segments"]) == 3


def test_parse_agro_call_missing_participants_is_deterministic():
    raw = agro_raw_call_missing_participants()
    first = parse_agro_call(raw, company_id=COMPANY_ID)
    second = parse_agro_call(raw, company_id=COMPANY_ID)
    assert first.raw_input == second.raw_input


def test_normalize_agro_call_missing_participants_still_produces_valid_call():
    call, result = normalize_agro_call(agro_raw_call_missing_participants(), company_id=COMPANY_ID)
    assert len(call.participants) == 2
    assert "missing_participants" in call.quality_flags
    assert "missing_participants" in result.quality_flags


# --- closer not resolved ---
#
# Comportamento documentado aqui, já existente no parser antes desta task (não é uma
# heurística nova): quando `closer` aponta para um nome que nao bate com nenhum
# participante/speaker conhecido, `_resolve_closer` retorna None, closer_id fica None
# (o contrato de Call permite closer_id opcional) e metadata_incomplete é sinalizada -
# nunca uma exception, porque a call em si continua totalmente processavel.


def test_parse_agro_call_closer_not_resolved_flags_metadata_incomplete():
    result = parse_agro_call(agro_raw_call_closer_not_resolved(), company_id=COMPANY_ID)
    assert result.raw_input["closer_id"] is None
    assert "metadata_incomplete" in result.quality_flags
    assert len(result.raw_input["participants"]) == 2
    assert len(result.raw_input["segments"]) == 3


def test_normalize_agro_call_closer_not_resolved_still_produces_valid_call():
    call, result = normalize_agro_call(agro_raw_call_closer_not_resolved(), company_id=COMPANY_ID)
    assert call.closer_id is None
    assert "metadata_incomplete" in call.quality_flags
    assert "metadata_incomplete" in result.quality_flags


# --- integration: parser -> normalize_call -> Call ---


def test_normalize_agro_call_produces_canonical_call_with_deterministic_ids():
    call, result = normalize_agro_call(agro_raw_call(), company_id=COMPANY_ID)
    expected_call_id = derive_call_id(COMPANY_ID, "agro_zoom", "zoom-agro-0001")
    assert call.call_id == expected_call_id
    for index, segment in enumerate(call.segments):
        assert segment.segment_id == derive_segment_id(call.call_id, index)
        assert segment.segment_index == index
    assert result.metadata["meeting_id"] == "zoom-agro-0001"
