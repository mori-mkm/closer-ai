"""Tests for the privacy-safe structural profiler (`closer_ai.ingestion.profiling`).

Priority order matches the module's own priority: privacy-leak prevention comes first and gets
more coverage than structural-correctness, because a leak here is the failure mode that
actually matters (see docs/data/REAL_CALL_VALIDATION_KIT.md). All fixtures are synthetic and
deliberately shaped like real PII so the leak tests are meaningful, never real customer data.
"""
from __future__ import annotations

import json
from pathlib import Path

from closer_ai.ingestion.profiling import profile_directory, profile_file

_FAKE_EMAIL = "fake@example.com"
_FAKE_PHONE = "+55 11 99999-9999"
_FAKE_NAME = "Synthetic Person"
_FAKE_TRANSCRIPT_LINE = "texto sintético da conversa sobre preço"

_SENSITIVE_MARKERS = (_FAKE_EMAIL, _FAKE_PHONE, _FAKE_NAME, _FAKE_TRANSCRIPT_LINE)


def _profile_as_text(profile) -> str:
    """Flatten a StructuralProfile to a string the way a report/log would render it."""
    return repr(profile)


# --- privacy: no sensitive value ever appears in the profile output ---


def test_json_profile_never_leaks_field_values(tmp_path: Path):
    raw = {
        "meeting_id": "zoom-0001",
        "participants": [
            {"speaker": _FAKE_NAME, "email": _FAKE_EMAIL, "phone": _FAKE_PHONE, "role": "lead"},
            {"speaker": "Closer Pessoa", "email": None, "phone": None, "role": "closer"},
        ],
        "transcript": [
            {"speaker": _FAKE_NAME, "start": 0.0, "end": 5.0, "text": _FAKE_TRANSCRIPT_LINE},
        ],
    }
    path = tmp_path / "maria_silva_call.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    profile = profile_file(path)
    rendered = _profile_as_text(profile)

    for marker in _SENSITIVE_MARKERS:
        assert marker not in rendered, f"leaked: {marker!r}"
    assert "maria_silva" not in rendered  # filename itself must not leak either
    assert profile.safe_id != path.stem


def test_csv_profile_never_leaks_field_values(tmp_path: Path):
    path = tmp_path / "leads.csv"
    path.write_text(
        f"name,email,phone,notes\n{_FAKE_NAME},{_FAKE_EMAIL},{_FAKE_PHONE},{_FAKE_TRANSCRIPT_LINE}\n",
        encoding="utf-8",
    )

    profile = profile_file(path)
    rendered = _profile_as_text(profile)

    for marker in _SENSITIVE_MARKERS:
        assert marker not in rendered


def test_vtt_profile_never_leaks_cue_text(tmp_path: Path):
    path = tmp_path / "call.vtt"
    path.write_text(
        "WEBVTT\n\n"
        f"00:00:00.000 --> 00:00:05.000\n{_FAKE_NAME}: {_FAKE_TRANSCRIPT_LINE}\n\n"
        f"00:00:05.000 --> 00:00:10.000\nOutro: {_FAKE_EMAIL} {_FAKE_PHONE}\n",
        encoding="utf-8",
    )

    profile = profile_file(path)
    rendered = _profile_as_text(profile)

    for marker in _SENSITIVE_MARKERS:
        assert marker not in rendered
    assert profile.transcript_segment_count == 2


def test_txt_profile_never_leaks_content(tmp_path: Path):
    path = tmp_path / "notes.txt"
    path.write_text(f"{_FAKE_NAME}\n{_FAKE_EMAIL}\n{_FAKE_TRANSCRIPT_LINE}\n", encoding="utf-8")

    profile = profile_file(path)
    rendered = _profile_as_text(profile)

    for marker in _SENSITIVE_MARKERS:
        assert marker not in rendered


def test_safe_id_never_equals_real_filename(tmp_path: Path):
    path = tmp_path / "maria.silva@example.com - call.json"
    path.write_text("{}", encoding="utf-8")

    profile = profile_file(path)
    assert path.name not in profile.safe_id
    assert "maria" not in profile.safe_id.lower()


def test_profile_directory_uses_sequential_sample_ids_not_filenames(tmp_path: Path):
    (tmp_path / "maria_silva.json").write_text(json.dumps({"a": 1}), encoding="utf-8")
    (tmp_path / "joao_pereira.json").write_text(json.dumps({"a": 1}), encoding="utf-8")

    profiles = profile_directory(tmp_path)
    ids = [p.safe_id for p in profiles]

    assert ids == ["sample_001", "sample_002"]
    for name in ("maria_silva", "joao_pereira"):
        assert not any(name in i for i in ids)


def test_malformed_file_error_does_not_leak_content(tmp_path: Path):
    path = tmp_path / "broken.json"
    path.write_text(f"{{not valid json, but contains {_FAKE_EMAIL}", encoding="utf-8")

    profile = profile_file(path)
    rendered = _profile_as_text(profile)

    assert _FAKE_EMAIL not in rendered
    assert profile.notes  # failure is visible, just not the content that caused it


# --- structural correctness ---


def test_json_list_profile_reports_counts_and_types(tmp_path: Path):
    raw = [
        {"speaker": "a", "start": 0.0, "end": 1.0, "text": "hi"},
        {"speaker": "b", "start": 1.0, "end": 2.0, "text": "hello"},
        {"speaker": "a", "start": 2.0, "end": None, "text": "bye"},
    ]
    path = tmp_path / "transcript.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    profile = profile_file(path)
    assert profile.format == "json"
    assert profile.record_count == 3
    assert set(profile.keys) == {"speaker", "start", "end", "text"}
    assert profile.field_types["start"] == "float"
    assert profile.null_counts["end"] == 1
    assert "start" in profile.timestamp_like_fields
    assert "end" in profile.timestamp_like_fields
    assert profile.speaker_identifier_count == 2  # distinct: "a", "b"


def test_json_single_object_with_nested_transcript_list(tmp_path: Path):
    raw = {
        "meeting_id": "zoom-0002",
        "transcript": [
            {"speaker": "a", "start": 0.0, "end": 1.0, "text": "hi"},
            {"speaker": "b", "start": 1.0, "end": 2.0, "text": "hello"},
        ],
    }
    path = tmp_path / "call.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    profile = profile_file(path)
    assert profile.transcript_segment_count == 2
    assert profile.speaker_identifier_count == 2


def test_csv_profile_reports_columns_and_row_count(tmp_path: Path):
    path = tmp_path / "deals.csv"
    path.write_text("deal_id,stage,created_at,value\nd1,open,2026-01-01,\nd2,won,2026-01-02,100\n", encoding="utf-8")

    profile = profile_file(path)
    assert profile.format == "csv"
    assert profile.record_count == 2
    assert profile.keys == ("deal_id", "stage", "created_at", "value")
    assert profile.null_counts["value"] == 1
    assert "created_at" in profile.timestamp_like_fields


def test_srt_profile_counts_cues(tmp_path: Path):
    path = tmp_path / "call.srt"
    path.write_text(
        "1\n00:00:00,000 --> 00:00:05,000\nline one\n\n"
        "2\n00:00:05,000 --> 00:00:10,000\nline two\n",
        encoding="utf-8",
    )
    profile = profile_file(path)
    assert profile.transcript_segment_count == 2


def test_unsupported_format_does_not_raise(tmp_path: Path):
    path = tmp_path / "recording.mp3"
    path.write_bytes(b"\x00\x01\x02")

    profile = profile_file(path)
    assert profile.format.startswith("unsupported:")
    assert profile.notes


def test_binary_file_does_not_raise(tmp_path: Path):
    path = tmp_path / "data.json"
    path.write_bytes(bytes(range(256)))

    profile = profile_file(path)
    assert profile.notes  # undecodable, reported safely, no crash


def test_profile_is_deterministic(tmp_path: Path):
    raw = {"a": 1, "transcript": [{"speaker": "x", "start": 0.0, "end": 1.0, "text": "hi"}]}
    path = tmp_path / "call.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    first = profile_file(path, safe_id="sample_001")
    second = profile_file(path, safe_id="sample_001")
    assert first == second
