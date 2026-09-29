"""Integration: synthetic canonical Call -> E2 prompt (real Knowledge Base) -> scripted provider
-> parsed predictions -> deterministic validation -> ClassificationRun. No network, no real LLM."""
from __future__ import annotations

from pathlib import Path

from classifier_support import ScriptedClassificationProvider, episode, response, synthetic_call

from closer_ai.ai.knowledge_context import CONCEPT_ORDER, CONTEXT_HEADER
from closer_ai.ai.objection_classifier import classify_call

KB = Path(__file__).resolve().parents[2] / "docs" / "knowledge" / "sales" / "objections"


def test_e2_end_to_end_with_scripted_provider():
    call = synthetic_call()
    s = [seg.segment_id for seg in call.segments]
    provider = ScriptedClassificationProvider(
        response(episode(objection_segment_ids=[s[1]], context_segment_ids=[s[2], s[3]])),
        model="scripted-e2",
    )
    run = classify_call(call, "E2", provider, knowledge_root=KB, knowledge_git_sha="0" * 40)

    assert len(provider.prompts) == 1
    prompt = provider.prompts[0]
    assert prompt.index("FACTS FROM CALL") < prompt.index(CONTEXT_HEADER) < prompt.index("OUTPUT REQUIREMENTS")
    assert run.valid, run.validation_errors
    assert (run.arm, run.provider, run.model) == ("E2", "scripted", "scripted-e2")
    assert run.call_detection == "OBJECTIONS_FOUND"
    [ep] = run.episodes
    assert (ep.anchor_segment_id, ep.category, ep.resolution_status) == (s[1], "PRICE_BUDGET", "unresolved")
    assert run.knowledge_sha256 and len(run.knowledge_concept_versions) == len(CONCEPT_ORDER)
    assert run.knowledge_git_sha == "0" * 40
