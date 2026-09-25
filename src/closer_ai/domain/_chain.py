"""Linear append-only chain validation shared by MatchDecision, DealIdentityDecision and
OutcomeAssessment, plus the CAS append for the two manual/automatic decision chains.

A chain is valid only if it is one line: exactly one root, every other record supersedes a
record in the set, no record is superseded twice, and every record is reachable from the root.
Anything else (fork, dangling parent, several roots, cycle) is reported, never repaired —
`created_at`/`decided_at` never pick a winner.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable
from itertools import pairwise
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


# --- decision chains with automatic/manual authority (MatchDecision, DealIdentityDecision) ------


def authority_chain_head(
    records: Iterable[T],
    record_id: Callable[[T], str],
    parent_id: Callable[[T], str | None],
    decided_by: Callable[[T], str],
) -> tuple[T | None, bool]:
    """(head, ok). ok=False if not one linear chain, or an "automatic" record supersedes a
    "manual" one anywhere in the chain (only possible if something else wrote the history)."""
    chain = linear_chain(records, record_id, parent_id)
    if chain is None:
        return None, False
    for parent, child in pairwise(chain):
        if decided_by(parent) == "manual" and decided_by(child) == "automatic":
            return None, False
    return (chain[-1] if chain else None), True


def cas_append(
    history: list[T],
    new: T,
    *,
    record_id: Callable[[T], str],
    parent_id: Callable[[T], str | None],
    decided_by: Callable[[T], str],
    result: Callable[[T], object],
    conflict: type[Exception],
) -> list[T]:
    """Compare-and-swap append; the expected head is parent_id(new). Identical redelivery, or a
    re-decision with the same result that does not raise authority, leaves history unchanged.
    Same id + different payload raises ValueError; stale head, fork, or automatic over manual
    raises `conflict`."""
    head, ok = authority_chain_head(history, record_id, parent_id, decided_by)
    if not ok:
        raise conflict("history is not a linear chain; manual repair required")

    existing = next((r for r in history if record_id(r) == record_id(new)), None)
    if existing is not None:
        if existing != new:
            raise ValueError(f"same id with different payload: {record_id(new)}")
        return list(history)

    actual_head = record_id(head) if head is not None else None
    if parent_id(new) != actual_head:
        raise conflict(
            f"stale write: expected head {parent_id(new)!r}, actual head {actual_head!r}; "
            "reload and recompute"
        )

    if head is not None:
        upgrades_authority = decided_by(head) == "automatic" and decided_by(new) == "manual"
        if result(head) == result(new) and not upgrades_authority:
            return list(history)
        if decided_by(head) == "manual" and decided_by(new) == "automatic":
            raise conflict("current decision is manual; only another manual decision can replace it")
    return [*history, new]
