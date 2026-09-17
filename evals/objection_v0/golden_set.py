"""Synthetic golden set for objection extraction v0.

Each entry pairs a synthetic `Call` with the `ObjectionEvent`s a correct extractor should
produce for it (an empty tuple for true negatives). Expected events are built the same way
the reference extractor builds them — `derive_objection_id` against the call's own segment
ids — so the golden set never hardcodes an id that could drift from the fixture module.

100% synthetic, no real client data (reuses `tests/fixtures/synthetic_objection_calls.py`).
See docs/agents/tasks/objection-event-v0.md and this evaluator's design-phase report for the
metric rationale behind why these specific cases are here.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tests" / "fixtures"))

from synthetic_objection_calls import (
    call_ambiguous_phrasing_not_detected,
    call_closer_only_objection_like_language,
    call_minimal_valid,
    call_multi_objection_different_categories,
    call_no_objection,
    call_objection_split_across_segments,
    call_same_category_repeated_different_segments,
    call_same_category_twice_in_one_segment,
    call_single_objection,
)

from closer_ai.domain.objection import ObjectionEvent, derive_objection_id
from closer_ai.normalization.models import Call


@dataclass(frozen=True)
class GoldenEntry:
    name: str
    call: Call
    expected: tuple[ObjectionEvent, ...]


def _expected(call: Call, segment_index: int, category: str) -> ObjectionEvent:
    segment_id = call.segments[segment_index].segment_id
    return ObjectionEvent(
        objection_id=derive_objection_id(call.call_id, segment_id, category),
        call_id=call.call_id,
        segment_id=segment_id,
        category=category,
    )


def build_golden_set() -> list[GoldenEntry]:
    no_objection = call_no_objection()
    single = call_single_objection()
    multi = call_multi_objection_different_categories()
    repeated = call_same_category_repeated_different_segments()
    dup_in_segment = call_same_category_twice_in_one_segment()
    closer_only = call_closer_only_objection_like_language()
    ambiguous = call_ambiguous_phrasing_not_detected()
    split = call_objection_split_across_segments()
    minimal = call_minimal_valid()

    return [
        # True negative: no objection anywhere in the call.
        GoldenEntry("no_objection", no_objection, ()),
        # Single clear objection, single category.
        GoldenEntry("single_objection", single, (_expected(single, 1, "price"),)),
        # Multiple objections, different categories, different segments.
        GoldenEntry(
            "multi_objection_different_categories",
            multi,
            (
                _expected(multi, 1, "timing_priority"),
                _expected(multi, 3, "trust_authority"),
            ),
        ),
        # Same category restated in a different segment -> two distinct events.
        GoldenEntry(
            "same_category_repeated_different_segments",
            repeated,
            (
                _expected(repeated, 0, "price"),
                _expected(repeated, 2, "price"),
            ),
        ),
        # Same category, two keyword hits, same segment -> collapses to one event.
        GoldenEntry(
            "same_category_twice_in_one_segment",
            dup_in_segment,
            (_expected(dup_in_segment, 0, "price"),),
        ),
        # True negative: objection-shaped language spoken only by the closer (role trap).
        GoldenEntry("closer_only_objection_language", closer_only, ()),
        # True negative (documented recall gap): near-miss phrasing, not an exact keyword.
        GoldenEntry("ambiguous_phrasing_not_detected", ambiguous, ()),
        # True negative (documented limitation): objection phrase split across segments.
        GoldenEntry("objection_split_across_segments", split, ()),
        # True negative: minimal valid call, no objection language.
        GoldenEntry("minimal_valid_call", minimal, ()),
    ]
