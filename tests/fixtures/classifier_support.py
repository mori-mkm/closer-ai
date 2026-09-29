"""Test doubles for the objection classifier runner. Synthetic only; not a production provider.

`ScriptedClassificationProvider` returns pre-written responses in order (or raises a scripted
exception) and records every prompt it received. `synthetic_price_call()` builds a small
fictitious canonical Call through `normalize_call`.
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from closer_ai.normalization import Call, normalize_call


class ScriptedClassificationProvider:
    name = "scripted"

    def __init__(self, *responses: Mapping[str, Any] | Exception, model: str = "test-model") -> None:
        self.model = model
        self._responses = list(responses)
        self.prompts: list[str] = []

    def classify(self, prompt: str) -> Mapping[str, Any]:
        self.prompts.append(prompt)
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


_PARTICIPANTS = [
    {"id": "p-closer", "name": None, "role": "closer"},
    {"id": "p-lead", "name": None, "role": "lead"},
]

PRICE_CALL_TEXTS = [
    ("p-closer", "O plano anual fica em 18 mil."),
    ("p-lead", "Gostei, mas não temos verba para isso neste ano."),
    ("p-closer", "Podemos parcelar em doze vezes."),
    ("p-lead", "Parcelado ainda passa do que a gente pode gastar."),
    ("p-closer", "Entendo. Vamos ver a agenda de treinamento?"),
]


def synthetic_call(texts: list[tuple[str, str]] = PRICE_CALL_TEXTS, source_id: str = "clf-1") -> Call:
    segments = [
        {"speaker_id": who, "start_ts": 10.0 * i, "end_ts": 10.0 * i + 5.0, "text": text}
        for i, (who, text) in enumerate(texts)
    ]
    return normalize_call(
        {
            "company_id": "synthco-001",
            "source": "synthetic",
            "source_id": source_id,
            "occurred_at": datetime(2026, 1, 15, 14, 0, tzinfo=UTC),
            "duration_seconds": 10.0 * len(texts) + 5.0,
            "closer_id": "p-closer",
            "participants": [dict(p) for p in _PARTICIPANTS],
            "segments": segments,
            "quality_flags": [],
        }
    )


def episode(**overrides: Any) -> dict[str, Any]:
    """A well-formed episode dict; override fields per test."""
    base: dict[str, Any] = {
        "prediction_id": "p1",
        "objection_segment_ids": [],
        "context_segment_ids": [],
        "category_status": "PRESENT",
        "category": "PRICE_BUDGET",
        "category_candidates": [],
        "reaction_status": "PRESENT",
        "reaction": "REJECT",
        "reaction_candidates": [],
        "resolution_status": "unresolved",
        "summary": "Lead says there is no budget this year and the installments still exceed it.",
    }
    base.update(overrides)
    return base


def response(*episodes: dict[str, Any], call_detection: str | None = None,
             uncertain_spans: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "call_detection": call_detection or ("OBJECTIONS_FOUND" if episodes else "NO_OBJECTION"),
        "episodes": list(episodes),
        "uncertain_spans": uncertain_spans or [],
    }
