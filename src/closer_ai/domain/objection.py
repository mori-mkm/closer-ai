"""ObjectionEvent contract. See docs/domain/OBJECTION_MODEL.md for the conceptual model.

Validation decisions worth knowing (they're invariants, not obvious from field names):

- Frozen (immutable), same as Call/TranscriptSegment (`closer_ai.normalization.models`):
  once extracted and referenced by an eval run or a future Deal/Outcome linkage, it must not
  change under a reference already taken against it.
- Evidence is a single `segment_id` on the source `Call` — the whole segment, not a
  character-offset sub-span, and not a list of segments. Deliberate v0 scope decision, not
  an oversight: it keeps evidence grounding a single mechanical lookup ("does (call_id,
  segment_id) resolve to a real segment on a real call"), which is what the eval harness's
  grounding metric needs. Multi-segment evidence is deferred until a golden set shows a
  single segment is actually insufficient (most explicit objection utterances land in one
  turn).
- `category` is a closed, finite enum, not a free string: precision/recall against a golden
  set requires a fixed label set to compare against. The four named categories match the
  examples in docs/agents/tasks/objection-event-v0.md's blockers section (full taxonomy is a
  later task, see ROADMAP phase 3); `other` is the escape hatch so a real objection that
  doesn't fit the v0 set yet doesn't force an invalid record.
- `objection_id` is deterministic, derived from (call_id, segment_id, category) with the same
  technique `closer_ai.normalization.ids` uses for call_id/segment_id (sha256 over
  json.dumps of a list, not string concatenation, so element boundaries are unambiguous, no
  PII in the input). See `derive_objection_id` below.
- Unlike Call/TranscriptSegment (whose ids are supplied by the caller, e.g. normalize_call,
  and not re-checked by the model), ObjectionEvent's validator DOES check that the supplied
  objection_id matches derive_objection_id(call_id, segment_id, category). This is a
  deliberate departure from that convention: a Call's ids are ultimately rooted in an
  external source id, so re-deriving them inside the model would just duplicate the caller's
  work; an ObjectionEvent's identity is entirely a function of its own fields, so enforcing
  the derivation is free and buys a real guarantee (see next point).
- That derivation doubles as the dedup rule: restating the SAME category within the SAME
  segment is not a new event, it collapses to the same objection_id (idempotent
  re-extraction, no duplicate rows for one utterance). Restating it in a DIFFERENT segment
  (e.g. the lead raises price again ten minutes later) IS a new event, because segment_id
  differs — that's intentional: a new segment is new evidence, and repetition across
  segments is itself a signal (objection wasn't resolved) later analysis should be able to
  see.
- No `raised_by`/`speaker_role` field. Who said it is already resolvable via
  Call.segments[i].speaker_id -> Call.participants for the referenced segment; duplicating
  that here would be a second source of truth that could drift from the Call it points at.
  (By domain definition an objection is lead-expressed anyway, see docs/domain/GLOSSARY.md.)
- No `confidence` field in v0. The reference extractor (AI Engineer's scope) is a
  deterministic rule/keyword matcher, i.e. a binary match, not a graded score — a confidence
  field would just be a constant with no signal. Add it when a probabilistic/LLM extractor
  produces a real distribution to report.
- No `Deal`/`Outcome` reference. Intentionally deferred, see docs/product/MVP_SCOPE.md and
  the blockers section of docs/agents/tasks/objection-event-v0.md. Call<->Deal matching is a
  later roadmap phase.
"""
from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

OBJECTION_SCHEMA_VERSION = "1.0.0"

ObjectionCategory = Literal["price", "timing_priority", "trust_authority", "no_need", "other"]

_ID_LENGTH = 24


def derive_objection_id(call_id: str, segment_id: str, category: str) -> str:
    """Deterministic id for an ObjectionEvent.

    Same derivation technique as closer_ai.normalization.ids (sha256 over json.dumps of a
    list). Not imported from there: that module's hash helper is private (`_hash`) to it, so
    the pattern is reimplemented here rather than reaching into normalization's internals —
    normalization/** is a read-only dependency for this module.
    """
    canonical = json.dumps(
        ["objection", call_id, segment_id, category], ensure_ascii=True, separators=(",", ":")
    )
    return f"obj_{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:_ID_LENGTH]}"


class ObjectionEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: str = OBJECTION_SCHEMA_VERSION
    objection_id: str
    call_id: str
    segment_id: str
    category: ObjectionCategory

    @model_validator(mode="after")
    def _check_invariants(self) -> ObjectionEvent:
        if not self.call_id.strip():
            raise ValueError("call_id must not be empty")
        if not self.segment_id.strip():
            raise ValueError("segment_id must not be empty")

        expected_id = derive_objection_id(self.call_id, self.segment_id, self.category)
        if self.objection_id != expected_id:
            raise ValueError(
                "objection_id must be derive_objection_id(call_id, segment_id, category); "
                f"expected {expected_id!r}, got {self.objection_id!r}"
            )
        return self
