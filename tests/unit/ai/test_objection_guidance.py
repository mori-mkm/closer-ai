"""Objection guidance knowledge (load/retrieve) and the guidance engine, with a fake provider."""
from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

from closer_ai.ai.knowledge_context import CONCEPT_ORDER
from closer_ai.ai.objection_classifier import EpisodePrediction
from closer_ai.ai.objection_guidance import (
    EVIDENCE_GRADES,
    GUIDANCE_SCHEMA,
    ObjectionKnowledgeError,
    build_guidance_prompt,
    guide_episode,
    load_objection_knowledge,
)
from closer_ai.demo.analyze_call import GUIDANCE_KB, parse_transcript

TRANSCRIPT = """\
closer: Podemos fechar hoje?
lead: Aqui eu não fecho nada sem o meu sócio aprovar.
closer: Entendo. O que ele vai querer saber?
lead: Em quanto tempo volta o investimento.
"""


@pytest.fixture(scope="module")
def kb():
    return load_objection_knowledge(GUIDANCE_KB)


@pytest.fixture(scope="module")
def call():
    return parse_transcript(TRANSCRIPT, "unit_authority")


def _seg(call, i: int) -> str:
    return call.segments[i].segment_id


def _episode(call, category="AUTHORITY_INTERNAL_BUY_IN", status="PRESENT", candidates=()):
    return EpisodePrediction(
        prediction_id="p1", objection_segment_ids=(_seg(call, 1),), context_segment_ids=(_seg(call, 3),),
        category_status=status, category=category if status == "PRESENT" else None,
        category_candidates=tuple(candidates), reaction_status="ABSENT", reaction=None,
        reaction_candidates=(), resolution_status="unknown", summary="Lead depende do sócio.",
    )


class FakeProvider:
    name = "fake"
    model = "fake-1"

    def __init__(self, response: dict | Callable[[str], dict]):
        self.response = response
        self.prompts: list[str] = []

    def classify(self, prompt: str, **kw):
        self.prompts.append(prompt)
        self.kwargs = kw
        return self.response(prompt) if callable(self.response) else self.response


def _answer(call, move_id="AUTHORITY_INTERNAL_BUY_IN.M1", **overrides):
    return {
        "move_id": move_id,
        "rationale": "O lead disse que não fecha sem o sócio aprovar.",
        "suggested_question": "Quem mais participa dessa decisão e o que o seu sócio precisa ver?",
        "evidence_segment_ids": [_seg(call, 1)],
        **overrides,
    }


# --- knowledge --------------------------------------------------------------------------------


def test_all_eight_categories_load_and_retrieve_by_exact_category(kb):
    assert tuple(kb.units) == CONCEPT_ORDER
    for category in CONCEPT_ORDER:
        unit = kb.retrieve(category)
        assert unit.category == category and unit.id == f"guidance.{category}"
        assert unit.recommended_moves and unit.typical_phrases
        assert all(m.id.startswith(f"{category}.M") for m in unit.recommended_moves)


@pytest.mark.parametrize("category", ["OTHER", None, "price", "UNKNOWN"])
def test_retrieve_returns_none_without_a_matching_unit(kb, category):
    assert kb.retrieve(category) is None


def test_evidence_grades_are_preserved_not_upgraded(kb):
    price = kb.retrieve("PRICE_BUDGET")
    assert price.move("PRICE_BUDGET.M1").evidence_grade == "MODERATE"
    assert price.move("PRICE_BUDGET.M1").source_ids == ("N5",)
    assert kb.retrieve("AUTHORITY_INTERNAL_BUY_IN").move("AUTHORITY_INTERNAL_BUY_IN.M1").evidence_grade == "WEAK"
    # mechanism-only MODERATE stays WEAK for sales, with the research's own note kept
    labeling = kb.retrieve("TRUST_RISK").move("TRUST_RISK.M2")
    assert labeling.evidence_grade == "WEAK" and "MODERATE (mecanismo, N17)" in labeling.grade_note
    assert kb.retrieve("COMPETITION_EXISTING_SOLUTION").move(
        "COMPETITION_EXISTING_SOLUTION.M4").evidence_grade == "NOT_SUPPORTED_BY_CURRENT_SOURCES"
    grades = {i.evidence_grade for u in kb.units.values() for i in (*u.recommended_moves, *u.do_not)}
    assert grades <= set(EVIDENCE_GRADES) and "STRONG" not in grades  # nothing in the research is STRONG for sales


def test_negative_knowledge_is_preserved(kb):
    assert all(u.do_not for u in kb.units.values())
    discount = kb.retrieve("PRICE_BUDGET").do_not[0]
    assert "desconto" in discount.guidance and discount.evidence_grade == "NOT_SUPPORTED_BY_CURRENT_SOURCES"
    assert any("pitch" in d.guidance for d in kb.retrieve("AUTHORITY_INTERNAL_BUY_IN").do_not)


def test_source_ids_are_preserved_and_registered(kb):
    assert kb.retrieve("AUTHORITY_INTERNAL_BUY_IN").evidence_source_ids == ("N13", "N25")
    assert kb.retrieve("AUTHORITY_INTERNAL_BUY_IN").move("AUTHORITY_INTERNAL_BUY_IN.M3").source_ids == ("N25",)
    used = {s for u in kb.units.values() for i in (*u.recommended_moves, *u.do_not) for s in i.source_ids}
    used |= {s for u in kb.units.values() for s in u.evidence_source_ids}
    assert used <= set(kb.sources)


def _mutate_unit(name: str, fn: Callable[[dict], None]) -> Callable[[Path], None]:
    def apply(root: Path) -> None:
        path = root / f"{name}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        fn(data)
        path.write_text(json.dumps(data), encoding="utf-8")
    return apply


@pytest.mark.parametrize("break_it", [
    _mutate_unit("PRICE_BUDGET", lambda d: d["recommended_moves"][0].update(evidence_grade="PROVEN")),
    _mutate_unit("PRICE_BUDGET", lambda d: d.update(do_not=[])),
    _mutate_unit("PRICE_BUDGET", lambda d: d["do_not"][1].update(source_ids=["N99"])),
    _mutate_unit("PRICE_BUDGET", lambda d: d["recommended_moves"][1].update(code="CLOSE_HARD")),
    _mutate_unit("PRICE_BUDGET", lambda d: d.update(extra="x")),
    _mutate_unit("PRICE_BUDGET", lambda d: d.update(category="TIMING_PRIORITY")),
    _mutate_unit("PRICE_BUDGET", lambda d: d["recommended_moves"][1].update(id="PRICE_BUDGET.M1")),
    _mutate_unit("PRICE_BUDGET", lambda d: d["recommended_moves"][0].pop("grade_note")),
    lambda root: (root / "TERMS_PROCESS.json").unlink(),
    lambda root: (root / "EXTRA.json").write_text("{}", encoding="utf-8"),
    lambda root: (root / "TRUST_RISK.json").write_text("{not json", encoding="utf-8"),
    lambda root: (root / "SOURCES.json").unlink(),
], ids=["grade", "empty-do-not", "unknown-source", "unknown-code", "extra-key", "category-mismatch",
        "duplicate-id", "missing-key", "missing-category", "unexpected-file", "invalid-json", "no-sources"])
def test_malformed_knowledge_fails_loudly(tmp_path, break_it):
    root = tmp_path / "guidance"
    shutil.copytree(GUIDANCE_KB, root)
    load_objection_knowledge(root)  # the copy itself is valid
    break_it(root)
    with pytest.raises(ObjectionKnowledgeError):
        load_objection_knowledge(root)


# --- guidance ---------------------------------------------------------------------------------


def test_guided_output_copies_grade_sources_and_avoid_from_knowledge(kb, call):
    provider = FakeProvider(_answer(call))
    g = guide_episode(call, _episode(call), kb, provider)
    unit = kb.retrieve("AUTHORITY_INTERNAL_BUY_IN")
    assert g.status == "GUIDED" and g.category == "AUTHORITY_INTERNAL_BUY_IN"
    assert g.recommended_move == unit.move("AUTHORITY_INTERNAL_BUY_IN.M1")
    assert g.knowledge_grade == "WEAK"
    assert g.avoid == unit.do_not
    assert g.category_evidence_sources == ("N13", "N25")
    assert (g.knowledge_unit_id, g.knowledge_unit_version) == ("guidance.AUTHORITY_INTERNAL_BUY_IN", "1.0")
    assert g.knowledge_move_id == "AUTHORITY_INTERNAL_BUY_IN.M1"
    assert g.generated_guidance.generated_by == "fake/fake-1"
    assert g.objection_evidence[0].text == call.segments[1].text  # quote copied from the Call
    assert g.objection_evidence[0].speaker_role == "lead"
    assert g.generated_guidance.rationale_evidence[0].segment_id == _seg(call, 1)


def test_sources_cover_the_chosen_move_and_avoid_items(kb, call):
    g = guide_episode(call, _episode(call), kb,
                      FakeProvider(_answer(call, move_id="AUTHORITY_INTERNAL_BUY_IN.M3")))
    assert g.knowledge_sources == ("N25",)


@pytest.mark.parametrize("answer, needle", [
    ({"move_id": "PRICE_BUDGET.M2"}, "not a move of guidance.AUTHORITY_INTERNAL_BUY_IN"),
    ({"move_id": "AUTHORITY_INTERNAL_BUY_IN.M99"}, "not a move"),
    ({"evidence_segment_ids": ["seg-invented"]}, "not in CALL EVIDENCE"),
    ({"evidence_segment_ids": []}, "non-empty list"),
    ({"suggested_question": "Fale com o sócio."}, "not a question"),
    ({"rationale": ""}, "rationale"),
    ({"evidence_grade": "STRONG"}, "expected keys"),  # the model cannot set the grade
])
def test_invalid_model_answers_are_rejected_not_repaired(kb, call, answer, needle):
    g = guide_episode(call, _episode(call), kb, FakeProvider(_answer(call, **answer)))
    assert g.status == "INVALID_RESPONSE"
    assert g.recommended_move is None and g.knowledge_grade is None and g.generated_guidance is None
    assert any(needle in e for e in g.errors), g.errors
    assert g.avoid == kb.retrieve("AUTHORITY_INTERNAL_BUY_IN").do_not  # negative knowledge still shown


@pytest.mark.parametrize("episode_kwargs", [
    {"category": "OTHER"},
    {"status": "AMBIGUOUS", "candidates": ("PRICE_BUDGET", "TIMING_PRIORITY")},
    {"status": "UNKNOWN"},
])
def test_no_knowledge_is_explicit_and_skips_the_provider(kb, call, episode_kwargs):
    provider = FakeProvider(lambda prompt: pytest.fail("provider must not be called"))
    g = guide_episode(call, _episode(call, **episode_kwargs), kb, provider)
    assert g.status == "NO_KNOWLEDGE" and g.recommended_move is None and g.errors
    assert g.category in (None, "OTHER") and not provider.prompts


def test_prompt_separates_call_evidence_from_sales_knowledge(kb, call):
    prompt = build_guidance_prompt(call, _episode(call), kb.retrieve("AUTHORITY_INTERNAL_BUY_IN"))
    evidence_at = prompt.index("CALL EVIDENCE")
    knowledge_at = prompt.index("SALES KNOWLEDGE — NOT FROM THIS CALL")
    assert evidence_at < prompt.index(call.segments[1].text) < knowledge_at
    assert call.segments[0].text not in prompt  # only the episode's segments are call evidence
    assert "AUTHORITY_INTERNAL_BUY_IN.M1" in prompt[knowledge_at:]
    assert "PRICE_BUDGET.M1" not in prompt  # only the retrieved unit


def test_brief_prompt_only_shortens_the_rationale(kb, call):
    unit = kb.retrieve("AUTHORITY_INTERNAL_BUY_IN")
    full, brief = build_guidance_prompt(call, _episode(call), unit), build_guidance_prompt(call, _episode(call), unit, brief=True)
    assert "one or two sentences in Portuguese" in full  # default (post-call) unchanged
    assert brief == full.replace("one or two sentences in Portuguese", "one short sentence in Portuguese")


def test_live_guidance_asks_brief_and_enforced_schema_validation_unchanged(kb, call):
    provider = FakeProvider(_answer(call))
    g = guide_episode(call, _episode(call), kb, provider, live=True)
    assert g.status == "GUIDED" and provider.kwargs == {"schema": GUIDANCE_SCHEMA}
    assert "one short sentence in Portuguese" in provider.prompts[0]
    assert set(GUIDANCE_SCHEMA["required"]) == {"move_id", "rationale", "suggested_question", "evidence_segment_ids"}
    guide_episode(call, _episode(call), kb, provider)
    assert provider.kwargs == {}  # post-call: plain JSON, as before
    bad = FakeProvider(_answer(call, evidence_segment_ids=[2]))  # what qwen3 wrote without the schema
    assert guide_episode(call, _episode(call), kb, bad, live=True).status == "INVALID_RESPONSE"  # still fails closed


# --- grounding of model-generated guidance (fail closed) -------------------------------------


def _price_call_and_episode():
    call = parse_transcript("closer: São doze parcelas.\nlead: Está caro pra mim.\ncloser: Entendo.\n", "unit_price")
    episode = EpisodePrediction(
        prediction_id="p1", objection_segment_ids=(_seg(call, 1),), context_segment_ids=(_seg(call, 2),),
        category_status="PRESENT", category="PRICE_BUDGET", category_candidates=(), reaction_status="ABSENT",
        reaction=None, reaction_candidates=(), resolution_status="unknown", summary="Preço.",
    )
    return call, episode


def _price_answer(call, question, rationale="A lead disse que está caro."):
    return {"move_id": "PRICE_BUDGET.M2", "rationale": rationale, "suggested_question": question,
            "evidence_segment_ids": [_seg(call, 1)]}


def test_hallucinated_date_is_invalid(kb, call):
    g = guide_episode(call, _episode(call), kb, FakeProvider(_answer(
        call, suggested_question="Consegue falar com o seu sócio até sexta?")))
    assert g.status == "INVALID_RESPONSE" and g.generated_guidance is None
    assert any("suggested_question: ungrounded date 'sexta'" in e for e in g.errors), g.errors


def test_date_stated_in_the_call_is_allowed(kb):
    call = parse_transcript("closer: Fechamos?\nlead: Sem o meu sócio aprovar não fecho; falo com ele na "
                            "sexta-feira.\ncloser: Certo.\nlead: Combinado.\n", "unit_date")
    g = guide_episode(call, _episode(call), kb, FakeProvider(_answer(
        call, suggested_question="Depois de falar com o seu sócio na sexta-feira, o que ele precisa ver?")))
    assert g.status == "GUIDED", g.errors
    assert "sexta-feira" in g.generated_guidance.suggested_question


@pytest.mark.parametrize("question", ["Consegue marcar 20 minutos com ele até [dia]?",
                                      "Você consegue levar isso pra ele até {data}?",
                                      "O que o seu sócio precisa ver sobre <X>?"])
def test_placeholder_is_invalid(kb, call, question):
    g = guide_episode(call, _episode(call), kb, FakeProvider(_answer(call, suggested_question=question)))
    assert g.status == "INVALID_RESPONSE"
    assert any("ungrounded placeholder" in e for e in g.errors), g.errors


def test_invented_amount_is_invalid(kb):
    call, episode = _price_call_and_episode()
    g = guide_episode(call, episode, kb, FakeProvider(_price_answer(
        call, "Se ficar em R$ 50.000, cabe no seu caixa?")))
    assert g.status == "INVALID_RESPONSE"
    assert any("number '50.000'" in e for e in g.errors) and any("'r$'" in e for e in g.errors)


def test_grounded_stakeholder_may_be_mentioned(kb, call):
    question = "O que o seu sócio precisa entender para conseguir avaliar essa decisão?"
    g = guide_episode(call, _episode(call), kb, FakeProvider(_answer(call, suggested_question=question)))
    assert g.status == "GUIDED" and g.generated_guidance.suggested_question == question


@pytest.mark.parametrize("question", ["O seu sócio concorda com esse valor?",
                                      "O seu CFO já viu essa proposta?",
                                      "A diretoria aprova esse investimento?"])
def test_invented_stakeholder_is_invalid(kb, question):
    call, episode = _price_call_and_episode()  # no decision-maker is mentioned in this call
    g = guide_episode(call, episode, kb, FakeProvider(_price_answer(call, question)))
    assert g.status == "INVALID_RESPONSE"
    assert any("ungrounded stakeholder" in e for e in g.errors), g.errors


def test_rationale_is_grounded_too(kb):
    call, episode = _price_call_and_episode()
    g = guide_episode(call, episode, kb, FakeProvider(_price_answer(
        call, "Caro em relação a quê?", rationale="A lead quer garantia de 30 dias.")))
    assert g.status == "INVALID_RESPONSE"
    assert any(e.startswith("rationale: ungrounded") for e in g.errors)


def test_value_sprint_v0_timing_output_is_now_rejected(kb):
    """Regression: the real qwen3:8b output of Value Sprint v0 invented a date and kept '[X]'."""
    call = parse_transcript(
        "closer: Podemos começar no mês que vem?\n"
        "lead: Agora não dá. Estamos no meio da safra e eu não tenho cabeça pra começar nada novo até a "
        "colheita acabar.\ncloser: Faz sentido. Quando termina a colheita?\n", "unit_timing")
    episode = EpisodePrediction(
        prediction_id="p1", objection_segment_ids=(_seg(call, 1),), context_segment_ids=(_seg(call, 2),),
        category_status="PRESENT", category="TIMING_PRIORITY", category_candidates=(), reaction_status="ABSENT",
        reaction=None, reaction_candidates=(), resolution_status="unknown", summary="Safra.",
    )
    before = {"move_id": "TIMING_PRIORITY.M3", "rationale": "O lead está no meio da safra.",
              "suggested_question": "Então marcamos 5 de abril pra revisarmos o [X]. Faz sentido?",
              "evidence_segment_ids": [_seg(call, 1)]}
    g = guide_episode(call, episode, kb, FakeProvider(before))
    assert g.status == "INVALID_RESPONSE"
    joined = " | ".join(g.errors)
    assert "placeholder '[X]'" in joined and "date 'abril'" in joined and "number '5'" in joined


def test_prompt_shows_templates_generically_but_knowledge_keeps_them(kb, call):
    unit = kb.retrieve("TIMING_PRIORITY")
    prompt = build_guidance_prompt(call, _episode(call), unit)
    assert "[data]" not in prompt and "[X]" not in prompt
    assert "Então marcamos uma data objetiva pra revisar esse ponto." in prompt
    assert "[data]" in unit.move("TIMING_PRIORITY.M3").guidance  # the knowledge text is unchanged
