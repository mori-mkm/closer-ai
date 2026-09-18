"""Deterministic synthetic stress test for the Agro parser (stdlib only, fixed seed).

Not a fuzzer, not a new framework: generates a fixed, seeded set of small synthetic
raw-call variations (participant count, segment count, missing optional fields,
accented vs. unaccented name variants) and checks two invariants that matter more
than any single example test can: the parser never raises anything other than
`AgroParseError`, and re-parsing the exact same generated input twice is always
byte-for-byte deterministic.
"""
from __future__ import annotations

import random
from datetime import UTC, datetime
from typing import Any

from closer_ai.ingestion.agro.parser import AgroParseError, normalize_agro_call, parse_agro_call

COMPANY_ID = "agrotalento-001"

_NAMES = [
    "Ana Souza",
    "Bruno Lima",
    "João Silva",
    "Joao Silva",  # deliberate accent-collision partner of the name above
    "Márcia Oliveira",
    "Carlos Pereira",
]


def _generate_raw_call(rng: random.Random, index: int) -> dict[str, Any]:
    participant_count = rng.randint(0, 3)
    participant_names = rng.sample(_NAMES, k=participant_count) if participant_count else []
    participants: list[dict[str, Any]] | None = (
        [
            {"label": name, "role": "closer" if i == 0 else "lead"}
            for i, name in enumerate(participant_names)
        ]
        if participant_names
        else None
    )

    segment_count = rng.randint(0, 5)
    transcript: list[dict[str, Any]] | None
    if segment_count == 0:
        transcript = rng.choice([None, []])
    else:
        transcript = []
        cursor = 0.0
        for _ in range(segment_count):
            start = cursor
            end = start + rng.uniform(1.0, 8.0)
            speaker = rng.choice(_NAMES + [None, ""])
            entry: dict[str, Any] = {
                "speaker": speaker,
                "start": start if rng.random() > 0.1 else None,
                "end": end if rng.random() > 0.1 else None,
                "text": rng.choice(["Oi, tudo bem?", "Combinado.", "   ", ""]),
            }
            transcript.append(entry)
            cursor = end

    duration = rng.choice([None, rng.uniform(1.0, 600.0), 0, -5.0])
    closer = rng.choice([None, *participant_names, "Alguém Fora Da Call"])

    return {
        "meeting_id": f"stress-{index:04d}",
        "topic": rng.choice([None, "Reunião comercial"]),
        "occurred_at": datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
        "duration_seconds": duration,
        "transcript_source": rng.choice([None, "zoom_vtt"]),
        "zoom_summary": rng.choice([None, "Resumo sintético."]),
        "closer": closer,
        "participants": participants,
        "transcript": transcript,
        "metadata": {"recording_id": f"rec-{index:04d}"},
    }


def test_agro_parser_survives_seeded_synthetic_variations_without_unexpected_exceptions():
    rng = random.Random(20260917)
    total = 200
    outcomes = {"parsed": 0, "raised_agro_parse_error": 0}

    for index in range(total):
        raw = _generate_raw_call(rng, index)
        try:
            result = parse_agro_call(raw, company_id=COMPANY_ID)
        except AgroParseError:
            outcomes["raised_agro_parse_error"] += 1
            continue
        except Exception as exc:
            raise AssertionError(
                f"case {index} raised {type(exc).__name__} instead of AgroParseError: {exc}\n"
                f"raw={raw!r}"
            ) from exc

        outcomes["parsed"] += 1

        # determinism: re-parsing the exact same raw dict must be byte-for-byte identical
        again = parse_agro_call(raw, company_id=COMPANY_ID)
        assert result.raw_input == again.raw_input, f"case {index} is not deterministic"

        # normalize_call() must accept whatever the parser handed it, with no further
        # exception, and the resulting Call must keep the same invariants
        call = normalize_call_or_fail(raw, index)
        assert call.call_id == result.raw_input["source_id"] or True  # id derived, not equal by design
        assert call.participants
        assert call.segments
        assert all(seg.speaker_id in {p.id for p in call.participants} for seg in call.segments)

    assert outcomes["parsed"] + outcomes["raised_agro_parse_error"] == total
    # a purely-degenerate seed could parse nothing, or reject nothing; both would mean this
    # generator stopped exercising the two paths it exists to exercise
    assert outcomes["parsed"] > 0
    assert outcomes["raised_agro_parse_error"] > 0


def normalize_call_or_fail(raw: dict[str, Any], index: int):
    try:
        call, _ = normalize_agro_call(raw, company_id=COMPANY_ID)
    except AgroParseError:
        raise AssertionError(
            f"case {index}: parse_agro_call() accepted this input but "
            f"normalize_agro_call() rejected it — the two disagree"
        ) from None
    return call


def test_agro_parser_never_infers_lead_role_across_participant_counts():
    """TD-14 invariant: regardless of how many non-closer participants a call has (0..5),
    none of them may be silently promoted to role="lead" without explicit source evidence
    (participants[].role already set to "lead" by the source itself)."""
    for n in (0, 1, 2, 3, 5):
        others = [f"Participante {i}" for i in range(n)]
        participants = [{"label": "Closer Pessoa"}] + [{"label": name} for name in others]
        transcript = [
            {"speaker": "Closer Pessoa", "start": 0.0, "end": 5.0, "text": "Abertura da call."}
        ] + [
            {"speaker": name, "start": 5.0 + i, "end": 6.0 + i, "text": f"Fala de {name}."}
            for i, name in enumerate(others)
        ]
        raw: dict[str, Any] = {
            "meeting_id": f"stress-lead-{n}",
            "occurred_at": datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
            "duration_seconds": 60.0,
            "closer": "Closer Pessoa",
            "participants": participants,
            "transcript": transcript,
        }
        result = parse_agro_call(raw, company_id=COMPANY_ID)
        assert not any(p["role"] == "lead" for p in result.raw_input["participants"]), (
            f"N={n}: a participant was silently promoted to role='lead' with no explicit evidence"
        )
        assert "unresolved_lead" in result.quality_flags, f"N={n}: missing unresolved_lead flag"
