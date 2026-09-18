"""Domain contracts for AI Closer: entities extracted from a canonical Call, plus the
Deal-level commercial model and Call<->Deal matching contract.

See docs/domain/OBJECTION_MODEL.md for ObjectionEvent's contract, and
docs/architecture/DATA_MODEL.md for Deal/CallDealMatch.
"""
from __future__ import annotations

from closer_ai.domain.deal import (
    DEAL_SCHEMA_VERSION,
    Deal,
    DealOutcome,
    Stage,
    StageEvent,
    derive_deal_id,
    derive_stage_event_id,
)
from closer_ai.domain.lead import LEAD_SCHEMA_VERSION, Lead, derive_lead_id
from closer_ai.domain.matching import (
    MATCHING_SCHEMA_VERSION,
    CallDealMatch,
    CallDealMatcher,
    ConfidenceLevel,
    EvidenceSignal,
    ExactExternalIdMatcher,
    MatchEvidence,
    MatchMethod,
    MatchStatus,
    derive_call_deal_match_id,
)
from closer_ai.domain.objection import (
    OBJECTION_SCHEMA_VERSION,
    ObjectionCategory,
    ObjectionEvent,
    derive_objection_id,
)

__all__ = [
    "DEAL_SCHEMA_VERSION",
    "LEAD_SCHEMA_VERSION",
    "MATCHING_SCHEMA_VERSION",
    "OBJECTION_SCHEMA_VERSION",
    "CallDealMatch",
    "CallDealMatcher",
    "ConfidenceLevel",
    "Deal",
    "DealOutcome",
    "EvidenceSignal",
    "ExactExternalIdMatcher",
    "Lead",
    "MatchEvidence",
    "MatchMethod",
    "MatchStatus",
    "ObjectionCategory",
    "ObjectionEvent",
    "Stage",
    "StageEvent",
    "derive_call_deal_match_id",
    "derive_deal_id",
    "derive_lead_id",
    "derive_objection_id",
    "derive_stage_event_id",
]
