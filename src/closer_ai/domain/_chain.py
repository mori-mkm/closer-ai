"""Linear append-only chain validation shared by MatchDecision and OutcomeAssessment.

A chain is valid only if it is one line: exactly one root, every other record supersedes a
record in the set, no record is superseded twice, and every record is reachable from the root.
Anything else (fork, dangling parent, several roots, cycle) is reported, never repaired —
`created_at`/`decided_at` never pick a winner.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import TypeVar

T = TypeVar("T")


def linear_chain(
    records: Iterable[T], record_id: Callable[[T], str], parent_id: Callable[[T], str | None]
) -> list[T] | None:
    """Records ordered root -> head; [] for no records; None if not one linear chain.
    Raises ValueError for two records with the same id and different payload."""
    by_id: dict[str, T] = {}
    for record in records:
        rid = record_id(record)
        seen = by_id.get(rid)
        if seen is not None and seen != record:
            raise ValueError(f"same id with different payload: {rid}")
        by_id[rid] = record
    if not by_id:
        return []

    roots = [r for r in by_id.values() if parent_id(r) is None]
    child_of: dict[str, T] = {}
    for record in by_id.values():
        parent = parent_id(record)
        if parent is None:
            continue
        if parent not in by_id or parent in child_of:
            return None
        child_of[parent] = record
    if len(roots) != 1:
        return None

    chain = [roots[0]]
    while record_id(chain[-1]) in child_of:
        chain.append(child_of[record_id(chain[-1])])
    return chain if len(chain) == len(by_id) else None
