"""Fully synthetic, fictitious raw call data for tests. No real client data of any kind.

`raw_call()` returns a fresh, independent dict every call (safe to mutate per test case)
matching the shape documented in `closer_ai.normalization.normalize.normalize_call`.
"""
from __future__ import annotations

import copy
from datetime import UTC, datetime
from typing import Any

_BASE_RAW_CALL: dict[str, Any] = {
    "company_id": "synthco-001",
    "source": "synthetic",
    "source_id": "synth-call-0001",
    "occurred_at": datetime(2026, 1, 15, 14, 0, tzinfo=UTC),
    "duration_seconds": 30.0,
    "closer_id": "participant-closer",
    "participants": [
        {"id": "participant-closer", "name": "Ana Synthetic", "role": "closer"},
        {"id": "participant-lead", "name": "Bruno Synthetic", "role": "lead"},
    ],
    "segments": [
        {
            "speaker_id": "participant-closer",
            "start_ts": 0.0,
            "end_ts": 5.0,
            "text": "Oi Bruno, tudo bem? Vamos falar sobre o plano.",
        },
        {
            "speaker_id": "participant-lead",
            "start_ts": 5.5,
            "end_ts": 12.0,
            "text": "Tudo bem! Fiquei com uma dúvida sobre o prazo.",
        },
        {
            "speaker_id": "participant-closer",
            "start_ts": 12.0,
            "end_ts": 20.0,
            "text": "Boa pergunta, deixa eu explicar como funciona.",
        },
    ],
    "quality_flags": [],
}


def raw_call(**overrides: Any) -> dict[str, Any]:
    call = copy.deepcopy(_BASE_RAW_CALL)
    call.update(overrides)
    return call
