"""Agro/Zoom raw-call ingestion: parse a first-hypothesis Zoom export shape into the
dict contract closer_ai.normalization.normalize.normalize_call() expects.

See parser.py for the field-by-field mapping and quality-flag semantics.
"""
from closer_ai.ingestion.agro.models import AgroParseResult, AgroRawCall
from closer_ai.ingestion.agro.parser import (
    AgroParseError,
    normalize_agro_call,
    parse_agro_call,
)

__all__ = [
    "AgroParseError",
    "AgroParseResult",
    "AgroRawCall",
    "normalize_agro_call",
    "parse_agro_call",
]
