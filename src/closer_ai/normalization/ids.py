"""Deterministic ID derivation for canonical Call records.

Same input always produces the same id (idempotent re-normalization); different input
never collides. IDs are derived only from non-PII identifiers (company_id, source,
source_id, segment index) — never from participant name or transcript text.

The hash input is built with `json.dumps` of a list, not string concatenation: JSON
unambiguously delimits each element (quotes + commas), so e.g. ("AB", "C") and ("A", "BC")
hash differently. Plain concatenation would not guarantee that.
"""
from __future__ import annotations

import hashlib
import json

_ID_LENGTH = 24


def _hash(parts: list[object]) -> str:
    canonical = json.dumps(parts, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:_ID_LENGTH]


def derive_call_id(company_id: str, source: str, source_id: str) -> str:
    return f"call_{_hash(['call', company_id, source, source_id])}"


def derive_segment_id(call_id: str, segment_index: int) -> str:
    return f"seg_{_hash(['segment', call_id, segment_index])}"
