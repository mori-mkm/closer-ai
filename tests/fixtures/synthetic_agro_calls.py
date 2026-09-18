"""Fully synthetic, fictitious Agro/Zoom-shaped raw call data for tests. No real
client data of any kind.

Mirrors the (still-undecided, first-hypothesis) shape `closer_ai.ingestion.agro`
expects on input — see `parser.py`. `agro_raw_call()` returns a fresh, independent
dict every call (safe to mutate per test case); the other helpers layer a specific
gap on top of it (incomplete metadata, unresolved speaker, missing/empty transcript,
inconsistent timestamps).
"""
from __future__ import annotations

import copy
from datetime import UTC, datetime
from typing import Any

_BASE_AGRO_RAW_CALL: dict[str, Any] = {
    "meeting_id": "zoom-agro-0001",
    "topic": "AgroTalento — Reunião comercial",
    "occurred_at": datetime(2026, 2, 3, 13, 0, tzinfo=UTC),
    "duration_seconds": 620.0,
    "transcript_source": "zoom_vtt",
    "zoom_summary": "Cliente demonstrou interesse no plano anual.",
    "closer": "Ana Souza",
    "participants": [
        {"label": "Ana Souza", "role": "closer"},
        {"label": "Bruno Lima", "role": "lead"},
    ],
    "transcript": [
        {
            "speaker": "Ana Souza",
            "start": 0.0,
            "end": 8.0,
            "text": "Oi Bruno, tudo bem? Vamos falar do plano.",
        },
        {
            "speaker": "Bruno Lima",
            "start": 8.5,
            "end": 16.0,
            "text": "Tudo bem! Fiquei com uma dúvida sobre o prazo.",
        },
        {
            "speaker": "Ana Souza",
            "start": 16.0,
            "end": 30.0,
            "text": "Boa pergunta, deixa eu explicar como funciona.",
        },
    ],
    "metadata": {"recording_id": "rec-0001", "host_email": "ana@agrotalento.example"},
}


def agro_raw_call(**overrides: Any) -> dict[str, Any]:
    call = copy.deepcopy(_BASE_AGRO_RAW_CALL)
    call.update(overrides)
    return call


def agro_raw_call_incomplete_metadata(**overrides: Any) -> dict[str, Any]:
    """Case 2: metadata incompleta (topic/transcript_source/zoom_summary ausentes)."""
    call = agro_raw_call(**overrides)
    call["topic"] = None
    call["transcript_source"] = None
    call["zoom_summary"] = None
    call["metadata"] = {}
    return call


def agro_raw_call_unresolved_speaker(**overrides: Any) -> dict[str, Any]:
    """Case 3: participante extra falando no transcript sem estar em `participants`."""
    call = agro_raw_call(**overrides)
    call["transcript"] = [
        *call["transcript"],
        {
            "speaker": "Convidado Desconhecido",
            "start": 30.0,
            "end": 35.0,
            "text": "Uma pergunta rápida antes de encerrar.",
        },
    ]
    return call


def agro_raw_call_missing_transcript(**overrides: Any) -> dict[str, Any]:
    """Case 4a: campo `transcript` ausente (None)."""
    call = agro_raw_call(**overrides)
    call["transcript"] = None
    return call


def agro_raw_call_empty_transcript(**overrides: Any) -> dict[str, Any]:
    """Case 4b: campo `transcript` presente mas vazio."""
    call = agro_raw_call(**overrides)
    call["transcript"] = []
    return call


def agro_raw_call_inconsistent_timestamps(**overrides: Any) -> dict[str, Any]:
    """Case 5: duração ausente + entradas com timestamp invertido/ausente."""
    call = agro_raw_call(**overrides)
    call["duration_seconds"] = None
    call["transcript"] = [
        {"speaker": "Ana Souza", "start": 0.0, "end": 8.0, "text": "Oi Bruno, tudo bem?"},
        {
            "speaker": "Bruno Lima",
            "start": 8.5,
            "end": 8.0,
            "text": "entrada com timestamp invertido",
        },
        {"speaker": "Ana Souza", "start": None, "end": 20.0, "text": "sem timestamp de início"},
        {"speaker": "Bruno Lima", "start": 20.0, "end": 45.0, "text": "Combinado, obrigado!"},
    ]
    return call


def agro_raw_call_missing_participants(**overrides: Any) -> dict[str, Any]:
    """`participants` ausente — participantes precisam ser reconstruídos a partir dos
    speakers vistos no transcript."""
    call = agro_raw_call(**overrides)
    call["participants"] = None
    return call


def agro_raw_call_closer_not_resolved(**overrides: Any) -> dict[str, Any]:
    """`closer` aponta para um nome que não corresponde a nenhum participante/speaker
    conhecido na call — closer não pode ser identificado com segurança."""
    call = agro_raw_call(**overrides)
    call["closer"] = "Carlos Ausente Da Call"
    return call
