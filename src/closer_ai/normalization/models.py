"""Canonical Call schema. See docs/architecture/DATA_MODEL.md for the conceptual model.

Validation decisions worth knowing (they're invariants, not obvious from field names):

- Call, TranscriptSegment and Participant are frozen (immutable) after creation. Future
  evidence_span references (ai/ layer) point at a segment by id; a Call must never change
  under a reference already taken against it.
- `participants` and `segments` must be non-empty: a Call with no transcript content is
  treated as an upstream error, not a valid empty record.
- A segment's `end_ts` must be strictly greater than `start_ts` (no zero-length segments).
- Segments may overlap across speakers (crosstalk) or have gaps (silence) — only the
  per-segment start<end is enforced, not monotonicity across the whole call.
- `segment_index` must be contiguous from 0 with no gaps or duplicates: future evidence_span
  lookups resolve a segment by (call_id, segment_index), so a gap would silently break that.
- Every segment's `speaker_id` must resolve to a participant in `Call.participants` —
  referential integrity that objection-extraction attribution (closer vs lead) depends on.
- If the transcript runs past `duration_seconds`, that's recorded as a "duration_mismatch"
  quality flag rather than rejected — ASR/diarization duration drift is expected, not fatal.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

CANONICAL_SCHEMA_VERSION = "1.0.0"

Role = Literal["closer", "lead", "other", "unknown"]


class Participant(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    name: str | None = None
    role: Role = "unknown"


class TranscriptSegment(BaseModel):
    model_config = ConfigDict(frozen=True)

    segment_id: str
    segment_index: int = Field(ge=0)
    speaker_id: str
    start_ts: float = Field(ge=0)
    end_ts: float
    text: str

    @model_validator(mode="after")
    def _check_span_and_text(self) -> TranscriptSegment:
        if self.end_ts <= self.start_ts:
            raise ValueError("end_ts must be strictly greater than start_ts")
        if not self.text.strip():
            raise ValueError("text must not be empty")
        return self


class Call(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: str = CANONICAL_SCHEMA_VERSION
    call_id: str
    company_id: str
    source: str
    source_id: str
    occurred_at: datetime
    duration_seconds: float = Field(gt=0)
    closer_id: str | None = None
    participants: list[Participant]
    segments: list[TranscriptSegment]
    quality_flags: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_invariants(self) -> Call:
        if self.occurred_at.tzinfo is None:
            raise ValueError("occurred_at must be timezone-aware")
        if not self.participants:
            raise ValueError("participants must not be empty")
        if not self.segments:
            raise ValueError("segments must not be empty")

        indices = sorted(s.segment_index for s in self.segments)
        if indices != list(range(len(self.segments))):
            raise ValueError(
                "segment_index must be contiguous starting at 0, with no gaps or duplicates"
            )

        participant_ids = {p.id for p in self.participants}
        unknown_speakers = {s.speaker_id for s in self.segments} - participant_ids
        if unknown_speakers:
            raise ValueError(f"segment speaker_id(s) not in participants: {sorted(unknown_speakers)}")

        max_end = max(s.end_ts for s in self.segments)
        if max_end > self.duration_seconds and "duration_mismatch" not in self.quality_flags:
            # frozen=True blocks normal attribute assignment; this is the documented escape
            # hatch for a validator that needs to derive a field from other fields.
            object.__setattr__(self, "quality_flags", [*self.quality_flags, "duration_mismatch"])

        return self
