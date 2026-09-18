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


# --- hardening round: type-confusion leaks (found by Reviewer) ---


def test_parse_agro_call_participant_label_wrong_type_does_not_crash():
    """label/name/id with a truthy non-string value (int, list, dict, ...) used to
    reach `_slugify()` unchecked and raise a raw TypeError. Now it's the same bucket
    as a missing label: the entry is skipped, not a crash."""
    raw = agro_raw_call()
    raw["participants"] = [{"label": 12345, "role": "closer"}, {"label": "Bruno Lima", "role": "lead"}]
    result = parse_agro_call(raw, company_id=COMPANY_ID)
    ids = {p["id"] for p in result.raw_input["participants"]}
    assert "bruno_lima" in ids
    assert len(result.raw_input["participants"]) <= 2


def test_parse_agro_call_transcript_speaker_wrong_type_does_not_crash():
    raw = agro_raw_call()
    raw["transcript"][0]["speaker"] = ["Ana", "Souza"]
    result = parse_agro_call(raw, company_id=COMPANY_ID)
    assert "unresolved_speaker" in result.quality_flags
    assert len(result.raw_input["segments"]) == 3


def test_normalize_agro_call_participant_label_wrong_type_does_not_leak_type_error():
    raw = agro_raw_call()
    raw["participants"] = [{"label": {"nested": "object"}, "role": "closer"}]
    # must not raise TypeError — either parses (degraded) or raises AgroParseError
    try:
        normalize_agro_call(raw, company_id=COMPANY_ID)
    except AgroParseError:
        pass


# --- hardening round: participant id collisions (slug clash) ---


def test_parse_agro_call_participant_slug_collision_is_flagged_not_silent():
    raw = agro_raw_call()
    raw["participants"] = [
        {"label": "Joao Silva", "role": "lead"},
        {"label": "João Silva", "role": "closer"},
    ]
    raw["transcript"] = [{"speaker": "Joao Silva", "start": 0.0, "end": 5.0, "text": "Oi."}]
    raw["closer"] = None
    result = parse_agro_call(raw, company_id=COMPANY_ID)
    assert "participant_id_collision" in result.quality_flags
    # the first-registered participant survives; the collision is visible, not merged silently
    assert len(result.raw_input["participants"]) == 1
    assert result.raw_input["participants"][0]["role"] == "lead"


def test_parse_agro_call_transcript_speaker_slug_collision_is_flagged():
    raw = agro_raw_call()
    raw["participants"] = [
        {"label": "Joao Silva", "role": "lead"},
        {"label": "Bruno Lima", "role": "lead"},
    ]
    # "João Silva" (accented) collides by slug with the already-registered "Joao Silva"
    raw["transcript"] = [
        {"speaker": "Joao Silva", "start": 0.0, "end": 5.0, "text": "Primeira fala."},
        {"speaker": "João Silva", "start": 5.0, "end": 10.0, "text": "Segunda fala, nome acentuado."},
    ]
    raw["closer"] = None
    result = parse_agro_call(raw, company_id=COMPANY_ID)
    assert "participant_id_collision" in result.quality_flags
    # both segments end up attributed to the same participant id (documented limitation)
    speaker_ids = {seg["speaker_id"] for seg in result.raw_input["segments"]}
    assert speaker_ids == {"joao_silva"}


def test_normalize_agro_call_participant_collision_still_produces_valid_call():
    """The merge is a known limitation, not a crash: normalize_call() must still
    accept the result."""
    raw = agro_raw_call()
    raw["participants"] = [{"label": "Joao Silva", "role": "lead"}]
    raw["transcript"] = [
        {"speaker": "Joao Silva", "start": 0.0, "end": 5.0, "text": "Primeira fala."},
        {"speaker": "João Silva", "start": 5.0, "end": 10.0, "text": "Segunda fala."},
    ]
    raw["closer"] = None
    call, _ = normalize_agro_call(raw, company_id=COMPANY_ID)
    assert "participant_id_collision" in call.quality_flags
    assert len(call.participants) == 1


# --- hardening round: closer resolves to a participant with a conflicting role ---


def test_parse_agro_call_closer_matching_non_unknown_role_is_not_promoted():
    """`closer` slug-matches a participant already registered with role "lead" —
    must not silently overwrite that role nor fabricate a resolution."""
    raw = agro_raw_call()
    raw["participants"] = [
        {"label": "Ana Souza", "role": "lead"},
        {"label": "Bruno Lima", "role": "lead"},
    ]
    raw["closer"] = "Ana Souza"
    result = parse_agro_call(raw, company_id=COMPANY_ID)
    assert result.raw_input["closer_id"] is None
    assert "metadata_incomplete" in result.quality_flags
    ana = next(p for p in result.raw_input["participants"] if p["id"] == "ana_souza")
    assert ana["role"] == "lead"  # untouched


# --- hardening round: closer=None vs closer-not-resolved is a deliberate distinction ---


def test_parse_agro_call_closer_none_does_not_flag_metadata_incomplete_on_its_own():
    raw = agro_raw_call(closer=None, transcript_source="zoom_vtt", zoom_summary="x", topic="x")
    result = parse_agro_call(raw, company_id=COMPANY_ID)
    assert result.raw_input["closer_id"] is None
    assert "metadata_incomplete" not in result.quality_flags


# --- hardening round: occurred_at edge cases (mirror the duration_seconds fix) ---


def test_parse_agro_call_naive_occurred_at_raises_agro_parse_error():
    from datetime import datetime

    raw = agro_raw_call(occurred_at=datetime(2026, 2, 3, 13, 0))  # noqa: DTZ001 - naive on purpose
    with pytest.raises(AgroParseError):
        parse_agro_call(raw, company_id=COMPANY_ID)


def test_parse_agro_call_unparseable_occurred_at_string_raises_agro_parse_error_not_pydantic():
    raw = agro_raw_call(occurred_at="not-a-date")
    with pytest.raises(AgroParseError) as exc_info:
        parse_agro_call(raw, company_id=COMPANY_ID)
    message = str(exc_info.value)
    assert "pydantic" not in message.lower()


def test_parse_agro_call_whitespace_meeting_id_raises():
    raw = agro_raw_call(meeting_id="   ")
    with pytest.raises(AgroParseError):
        parse_agro_call(raw, company_id=COMPANY_ID)


def test_parse_agro_call_missing_end_timestamp_dropped_with_flag():
    raw = agro_raw_call()
    raw["transcript"][0]["end"] = None
    result = parse_agro_call(raw, company_id=COMPANY_ID)
    assert "missing_timestamp" in result.quality_flags
    assert len(result.raw_input["segments"]) == 2


# --- hardening round: determinism of IDs against irrelevant metadata changes ---


def test_parse_agro_call_metadata_change_does_not_affect_call_id_or_segment_ids():
    baseline = parse_agro_call(agro_raw_call(), company_id=COMPANY_ID)
    changed = parse_agro_call(
        agro_raw_call(zoom_summary="Resumo completamente diferente.", topic="Outro título"),
        company_id=COMPANY_ID,
    )
    baseline_call, _ = normalize_agro_call(agro_raw_call(), company_id=COMPANY_ID)
    changed_call, _ = normalize_agro_call(
        agro_raw_call(zoom_summary="Resumo completamente diferente.", topic="Outro título"),
        company_id=COMPANY_ID,
    )
    assert baseline_call.call_id == changed_call.call_id
    assert [s.segment_id for s in baseline_call.segments] == [s.segment_id for s in changed_call.segments]
    assert baseline.raw_input["source_id"] == changed.raw_input["source_id"]


def test_normalize_agro_call_is_fully_deterministic():
    raw = agro_raw_call()
    call_a, _ = normalize_agro_call(raw, company_id=COMPANY_ID)
    call_b, _ = normalize_agro_call(raw, company_id=COMPANY_ID)
    assert call_a == call_b


# --- hardening round: accented participant labels are slugified, not misread as unresolved ---


def test_parse_agro_call_accented_participant_label_resolves_cleanly():
    raw = agro_raw_call()
    raw["participants"] = [
        {"label": "André Ferreira", "role": "closer"},
        {"label": "José Lima", "role": "lead"},
    ]
    raw["transcript"] = [
        {"speaker": "André Ferreira", "start": 0.0, "end": 5.0, "text": "Oi José, tudo bem?"},
        {"speaker": "José Lima", "start": 5.0, "end": 10.0, "text": "Tudo certo."},
    ]
    raw["closer"] = "André Ferreira"
    result = parse_agro_call(raw, company_id=COMPANY_ID)
    assert "unresolved_speaker" not in result.quality_flags
    assert "participant_id_collision" not in result.quality_flags
    assert result.raw_input["closer_id"] is not None


# --- hardening round: unknown top-level fields are ignored, not rejected ---


def test_parse_agro_call_ignores_unknown_top_level_fields():
    raw = agro_raw_call()
    raw["some_future_zoom_field"] = {"anything": "at all"}
    result = parse_agro_call(raw, company_id=COMPANY_ID)
    assert result.quality_flags == []


# --- hardening round: normalize_call() safety net for fields parser.py doesn't
# --- pre-validate (participant role is a Call-level Literal, not reimplemented here)


def test_normalize_agro_call_invalid_participant_role_raises_agro_parse_error_not_pydantic():
    raw = agro_raw_call()
    raw["participants"][0]["role"] = "not_a_real_role"
    with pytest.raises(AgroParseError) as exc_info:
        normalize_agro_call(raw, company_id=COMPANY_ID)
    assert "pydantic" not in str(exc_info.value).lower()


# --- hardening round: no leaking ValidationError even via the exception chain ---
#
# A clean str(exc) is not enough on its own: `raise ... from exc` keeps the original
# pydantic.ValidationError as __cause__, and anything that logs a full traceback
# (traceback.print_exc(), logging.exception()) would still print it — including the
# rejected field value and the errors.pydantic.dev URL. Both AgroParseError sites that
# wrap a ValidationError use `from None` specifically to close this.


def test_parse_agro_call_shape_error_does_not_keep_validation_error_as_cause():
    raw = agro_raw_call(occurred_at="not-a-date")
    with pytest.raises(AgroParseError) as exc_info:
        parse_agro_call(raw, company_id=COMPANY_ID)
    assert exc_info.value.__cause__ is None


def test_normalize_agro_call_role_error_does_not_keep_validation_error_as_cause():
    raw = agro_raw_call()
    raw["participants"][0]["role"] = "not_a_real_role"
    with pytest.raises(AgroParseError) as exc_info:
        normalize_agro_call(raw, company_id=COMPANY_ID)
    assert exc_info.value.__cause__ is None
