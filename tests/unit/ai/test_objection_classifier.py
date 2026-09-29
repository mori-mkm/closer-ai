"""Objection classifier runner v0.1: arm assembly, leakage boundary, validation, provider, digests.

Synthetic calls only; ScriptedClassificationProvider stands in for any LLM. Knowledge Context
Builder behavior itself is covered in test_knowledge_context.py and not re-tested here.
"""
from __future__ import annotations

import inspect
import re
import shutil
from pathlib import Path

import pytest
from classifier_support import (
    ScriptedClassificationProvider,
    episode,
    response,
    synthetic_call,
)

from closer_ai.ai.knowledge_context import CONCEPT_ORDER, CONTEXT_HEADER, build_knowledge_context
from closer_ai.ai.objection_classifier import (
    CATEGORY_LABELS,
    CLASSIFICATION_GUIDE,
    OUTPUT_REQUIREMENTS,
    TASK_RULES,
    MalformedResponseError,
    build_prompt,
    classify_call,
    render_call_facts,
    segment_sequence_hash,
)

KB = Path(__file__).resolve().parents[3] / "docs" / "knowledge" / "sales" / "objections"
CALL = synthetic_call()
S = [s.segment_id for s in CALL.segments]  # S[0] closer, S[1] lead, S[2] closer, S[3] lead, S[4] closer


def _run(resp, arm="E0", call=CALL):
    return classify_call(call, arm, ScriptedClassificationProvider(resp), knowledge_root=KB)


def _price(**kw):
    return episode(**{"objection_segment_ids": [S[1]], "context_segment_ids": [S[2], S[3]], **kw})


# --- arm assembly ---------------------------------------------------------------------------


def test_arms_share_rules_facts_and_output_contract():
    prompts = {arm: build_prompt(CALL, arm, KB) for arm in ("E0", "E1", "E2")}
    facts = render_call_facts(CALL)
    for prompt in prompts.values():
        assert prompt.startswith(TASK_RULES + "\n\n" + facts + "\n\n")
        assert prompt.endswith("\n\n" + OUTPUT_REQUIREMENTS + "\n")


def test_e0_has_no_guide_and_no_knowledge():
    prompt = build_prompt(CALL, "E0")
    assert prompt == "\n\n".join([TASK_RULES, render_call_facts(CALL), OUTPUT_REQUIREMENTS]) + "\n"
    assert CLASSIFICATION_GUIDE not in prompt and CONTEXT_HEADER not in prompt


def test_e1_has_short_guide_with_all_labels_and_no_cards():
    prompt = build_prompt(CALL, "E1")
    assert CLASSIFICATION_GUIDE in prompt and CONTEXT_HEADER not in prompt
    assert "=== PRICE_BUDGET ===" not in prompt and "### Do not use when" not in prompt
    for label in CATEGORY_LABELS:
        assert f"\n{label}: " in CLASSIFICATION_GUIDE


def test_e2_embeds_the_knowledge_context_builder_block():
    prompt = build_prompt(CALL, "E2", KB)
    assert build_knowledge_context(KB).text in prompt
    assert CLASSIFICATION_GUIDE not in prompt


def test_e2_without_knowledge_root_and_unknown_arm_fail():
    with pytest.raises(ValueError, match="knowledge_root"):
        build_prompt(CALL, "E2")
    with pytest.raises(ValueError, match="unknown arm"):
        build_prompt(CALL, "E3")


def test_facts_render_segment_ids_roles_and_order_only():
    facts = render_call_facts(CALL)
    blocks = facts.split("\n\n")
    assert blocks[0] == "FACTS FROM CALL"
    roles = ["closer", "lead", "closer", "lead", "closer"]
    for block, seg, role in zip(blocks[1:], CALL.segments, roles, strict=True):
        assert block == f"[{seg.segment_id} | {role}]\n{seg.text}"


# --- leakage boundary -----------------------------------------------------------------------


def test_classifier_accepts_no_deal_outcome_or_crm_input():
    params = set(inspect.signature(classify_call).parameters)
    assert params == {"call", "arm", "provider", "knowledge_root", "knowledge_git_sha"}
    assert set(inspect.signature(build_prompt).parameters) == {"call", "arm", "knowledge_root"}


def test_prompt_uses_no_call_metadata_beyond_segments():
    other = CALL.model_copy(update={"company_id": "zz", "source": "other", "source_id": "zz",
                                    "closer_id": None, "quality_flags": ["x"]})
    for arm in ("E0", "E1", "E2"):
        assert build_prompt(other, arm, KB) == build_prompt(CALL, arm, KB)


def test_non_call_input_is_rejected():
    with pytest.raises(TypeError, match="canonical Call"):
        classify_call({"segments": []}, "E0", ScriptedClassificationProvider(response()))


# --- validation -----------------------------------------------------------------------------


def test_valid_single_objection():
    run = _run(response(_price()))
    assert run.valid, run.validation_errors
    assert run.episodes[0].anchor_segment_id == S[1]


def test_no_objection_call():
    run = _run(response())
    assert run.valid and run.call_detection == "NO_OBJECTION" and run.episodes == ()


def test_multi_category_same_anchor_as_separate_predictions():
    impl = episode(prediction_id="p2", objection_segment_ids=[S[1]], category="IMPLEMENTATION_INTEGRATION",
                   reaction_status="ABSENT", reaction=None, resolution_status="unknown")
    run = _run(response(_price(), impl))
    assert run.valid, run.validation_errors


def test_category_unknown_and_ambiguous():
    unknown = _price(category_status="UNKNOWN", category=None)
    ambiguous = _price(prediction_id="p2", category_status="AMBIGUOUS", category=None,
                       category_candidates=["PRICE_BUDGET", "TIMING_PRIORITY"])
    assert _run(response(unknown, ambiguous)).valid


def test_uncertain_span_without_episode_is_valid():
    run = _run(response(uncertain_spans=[{"segment_ids": [S[1]], "status": "AMBIGUOUS"}]))
    assert run.valid and run.uncertain_spans[0].status == "AMBIGUOUS"


@pytest.mark.parametrize(
    ("resp", "message"),
    [
        (response(_price(category="STATUS_QUO")), "category"),
        (response(_price(category="price")), "category"),  # domain enum value is not a label
        (response(_price(category_status="AMBIGUOUS", category=None,
                         category_candidates=["PRICE_BUDGET"])), ">=2 distinct candidates"),
        (response(_price(objection_segment_ids=["seg_does_not_exist"])), "not in this call"),
        (response(_price(objection_segment_ids=["o cliente disse que está caro"])), "not in this call"),
        (response(_price(objection_segment_ids=[S[0]], context_segment_ids=[S[1]])), "not spoken by a lead"),
        (response(_price(objection_segment_ids=[S[1], S[2]], context_segment_ids=[S[3]])),
         "more than one speaker"),
        (response(_price(context_segment_ids=[S[3], S[2]])), "call order"),
        (response(_price(context_segment_ids=[S[2], S[2]])), "duplicate segment_ids"),
        (response(_price(context_segment_ids=[S[1], S[3]])), "both objection and context"),
        (response(_price(objection_segment_ids=[S[3]], context_segment_ids=[S[1]])), "call order|before"),
        (response(_price(resolution_status="AMBIGUOUS")), "resolution_status"),
        (response(_price(resolution_status="REJECT")), "resolution_status"),
        (response(_price(resolution_status="resolved")), "contradicts reaction"),
        (response(_price(reaction="NEUTRAL")), "reaction"),
        (response(_price(), call_detection="NO_OBJECTION"), "contradicts"),
        (response(call_detection="OBJECTIONS_FOUND"), "contradicts"),
        (response(_price(), _price()), "duplicate prediction_id"),
        (response(_price(), _price(prediction_id="p2")), "same anchor and category"),
        (response(_price(summary=" ")), "summary"),
        (response(uncertain_spans=[{"segment_ids": [S[1]], "status": "PRESENT"}]), "status"),
    ],
)
def test_invalid_predictions_are_reported_not_repaired(resp, message):
    run = _run(resp)
    assert not run.valid
    assert any(re.search(message, err) for err in run.validation_errors), run.validation_errors
    assert run.raw_response is resp  # kept verbatim for the run record


# --- GL-3 -----------------------------------------------------------------------------------


def test_gl3_clarification_as_only_reaction_is_unknown():
    clar = _price(reaction="CLARIFICATION", resolution_status="unknown")
    assert _run(response(clar)).valid
    assert not _run(response(_price(reaction="CLARIFICATION", resolution_status="unresolved"))).valid


def test_gl3_ambiguous_reaction_resolves_to_unknown():
    amb = _price(reaction_status="AMBIGUOUS", reaction=None,
                 reaction_candidates=["CLARIFICATION", "REJECT"], resolution_status="unknown")
    assert _run(response(amb)).valid
    bad = dict(amb, resolution_status="unresolved")
    assert not _run(response(bad)).valid


def test_reaffirming_question_as_reject_resolves_normally():
    assert _run(response(_price(reaction="REJECT", resolution_status="unresolved"))).valid


# --- provider -------------------------------------------------------------------------------


def test_provider_receives_exact_prompt_and_metadata_is_recorded():
    provider = ScriptedClassificationProvider(response(_price()), model="m-1")
    run = classify_call(CALL, "E1", provider)
    assert provider.prompts == [build_prompt(CALL, "E1")]
    assert (run.provider, run.model, run.arm, run.call_id) == ("scripted", "m-1", "E1", CALL.call_id)


def test_provider_error_propagates_unchanged():
    boom = RuntimeError("provider down")
    with pytest.raises(RuntimeError, match="provider down"):
        classify_call(CALL, "E0", ScriptedClassificationProvider(boom))


@pytest.mark.parametrize(
    "bad",
    [
        "not a dict",
        {"episodes": [], "uncertain_spans": []},
        dict(response(), extra=1),
        response(episode(objection_segment_ids="seg")),
        response(dict(episode(), confidence=0.9)),
        dict(response(), episodes={}),
    ],
)
def test_malformed_response_raises(bad):
    with pytest.raises(MalformedResponseError):
        classify_call(CALL, "E0", ScriptedClassificationProvider(bad))


# --- provenance and digests -----------------------------------------------------------------


def test_run_provenance_per_arm():
    e0 = _run(response(), "E0")
    e2 = classify_call(CALL, "E2", ScriptedClassificationProvider(response()), KB, knowledge_git_sha="abc")
    assert e0.knowledge_sha256 is None and e0.knowledge_concept_versions == () and e0.knowledge_git_sha is None
    assert e2.knowledge_sha256 == build_knowledge_context(KB).sha256
    assert len(e2.knowledge_concept_versions) == len(CONCEPT_ORDER) and e2.knowledge_git_sha == "abc"
    assert e0.segment_sequence_hash == e2.segment_sequence_hash == segment_sequence_hash(CALL)
    prompt = build_prompt(CALL, "E0")
    assert (e0.prompt_chars, e0.prompt_utf8_bytes) == (len(prompt), len(prompt.encode("utf-8")))


def test_prompt_digests_are_stable_and_differ_by_arm():
    digests = {arm: _run(response(), arm).prompt_sha256 for arm in ("E0", "E1", "E2")}
    assert len(set(digests.values())) == 3
    assert _run(response(), "E1").prompt_sha256 == digests["E1"]


def test_transcript_change_changes_prompt_and_segmentation_digest():
    texts = [("p-closer", "O plano anual fica em 18 mil."), ("p-lead", "Gostei, mas não temos verba agora.")]
    a, b = synthetic_call(texts), synthetic_call([texts[0], (texts[1][0], texts[1][1] + "!")])
    assert _run(response(), call=a).prompt_sha256 != _run(response(), call=b).prompt_sha256
    assert segment_sequence_hash(a) != segment_sequence_hash(b)


def test_knowledge_change_changes_e2_only(tmp_path: Path):
    kb = tmp_path / "objections"
    shutil.copytree(KB, kb)
    before = {arm: build_prompt(CALL, arm, kb) for arm in ("E0", "E1", "E2")}
    path = kb / "PRICE_BUDGET.md"
    path.write_text(path.read_text(encoding="utf-8").replace(
        "## Do not use when\n\n", "## Do not use when\n\n- nova regra;\n", 1), encoding="utf-8")
    after = {arm: build_prompt(CALL, arm, kb) for arm in ("E0", "E1", "E2")}
    assert after["E0"] == before["E0"] and after["E1"] == before["E1"]
    assert after["E2"] != before["E2"]


def test_prompt_has_no_carriage_returns():
    for arm in ("E0", "E1", "E2"):
        assert "\r" not in build_prompt(CALL, arm, KB)
