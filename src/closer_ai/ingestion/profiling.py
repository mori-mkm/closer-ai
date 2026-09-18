"""Privacy-safe structural profiler for raw source files, before any parser/adapter exists.

See docs/data/REAL_CALL_VALIDATION_KIT.md. This is deliberately source-agnostic: it does not
know about `AgroRawCall`, Zoom, or any specific vendor shape. Its only job is to describe the
STRUCTURE of a local file (format, field names, counts) safely enough to reason about before
deciding how — or whether — to adapt `closer_ai.ingestion.agro` (or a future sibling module)
to it.

Design decisions worth knowing:

- Never returns field VALUES, only names, types, and counts. Timestamp-like and speaker-like
  fields are detected by KEY NAME heuristics only (never by inspecting/echoing the value). The
  one deliberate exception — counting *distinct* values under a speaker-like key — never
  surfaces the values themselves, only `len(set(...))`; this is explicitly allowed by the task
  this module was built for ("number of speaker identifiers" is a safe structural fact, the
  identifiers themselves are not).
- **Key names are not automatically trusted as safe either.** A JSON object's own top-level
  keys can themselves BE the sensitive data — e.g. `{"maria@x.com": {...}, "joao@x.com": {...}}`,
  a participant/attendee map keyed by identity rather than a list of records. Any key (JSON or
  CSV header) that matches an email- or phone-shaped pattern is redacted to
  `<redacted_key_N>` before it can appear anywhere in the report (`_sanitize_keys`). This is a
  pattern-based heuristic, not a general PII detector — a key that's a bare human name (e.g.
  `"Maria Silva": {...}`) would not be caught by it. Same class of known, documented gap as
  `MatchEvidence.detail`'s PII convention (`docs/context/TECH_DEBT.md` TD-04): closes the
  concrete, reproducible risk, does not claim to close every risk.
- Filenames are not trusted either: a real filename could itself carry PII (e.g.
  "maria_silva_call.json"). `profile_file` never puts `path.name` in the returned profile —
  only a `safe_id`, which defaults to a stable, non-reversible hash of the path unless the
  caller supplies one (e.g. "sample_001").
- Unsupported/unrecognized formats never raise — they come back as a minimal profile with
  `format="unsupported:<ext>"` so profiling a whole directory never aborts on one odd file.
- Read/parse failures are caught and turned into a `notes` entry, never a raw exception message
  that could echo file content (same "safe to log" discipline already established in
  `closer_ai.ingestion.agro.parser`).
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_TIMESTAMP_KEY_HINTS = ("time", "date", "start", "end", "_at", "timestamp", "duration")
_SPEAKER_KEY_HINTS = ("speaker", "participant", "user", "host", "attendee")
_TRANSCRIPT_KEY_HINTS = ("transcript", "segments", "entries", "utterances", "lines")

_SUPPORTED_EXTENSIONS = {".json", ".csv", ".txt", ".vtt", ".srt"}

# A raw key/column-header that matches either of these IS the sensitive data (e.g. a
# participant map keyed by email), not a schema field name — see module docstring.
_EMAIL_LIKE_KEY = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE_LIKE_KEY = re.compile(r"^\+?[\d][\d\s\-().]{6,}$")


def _sanitize_keys(raw_keys: list[str]) -> tuple[dict[str, str], int]:
    """Maps every raw key to a safe-to-report name: itself, unless it looks like an email or
    phone number, in which case it becomes a redacted placeholder. Never returns the raw key
    for anything that matched. Returns (raw_key -> safe_key, redacted_count)."""
    mapping: dict[str, str] = {}
    redacted = 0
    for k in raw_keys:
        if _EMAIL_LIKE_KEY.match(k) or _PHONE_LIKE_KEY.match(k):
            redacted += 1
            mapping[k] = f"<redacted_key_{redacted}>"
        else:
            mapping[k] = k
    return mapping, redacted


@dataclass(frozen=True)
class StructuralProfile:
    """Safe-to-log/safe-to-commit structural summary of one raw source file. Never contains a
    field value, transcript line, filename, or any other content that could be PII."""

    safe_id: str
    format: str
    size_bytes: int
    encoding: str | None = None
    record_count: int | None = None
    keys: tuple[str, ...] = field(default_factory=tuple)
    field_types: dict[str, str] = field(default_factory=dict)
    null_counts: dict[str, int] = field(default_factory=dict)
    timestamp_like_fields: tuple[str, ...] = field(default_factory=tuple)
    transcript_segment_count: int | None = None
    speaker_identifier_count: int | None = None
    duration_field_present: bool = False
    notes: tuple[str, ...] = field(default_factory=tuple)


def _safe_id_for(path: Path) -> str:
    """Non-reversible id derived from the path string (not its content) — never the filename
    itself, which could carry PII (see module docstring)."""
    return f"file_{hashlib.sha256(str(path).encode('utf-8')).hexdigest()[:16]}"


def _detect_encoding(raw: bytes) -> str | None:
    # latin-1 successfully decodes every byte value, so it would otherwise mask genuinely
    # binary content (mp3, etc.) as "text" — an embedded null byte is a standard, cheap
    # heuristic for "this is not text at all", checked before the latin-1 fallback ever runs.
    if b"\x00" in raw:
        return None
    for candidate in ("utf-8", "latin-1"):
        try:
            raw.decode(candidate)
            return candidate
        except UnicodeDecodeError:
            continue
    return None


def _has_hint(key: str, hints: tuple[str, ...]) -> bool:
    lowered = key.lower()
    return any(hint in lowered for hint in hints)


def _profile_json_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    # raw_keys are used for all actual dict lookups below (record.get(k)); everything that
    # ends up in the returned profile uses key_map[k] instead — see _sanitize_keys and the
    # module docstring for why a raw key can itself be sensitive (e.g. an email-keyed map).
    raw_keys: list[str] = []
    for record in records:
        if isinstance(record, dict):
            for k in record:
                if k not in raw_keys:
                    raw_keys.append(k)

    key_map, redacted_count = _sanitize_keys(raw_keys)

    field_types: dict[str, str] = {}
    null_counts: dict[str, int] = {key_map[k]: 0 for k in raw_keys}
    for k in raw_keys:
        safe_k = key_map[k]
        seen_type: str | None = None
        for record in records:
            if not isinstance(record, dict):
                continue
            value = record.get(k)
            if value is None:
                null_counts[safe_k] += 1
                continue
            if seen_type is None:
                seen_type = type(value).__name__
        field_types[safe_k] = seen_type or "null"

    timestamp_like = tuple(key_map[k] for k in raw_keys if _has_hint(k, _TIMESTAMP_KEY_HINTS))
    duration_present = any(_has_hint(k, ("duration",)) for k in raw_keys)

    speaker_key = next((k for k in raw_keys if _has_hint(k, _SPEAKER_KEY_HINTS)), None)
    speaker_count = None
    if speaker_key is not None:
        # count of DISTINCT values only — never the values themselves (see module docstring)
        speaker_count = len(
            {str(r.get(speaker_key)) for r in records if isinstance(r, dict) and r.get(speaker_key) is not None}
        )

    transcript_count = None
    for record in records:
        if not isinstance(record, dict):
            continue
        for k, v in record.items():
            if _has_hint(k, _TRANSCRIPT_KEY_HINTS) and isinstance(v, list):
                transcript_count = len(v)
                break
        if transcript_count is not None:
            break

    notes: tuple[str, ...] = ()
    if redacted_count:
        message = (
            f"{redacted_count} top-level key(s) matched an email/phone pattern and were "
            "redacted — this may mean the object is keyed by identity rather than by schema "
            "field name; inspect structure manually before trusting keys/field_types"
        )
        notes = (message,)

    return {
        "record_count": len(records),
        "keys": tuple(key_map[k] for k in raw_keys),
        "field_types": field_types,
        "null_counts": null_counts,
        "timestamp_like_fields": timestamp_like,
        "duration_field_present": duration_present,
        "speaker_identifier_count": speaker_count,
        "transcript_segment_count": transcript_count,
        "notes": notes,
    }


def _profile_json(raw: bytes, encoding: str) -> dict[str, Any]:
    data = json.loads(raw.decode(encoding))
    if isinstance(data, list):
        return _profile_json_records([r for r in data if isinstance(r, dict)])
    if isinstance(data, dict):
        # a single-object export (one call, one deal, ...) — profile it as a 1-record set,
        # and also inspect any top-level list field as a nested transcript/segments container
        extra = _profile_json_records([data])
        for k, v in data.items():
            if _has_hint(k, _TRANSCRIPT_KEY_HINTS) and isinstance(v, list):
                nested_records = [r for r in v if isinstance(r, dict)]
                nested = _profile_json_records(nested_records)
                extra["transcript_segment_count"] = len(v)
                if extra.get("speaker_identifier_count") is None:
                    extra["speaker_identifier_count"] = nested["speaker_identifier_count"]
                break
        return extra
    return {"record_count": 1, "notes": ("top-level JSON value is a scalar, not an object/list",)}


def _profile_csv(raw: bytes, encoding: str) -> dict[str, Any]:
    text = raw.decode(encoding)
    reader = csv.DictReader(io.StringIO(text))
    raw_keys = tuple(reader.fieldnames or ())
    key_map, redacted_count = _sanitize_keys(list(raw_keys))

    null_counts = {key_map[k]: 0 for k in raw_keys}
    row_count = 0
    for row in reader:
        row_count += 1
        for k in raw_keys:
            if not (row.get(k) or "").strip():
                null_counts[key_map[k]] += 1
    timestamp_like = tuple(key_map[k] for k in raw_keys if _has_hint(k, _TIMESTAMP_KEY_HINTS))
    duration_present = any(_has_hint(k, ("duration",)) for k in raw_keys)
    notes: tuple[str, ...] = ()
    if redacted_count:
        message = (
            f"{redacted_count} column header(s) matched an email/phone pattern and were "
            "redacted — inspect structure manually before trusting keys/field_types"
        )
        notes = (message,)
    return {
        "record_count": row_count,
        "keys": tuple(key_map[k] for k in raw_keys),
        "field_types": {key_map[k]: "str" for k in raw_keys},  # CSV cells are all strings structurally
        "null_counts": null_counts,
        "timestamp_like_fields": timestamp_like,
        "duration_field_present": duration_present,
        "notes": notes,
    }


def _profile_cue_format(raw: bytes, encoding: str) -> dict[str, Any]:
    """VTT/SRT: count cue blocks by blank-line-separated blocks. Structural only — never reads
    cue text into the report."""
    text = raw.decode(encoding)
    blocks = [b for b in text.replace("\r\n", "\n").split("\n\n") if b.strip()]
    # VTT files start with a "WEBVTT" header block that isn't a cue
    cue_count = len(blocks)
    if text.strip().upper().startswith("WEBVTT") and cue_count > 0:
        cue_count -= 1
    return {"transcript_segment_count": max(cue_count, 0), "duration_field_present": True}


def _profile_txt(raw: bytes, encoding: str) -> dict[str, Any]:
    line_count = raw.decode(encoding).count("\n") + 1
    return {"record_count": line_count}


def profile_file(path: Path, *, safe_id: str | None = None) -> StructuralProfile:
    """Profile one local file's structure. Never reads the file into the returned object's
    content — see module docstring for the exact privacy guarantees."""
    resolved_safe_id = safe_id or _safe_id_for(path)
    size_bytes = path.stat().st_size
    suffix = path.suffix.lower()

    if suffix not in _SUPPORTED_EXTENSIONS:
        return StructuralProfile(
            safe_id=resolved_safe_id,
            format=f"unsupported:{suffix or 'no-extension'}",
            size_bytes=size_bytes,
            notes=("format not recognized by structural profiler — inspect manually",),
        )

    raw = path.read_bytes()
    encoding = _detect_encoding(raw)
    if encoding is None:
        return StructuralProfile(
            safe_id=resolved_safe_id,
            format=suffix.lstrip("."),
            size_bytes=size_bytes,
            notes=("could not decode as utf-8 or latin-1 — possibly binary",),
        )

    try:
        if suffix == ".json":
            extra = _profile_json(raw, encoding)
        elif suffix == ".csv":
            extra = _profile_csv(raw, encoding)
        elif suffix in (".vtt", ".srt"):
            extra = _profile_cue_format(raw, encoding)
        else:
            extra = _profile_txt(raw, encoding)
    except Exception as exc:  # noqa: BLE001 - deliberately broad: never leak content via a raw
        # traceback (same "safe to log" discipline as AgroParseError). Only the exception TYPE
        # name is safe to report; str(exc) could echo a parsed fragment of the file.
        return StructuralProfile(
            safe_id=resolved_safe_id,
            format=suffix.lstrip("."),
            size_bytes=size_bytes,
            encoding=encoding,
            notes=(f"failed to parse as {suffix.lstrip('.')}: {type(exc).__name__}",),
        )

    return StructuralProfile(
        safe_id=resolved_safe_id,
        format=suffix.lstrip("."),
        size_bytes=size_bytes,
        encoding=encoding,
        **extra,
    )


def profile_directory(directory: Path) -> list[StructuralProfile]:
    """Profile every file directly under `directory` (non-recursive), each with a stable
    per-directory sample id (`sample_001`, `sample_002`, ...) instead of the real filename."""
    files = sorted(p for p in directory.iterdir() if p.is_file())
    return [
        profile_file(p, safe_id=f"sample_{index:03d}") for index, p in enumerate(files, start=1)
    ]
