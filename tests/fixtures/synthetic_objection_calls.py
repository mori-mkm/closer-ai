"""Fully synthetic, fictitious `Call` fixtures for ObjectionEvent tests/evals. No real
client data of any kind.

Built on `closer_ai.normalization.normalize_call()`, following the raw-dict-then-normalize
pattern in `tests/fixtures/synthetic_calls.py`, so every call returned here is an
already-validated, id-bearing `closer_ai.normalization.Call`.

Keyword phrases used below are taken verbatim from `_KEYWORDS` in
`closer_ai.ai.objection_extraction.RuleBasedObjectionExtractor` so expectations are exact,
not approximate. Where a text is deliberately NOT meant to match, that is called out in the
function's docstring.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from closer_ai.normalization import Call, normalize_call

_PARTICIPANTS: list[dict[str, Any]] = [
    {"id": "participant-closer", "name": "Ana Synthetic", "role": "closer"},
    {"id": "participant-lead", "name": "Bruno Synthetic", "role": "lead"},
]


def _raw(source_id: str, segments: list[dict[str, Any]], **overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "company_id": "synthco-001",
        "source": "synthetic",
        "source_id": source_id,
        "occurred_at": datetime(2026, 1, 15, 14, 0, tzinfo=UTC),
        "duration_seconds": max((s["end_ts"] for s in segments), default=1.0) + 5.0,
        "closer_id": "participant-closer",
        "participants": [dict(p) for p in _PARTICIPANTS],
        "segments": segments,
        "quality_flags": [],
    }
    base.update(overrides)
    return base


def call_no_objection() -> Call:
    """True negative: small talk / agreement only, no objection language anywhere."""
    segments = [
        {
            "speaker_id": "participant-closer",
            "start_ts": 0.0,
            "end_ts": 4.0,
            "text": "Oi Bruno, tudo bem? Vamos falar sobre o plano.",
        },
        {
            "speaker_id": "participant-lead",
            "start_ts": 4.5,
            "end_ts": 9.0,
            "text": "Tudo ótimo! Pode explicar como funciona.",
        },
        {
            "speaker_id": "participant-closer",
            "start_ts": 9.5,
            "end_ts": 15.0,
            "text": "Claro, funciona assim...",
        },
        {
            "speaker_id": "participant-lead",
            "start_ts": 15.5,
            "end_ts": 19.0,
            "text": "Faz sentido, obrigado pela explicação.",
        },
    ]
    return normalize_call(_raw("synth-obj-no-objection", segments))


def call_single_objection() -> Call:
    """One clear, single-category objection ('price') in one lead segment (index 1)."""
    segments = [
        {
            "speaker_id": "participant-closer",
            "start_ts": 0.0,
            "end_ts": 4.0,
            "text": "Esse é o investimento do programa completo.",
        },
        {
            "speaker_id": "participant-lead",
            "start_ts": 4.5,
            "end_ts": 9.0,
            "text": "Nossa, tá caro pra mim agora.",
        },
    ]
    return normalize_call(_raw("synth-obj-single", segments))


def call_multi_objection_different_categories() -> Call:
    """Two objections, different categories, different segments: 'timing_priority' at
    index 1, 'trust_authority' at index 3."""
    segments = [
        {
            "speaker_id": "participant-closer",
            "start_ts": 0.0,
            "end_ts": 4.0,
            "text": "Podemos começar essa semana?",
        },
        {
            "speaker_id": "participant-lead",
            "start_ts": 4.5,
            "end_ts": 9.0,
            "text": "Não tenho tempo essa semana, muita coisa acontecendo.",
        },
        {
            "speaker_id": "participant-closer",
            "start_ts": 9.5,
            "end_ts": 13.0,
            "text": "Entendo, e sobre a decisão em si?",
        },
        {
            "speaker_id": "participant-lead",
            "start_ts": 13.5,
            "end_ts": 18.0,
            "text": "Preciso pensar e falar com meu sócio antes.",
        },
    ]
    return normalize_call(_raw("synth-obj-multi-category", segments))


def call_same_category_repeated_different_segments() -> Call:
    """Same category ('price') raised twice, in two different lead segments (index 0 and
    index 2) — must yield two distinct ObjectionEvents (different segment_id => different
    objection_id), per the dedup rule in docs/domain/OBJECTION_MODEL.md ("IDs e dedup")."""
    segments = [
        {
            "speaker_id": "participant-lead",
            "start_ts": 0.0,
            "end_ts": 4.0,
            "text": "Tá caro pra mim nesse momento.",
        },
        {
            "speaker_id": "participant-closer",
            "start_ts": 4.5,
            "end_ts": 9.0,
            "text": "Entendo, deixa eu te mostrar as opções de parcelamento.",
        },
        {
            "speaker_id": "participant-lead",
            "start_ts": 9.5,
            "end_ts": 14.0,
            "text": "Mesmo parcelado, ainda não tenho orçamento pra isso.",
        },
    ]
    return normalize_call(_raw("synth-obj-repeat-price", segments))


def call_same_category_twice_in_one_segment() -> Call:
    """Two 'price' keyword hits inside the SAME lead segment (index 0) — must collapse to
    exactly one ObjectionEvent (same segment + same category => same objection_id)."""
    segments = [
        {
            "speaker_id": "participant-lead",
            "start_ts": 0.0,
            "end_ts": 6.0,
            "text": "Tá caro e também não tenho orçamento pra isso agora.",
        },
    ]
    return normalize_call(_raw("synth-obj-dup-in-segment", segments))


def call_closer_only_objection_like_language() -> Call:
    """Objection-shaped keywords appear ONLY in a closer segment (role-play / quoting the
    lead's likely pushback) — must yield zero events, since extraction is restricted to
    role='lead' segments (attribution trap flagged in the design-phase report)."""
    segments = [
        {
            "speaker_id": "participant-closer",
            "start_ts": 0.0,
            "end_ts": 6.0,
            "text": "As vezes o cliente pensa 'tá caro', mas o retorno compensa.",
        },
        {
            "speaker_id": "participant-lead",
            "start_ts": 6.5,
            "end_ts": 10.0,
            "text": "Faz sentido, concordo.",
        },
    ]
    return normalize_call(_raw("synth-obj-closer-quoting", segments))


def call_ambiguous_phrasing_not_detected() -> Call:
    """Near-miss phrasing a human might read as an objection ('vou pensar a respeito') that
    does NOT match any exact keyword in `_KEYWORDS` (only 'preciso pensar' does). Documents a
    known recall gap of the v0 keyword matcher — not a bug, an adversarial case the design
    phase flagged in advance."""
    segments = [
        {
            "speaker_id": "participant-lead",
            "start_ts": 0.0,
            "end_ts": 5.0,
            "text": "Vou pensar a respeito com calma.",
        },
    ]
    return normalize_call(_raw("synth-obj-ambiguous", segments))


def call_objection_split_across_segments() -> Call:
    """The phrase 'não tenho tempo' is split across a segment boundary ('Não tenho' /
    'tempo agora, foi mal') — neither segment contains the full keyword substring.
    Documents the single-segment evidence limitation (OBJECTION_MODEL.md "Edge cases
    considered and rejected" — multi-segment evidence explicitly deferred for v0)."""
    segments = [
        {
            "speaker_id": "participant-lead",
            "start_ts": 0.0,
            "end_ts": 2.0,
            "text": "Não tenho",
        },
        {
            "speaker_id": "participant-lead",
            "start_ts": 2.1,
            "end_ts": 5.0,
            "text": "tempo agora, foi mal.",
        },
    ]
    return normalize_call(_raw("synth-obj-split-segment", segments))


def call_minimal_valid() -> Call:
    """Lower bound: a single participant (lead), a single segment, no objection language."""
    segments = [
        {"speaker_id": "participant-lead", "start_ts": 0.0, "end_ts": 1.0, "text": "Oi."},
    ]
    return normalize_call(
        _raw(
            "synth-obj-minimal",
            segments,
            participants=[{"id": "participant-lead", "name": None, "role": "lead"}],
            closer_id=None,
        )
    )
