"""raw dict -> canonical Call. Source-agnostic, synthetic-data entry point only.

This proves the `raw -> Call` contract. Per-source parsers (Kommo, Zoom, etc. against real
transcripts) are a separate future task — see docs/context/CURRENT_STATE.md.

Expected `raw` shape (all keys required unless noted):

    {
        "company_id": str,
        "source": str,
        "source_id": str,
        "occurred_at": datetime,   # timezone-aware
        "duration_seconds": float,
        "closer_id": str | None,  # optional, resolved later
        "participants": [{"id": str, "name": str | None, "role": str}, ...],
        "segments": [{"speaker_id": str, "start_ts": float, "end_ts": float, "text": str}, ...],
        "quality_flags": [str, ...],  # optional
    }
"""
from __future__ import annotations

from typing import Any

from closer_ai.normalization.ids import derive_call_id, derive_segment_id
from closer_ai.normalization.models import (
    CANONICAL_SCHEMA_VERSION,
    Call,
    Participant,
    TranscriptSegment,
)


def normalize_call(raw: dict[str, Any]) -> Call:
    company_id = raw["company_id"]
    source = raw["source"]
    source_id = raw["source_id"]
    call_id = derive_call_id(company_id, source, source_id)

    participants = [
        Participant(id=p["id"], name=p.get("name"), role=p.get("role", "unknown"))
        for p in raw["participants"]
    ]

    segments = [
        TranscriptSegment(
            segment_id=derive_segment_id(call_id, index),
            segment_index=index,
            speaker_id=segment["speaker_id"],
            start_ts=segment["start_ts"],
            end_ts=segment["end_ts"],
            text=segment["text"],
        )
        for index, segment in enumerate(raw["segments"])
    ]

    return Call(
        schema_version=CANONICAL_SCHEMA_VERSION,
        call_id=call_id,
        company_id=company_id,
        source=source,
        source_id=source_id,
        occurred_at=raw["occurred_at"],
        duration_seconds=raw["duration_seconds"],
        closer_id=raw.get("closer_id"),
        participants=participants,
        segments=segments,
        quality_flags=list(raw.get("quality_flags", [])),
    )
