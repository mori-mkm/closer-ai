"""Agro/Zoom raw call -> input dict for `closer_ai.normalization.normalize.normalize_call`.

Pipeline:

    AgroRawCall (validated source shape)
        -> parse_agro_call()
        -> AgroParseResult.raw_input  (dict compatible with normalize_call())
        -> normalize_call()
        -> Call

`parse_agro_call` never invents data. A missing/malformed field either becomes a
quality flag (recoverable — the field is dropped or estimated) or an `AgroParseError`
(the call cannot become a valid `Call` at all: no stable identity, no timestamp, or a
transcript with zero usable segments). Quality flags:

- missing_transcript: the `transcript` field itself was not provided (None).
- empty_transcript: `transcript` was provided but no usable segment survived parsing.
- missing_participants: the `participants` field was empty/absent; participants were
  reconstructed from speaker labels seen in the transcript instead.
- unresolved_speaker: a transcript entry's speaker label did not match any known
  participant (missing, or present but not a usable string), or a `participants`
  entry's label/name/id was present but not a usable string. Either way, the entry
  is not silently dropped — a placeholder participant (role "unknown") is
  synthesized so the evidence is preserved, just unattributed.
- missing_timestamp: a transcript entry was missing `start`/`end` and was dropped.
- missing_duration: `duration_seconds` was absent; estimated from the maximum
  `end_ts` across the parsed segments (not the last segment in list order — the
  two coincide in a chronological transcript, but crosstalk/out-of-order input
  would not, and this schema explicitly allows both).
- transcript_parse_error: a transcript entry was structurally unusable (not a mapping,
  blank/non-string text, or `end <= start`) and was dropped.
- metadata_incomplete: descriptive metadata (topic/transcript_source/zoom_summary) was
  missing, or a `closer` label was given but did not resolve to any known participant
  — informational only, never blocks output. `closer` simply absent (None) does NOT
  raise this flag: "we were never told" and "we were told and couldn't find them" are
  different signals, and only the latter indicates something went wrong upstream.
- participant_id_collision: two different raw labels (participants entries, or a
  transcript speaker label against an already-known participant) normalized via
  `_slugify` to the same participant id. KNOWN LIMITATION: participant identity in
  this hypothesis format is name-based, not backed by a stable source id (Zoom
  participant UUID, email, ...) — see docs/domain/AGRO_INGESTION_CONTRACT.md. This
  flag makes the resulting merge/attribution visible for manual triage; it does not
  (and, without a stable id from the real source, cannot safely) resolve it.

All flags end up in `AgroParseResult.raw_input["quality_flags"]`, so they flow
straight into `Call.quality_flags` via the existing mechanism — no schema change.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

from pydantic import ValidationError

from closer_ai.ingestion.agro.models import AgroParseResult, AgroRawCall
from closer_ai.normalization.models import Call
from closer_ai.normalization.normalize import normalize_call

FLAG_MISSING_TRANSCRIPT = "missing_transcript"
FLAG_EMPTY_TRANSCRIPT = "empty_transcript"
FLAG_MISSING_PARTICIPANTS = "missing_participants"
FLAG_UNRESOLVED_SPEAKER = "unresolved_speaker"
FLAG_MISSING_TIMESTAMP = "missing_timestamp"
FLAG_MISSING_DURATION = "missing_duration"
FLAG_TRANSCRIPT_PARSE_ERROR = "transcript_parse_error"
FLAG_METADATA_INCOMPLETE = "metadata_incomplete"
FLAG_PARTICIPANT_ID_COLLISION = "participant_id_collision"


class AgroParseError(Exception):
    """Raised only when a raw Agro/Zoom call cannot become a valid `Call` at all:
    missing/blank meeting_id, missing or non-tz-aware occurred_at, a transcript with
    zero usable segments, or a `duration_seconds` that is present but not positive
    (a missing duration is recoverable — see FLAG_MISSING_DURATION below — but a
    present, invalid one is a source data error, not something to estimate around).
    Anything else recoverable becomes a quality flag instead of raising."""


def _add_flag(flags: list[str], flag: str) -> None:
    if flag not in flags:
        flags.append(flag)


def _slugify(label: str) -> str:
    normalized = unicodedata.normalize("NFKD", label).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "_", normalized.lower()).strip("_")
    return slug or "unknown_speaker"


def _as_str(value: Any) -> str | None:
    """A `dict[str, Any]` entry from the source is untyped by design (we don't control
    the real Zoom/Agro shape yet). A truthy value that isn't a usable string (an int,
    a list, a nested dict, ...) is source data we can't safely turn into a label or
    slugify — treat it exactly like "missing", never pass it to `_slugify`."""
    return value if isinstance(value, str) and value.strip() else None


def _find_participant(participants: list[dict[str, Any]], pid: str) -> dict[str, Any] | None:
    return next((p for p in participants if p["id"] == pid), None)


def _register_participant_or_flag_collision(
    participants: list[dict[str, Any]],
    participant_ids: set[str],
    flags: list[str],
    *,
    pid: str,
    label: str,
    role: str = "unknown",
) -> None:
    """Adds a new participant for `pid`, or — if `pid` is already taken by a
    participant registered under a *different* raw label — flags the collision
    instead of silently dropping or misattributing the new one."""
    existing = _find_participant(participants, pid)
    if existing is None:
        participant_ids.add(pid)
        participants.append({"id": pid, "name": label, "role": role})
        return
    if existing["name"] not in (None, label):
        _add_flag(flags, FLAG_PARTICIPANT_ID_COLLISION)


def _parse_participants(
    raw_participants: list[dict[str, Any]] | None, flags: list[str]
) -> tuple[list[dict[str, Any]], set[str]]:
    if not raw_participants:
        _add_flag(flags, FLAG_MISSING_PARTICIPANTS)
        return [], set()

    participants: list[dict[str, Any]] = []
    participant_ids: set[str] = set()
    for entry in raw_participants:
        label = _as_str(entry.get("label")) or _as_str(entry.get("name")) or _as_str(entry.get("id"))
        if not label:
            continue
        pid = _slugify(label)
        name = _as_str(entry.get("name")) or label
        role = entry.get("role") or "unknown"
        _register_participant_or_flag_collision(
            participants, participant_ids, flags, pid=pid, label=name, role=role
        )

    if not participants:
        _add_flag(flags, FLAG_MISSING_PARTICIPANTS)
    return participants, participant_ids


def _parse_transcript(
    raw_transcript: list[dict[str, Any]] | None,
    participants: list[dict[str, Any]],
    participant_ids: set[str],
) -> tuple[list[dict[str, Any]], list[str]]:
    flags: list[str] = []

    if raw_transcript is None:
        _add_flag(flags, FLAG_MISSING_TRANSCRIPT)
        return [], flags
    if not raw_transcript:
        _add_flag(flags, FLAG_EMPTY_TRANSCRIPT)
        return [], flags

    segments: list[dict[str, Any]] = []
    for entry in raw_transcript:
        if not isinstance(entry, dict):
            _add_flag(flags, FLAG_TRANSCRIPT_PARSE_ERROR)
            continue

        text = entry.get("text")
        if not isinstance(text, str) or not text.strip():
            _add_flag(flags, FLAG_TRANSCRIPT_PARSE_ERROR)
            continue

        start = entry.get("start")
        end = entry.get("end")
        if not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
            _add_flag(flags, FLAG_MISSING_TIMESTAMP)
            continue
        if end <= start:
            _add_flag(flags, FLAG_TRANSCRIPT_PARSE_ERROR)
            continue

        label = _as_str(entry.get("speaker"))
        if not label:
            # missing, or present but not a usable string (e.g. a numeric id, a
            # nested object) — same bucket, we can't attribute it to anyone by name
            _add_flag(flags, FLAG_UNRESOLVED_SPEAKER)
            speaker_id = "unknown_speaker"
            if speaker_id not in participant_ids:
                participant_ids.add(speaker_id)
                participants.append({"id": speaker_id, "name": None, "role": "unknown"})
        else:
            speaker_id = _slugify(label)
            if speaker_id not in participant_ids:
                _add_flag(flags, FLAG_UNRESOLVED_SPEAKER)
                participant_ids.add(speaker_id)
                participants.append({"id": speaker_id, "name": label, "role": "unknown"})
            else:
                existing = _find_participant(participants, speaker_id)
                if existing is not None and existing["name"] not in (None, label):
                    _add_flag(flags, FLAG_PARTICIPANT_ID_COLLISION)

        segments.append(
            {"speaker_id": speaker_id, "start_ts": float(start), "end_ts": float(end), "text": text}
        )

    if not segments:
        _add_flag(flags, FLAG_EMPTY_TRANSCRIPT)

    return segments, flags


def _resolve_closer(
    closer_label: str | None, participants: list[dict[str, Any]], participant_ids: set[str]
) -> str | None:
    if not closer_label:
        return None
    pid = _slugify(closer_label)
    if pid not in participant_ids:
        return None
    participant = _find_participant(participants, pid)
    if participant is None:
        return None
    if participant["role"] not in ("unknown", "closer"):
        # `closer` resolves (by slug) to a participant already known as something
        # else (e.g. "lead") — either a source-data conflict or a slug collision
        # (see FLAG_PARTICIPANT_ID_COLLISION). Never silently overwrite an existing
        # role or fabricate a resolution: treat as unresolved, same as no match at
        # all — the caller flags metadata_incomplete for that.
        return None
    participant["role"] = "closer"
    return pid


def parse_agro_call(
    raw: dict[str, Any], *, company_id: str, source: str = "agro_zoom"
) -> AgroParseResult:
    try:
        parsed = AgroRawCall.model_validate(raw)
    except ValidationError as exc:
        # Deliberately built from exc.errors() (field path + message only), never
        # str(exc)/exc itself — pydantic's default rendering echoes the rejected
        # input value per field and links to https://errors.pydantic.dev/..., either
        # of which could put source content in an exception message meant to be safe
        # to log (see docs/domain/AGRO_INGESTION_CONTRACT.md — no PII in logs).
        fields = ", ".join(".".join(str(part) for part in error["loc"]) for error in exc.errors())
        raise AgroParseError(f"invalid Agro raw call structure (fields: {fields})") from exc

    flags: list[str] = []

    participants, participant_ids = _parse_participants(parsed.participants, flags)
    segments, transcript_flags = _parse_transcript(parsed.transcript, participants, participant_ids)
    for flag in transcript_flags:
        _add_flag(flags, flag)

    if not segments:
        raise AgroParseError(f"meeting {parsed.meeting_id}: transcript has no usable segments")

    if parsed.occurred_at is None:
        raise AgroParseError(f"meeting {parsed.meeting_id}: missing occurred_at")
    if parsed.occurred_at.tzinfo is None:
        raise AgroParseError(f"meeting {parsed.meeting_id}: occurred_at must be timezone-aware")

    duration_seconds = parsed.duration_seconds
    if duration_seconds is not None and duration_seconds <= 0:
        raise AgroParseError(
            f"meeting {parsed.meeting_id}: duration_seconds must be positive, "
            f"got {duration_seconds!r}"
        )
    if duration_seconds is None:
        duration_seconds = max(segment["end_ts"] for segment in segments)
        _add_flag(flags, FLAG_MISSING_DURATION)

    closer_id = _resolve_closer(parsed.closer, participants, participant_ids)
    if parsed.closer and closer_id is None:
        _add_flag(flags, FLAG_METADATA_INCOMPLETE)
    if parsed.transcript_source is None or parsed.zoom_summary is None or parsed.topic is None:
        _add_flag(flags, FLAG_METADATA_INCOMPLETE)

    raw_input = {
        "company_id": company_id,
        "source": source,
        "source_id": parsed.meeting_id,
        "occurred_at": parsed.occurred_at,
        "duration_seconds": duration_seconds,
        "closer_id": closer_id,
        "participants": [
            {"id": p["id"], "name": p["name"], "role": p["role"]} for p in participants
        ],
        "segments": segments,
        "quality_flags": flags,
    }

    metadata = {
        "meeting_id": parsed.meeting_id,
        "topic": parsed.topic,
        "transcript_source": parsed.transcript_source,
        "zoom_summary": parsed.zoom_summary,
        "raw_metadata": dict(parsed.metadata or {}),
    }

    return AgroParseResult(raw_input=raw_input, quality_flags=list(flags), metadata=metadata)


def normalize_agro_call(
    raw: dict[str, Any], *, company_id: str, source: str = "agro_zoom"
) -> tuple[Call, AgroParseResult]:
    result = parse_agro_call(raw, company_id=company_id, source=source)
    try:
        call = normalize_call(result.raw_input)
    except ValidationError as exc:
        # Defense-in-depth, not the primary contract: parse_agro_call() already
        # guards the invariants it knows about (span, text, tz-awareness, duration),
        # but participants[].role comes straight from an untyped source field and is
        # only validated by Call's own Literal — this is the one remaining path a
        # pydantic.ValidationError could otherwise leak through undocumented.
        raise AgroParseError(
            f"meeting {result.metadata['meeting_id']}: parsed input rejected by "
            f"normalize_call()"
        ) from exc
    return call, result
