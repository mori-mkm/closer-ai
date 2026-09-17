"""Domain contracts for AI Closer: entities extracted from a canonical Call.

See docs/domain/OBJECTION_MODEL.md for ObjectionEvent's contract.
"""
from __future__ import annotations

from closer_ai.domain.objection import (
    OBJECTION_SCHEMA_VERSION,
    ObjectionCategory,
    ObjectionEvent,
    derive_objection_id,
)

__all__ = [
    "OBJECTION_SCHEMA_VERSION",
    "ObjectionCategory",
    "ObjectionEvent",
    "derive_objection_id",
]
