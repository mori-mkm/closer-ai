"""End-to-end: Agro raw call -> parser -> normalize_call -> canonical Call.

Vertical slice covering representative synthetic Agro/Zoom calls, not the real
108-call corpus (see docs/context/CURRENT_STATE.md for that as a future step).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "fixtures"))

from synthetic_agro_calls import (
    agro_raw_call,
    agro_raw_call_incomplete_metadata,
    agro_raw_call_inconsistent_timestamps,
    agro_raw_call_missing_transcript,
    agro_raw_call_unresolved_speaker,
)

from closer_ai.ingestion.agro.parser import AgroParseError, normalize_agro_call

COMPANY_ID = "agrotalento-001"


def test_normal_call_end_to_end():
    call, result = normalize_agro_call(agro_raw_call(), company_id=COMPANY_ID)
    assert call.source == "agro_zoom"
    assert call.source_id == "zoom-agro-0001"
    assert call.closer_id is not None
    assert call.quality_flags == []
    assert result.quality_flags == []


def test_incomplete_metadata_still_produces_valid_call():
    call, result = normalize_agro_call(agro_raw_call_incomplete_metadata(), company_id=COMPANY_ID)
    assert call.quality_flags == ["metadata_incomplete"]
    assert result.metadata["topic"] is None


def test_unresolved_speaker_still_produces_valid_call():
    call, result = normalize_agro_call(agro_raw_call_unresolved_speaker(), company_id=COMPANY_ID)
    assert len(call.segments) == 4
    assert "unresolved_speaker" in call.quality_flags
    assert "unresolved_speaker" in result.quality_flags


def test_missing_transcript_raises_before_reaching_normalize_call():
    with pytest.raises(AgroParseError):
        normalize_agro_call(agro_raw_call_missing_transcript(), company_id=COMPANY_ID)


def test_inconsistent_timestamps_recovers_with_flags():
    call, result = normalize_agro_call(agro_raw_call_inconsistent_timestamps(), company_id=COMPANY_ID)
    assert len(call.segments) == 2
    assert "missing_duration" in call.quality_flags
    assert "missing_timestamp" in result.quality_flags
    assert "transcript_parse_error" in result.quality_flags
