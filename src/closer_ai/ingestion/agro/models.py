"""Raw Zoom/Agro call shape, as received before normalization.

This is NOT a second `Call` model. `AgroRawCall` mirrors the loosely-typed export a
Zoom/Agro pipeline hands us (speaker labels instead of stable ids, optional/missing
fields, free-form metadata) so `parser.py` has something typed to validate against
before it maps that shape onto the `closer_ai.normalization.normalize.normalize_call`
input contract. The real Zoom/Agro export format is still undecided (see
docs/architecture/INTEGRATIONS.md) — every field here is a first hypothesis, not a
confirmed spec.

`AgroParseResult` is the parser's output: `raw_input` is the dict `normalize_call()`
expects, `quality_flags` mirrors what was merged into it, and `metadata` carries the
source context (meeting id, topic, zoom summary, ...) that has no place on the
canonical `Call` — this is the "pipeline output" traceability layer.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator


class AgroRawCall(BaseModel):
    model_config = ConfigDict(frozen=True)

    meeting_id: str
    topic: str | None = None
    occurred_at: datetime | None = None
    duration_seconds: float | None = None
    transcript_source: str | None = None
    zoom_summary: str | None = None
    closer: str | None = None
    participants: list[dict[str, Any]] | None = None
    transcript: list[dict[str, Any]] | None = None
    metadata: dict[str, Any] | None = None

    @field_validator("meeting_id")
    @classmethod
    def _meeting_id_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("meeting_id must not be blank")
        return value


@dataclass(frozen=True)
class AgroParseResult:
    raw_input: dict[str, Any]
    quality_flags: list[str]
    metadata: dict[str, Any]
