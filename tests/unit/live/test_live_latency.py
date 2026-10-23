"""P1 latency: deterministic fast path + separate classifier model. No real Ollama."""
from __future__ import annotations

import pytest
from test_live_session import FakeProvider, _live, _say  # same folder

from closer_ai.ai.objection_guidance import load_objection_knowledge
from closer_ai.demo.analyze_call import CLASSIFICATION_KB, GUIDANCE_KB
from closer_ai.live.server import Runtime, parse_utterance
from closer_ai.live.session import LiveConfig, LiveSalesSession, fast_path_category


@pytest.fixture(scope="module")
def kb():
    return load_objection_knowledge(GUIDANCE_KB)


class Clock:
    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now


def _session(kb, provider=None, classifier=None, **cfg):
    provider, clock = provider or FakeProvider(), Clock()
    s = LiveSalesSession("m1", provider, kb, CLASSIFICATION_KB, LiveConfig(**cfg), clock=clock,
                         classifier_provider=classifier)
    return s, provider, clock


def _classifier_calls(provider) -> int:
    return sum(not p.startswith(("GUIDANCE TASK", "COMMERCIAL FACTS TASK")) for p in provider.prompts)


@pytest.mark.parametrize("line", [
    "Gostei da proposta, mas achei muito caro.", "Está muito caro.", "Ficou caro.", "Não tenho orçamento.",
    "Não cabe no orçamento.", "Está acima do nosso orçamento.",
])
def test_fast_path_price(line):
    assert fast_path_category(line) == "PRICE_BUDGET"


@pytest.mark.parametrize("line", [
    "Preciso falar com meu sócio antes de fechar.", "Preciso falar com um sócio antes de fechar.",
    "Não posso decidir isso sozinho.", "Eu gostei, mas não posso decidir isso sozinho.",
    "Meu diretor precisa aprovar antes da gente seguir.", "Só consigo avançar depois da aprovação do meu sócio.",
])
def test_fast_path_authority_blockers(line):
    assert fast_path_category(line) == "AUTHORITY_INTERNAL_BUY_IN"


@pytest.mark.parametrize("line", [
    "Não achei caro, o preço está ok.", "Não é tão caro assim.", "É caro, mas vale a pena.", "Está caro?",
    "O concorrente é muito caro.", "Esse valor ficou um pouco pesado pra gente.",  # paraphrase -> LLM
    "Não, ficou acima.",  # needs the closer's question -> LLM
    "Achei caro e preciso falar com meu sócio.",  # two categories -> LLM
    "Sim, meu sócio.", "Meu sócio participa.", "Eu e meu diretor.", "Meu sócio.",  # discovery, not blockers
    "Preciso falar com meu sócio no mês que vem.",  # timing marker -> LLM
    "Agora não é o momento, talvez no próximo trimestre.", "Hoje temos cinco pessoas no time.",
    "Sinceramente não sei se a gente precisa disso.",
])
def test_fast_path_is_unsure_so_the_llm_decides(line):
    assert fast_path_category(line) is None


def test_fast_path_skips_only_the_classifier_and_keeps_the_rest_of_the_pipeline(kb):
    s, provider, clock = _session(kb)
    t = _live(s, clock, [("closer", "O que achou?"), ("lead", "Gostei da proposta, mas achei muito caro.")])
    assert (t["classification_source"], t["category"], t["outcome"]) == ("deterministic_fast_path", "PRICE_BUDGET",
                                                                         "RECOMMENDED")
    assert _classifier_calls(provider) == 0 and provider.guidance_calls() == 1  # guidance + grounding still run
    assert s.current().knowledge_unit == "guidance.PRICE_BUDGET"
    assert s.fast_path_counters == {"attempts": 1, "hits": 1, "llm_calls_saved": 1}
    assert s.fast_path_by_category == {"PRICE_BUDGET": 1}
    # the Commercial State gets the same OBJECTION_IDENTIFIED as from the LLM path
    assert s.commercial.view()["objections"] == [{"value": "PRICE_BUDGET", "segment_ids": ["seg_2"],
                                                  "status": "CONFIRMED"}]


def test_fast_path_grounding_still_fails_closed(kb):
    s, _, clock = _session(kb, FakeProvider(bad_guidance="O CFO aprovou R$ 10.000 ontem?"))
    t = _live(s, clock, [("lead", "Gostei da proposta, mas achei muito caro.")])
    assert t["classification_source"] == "deterministic_fast_path"
    assert (t["outcome"], s.current()) == ("NO_RECOMMENDATION", None) and t["reason"].startswith("GUIDANCE_")


def test_unsure_lines_fall_back_to_the_llm(kb):
    s, provider, clock = _session(kb)
    t = _live(s, clock, [("closer", "Faz sentido?"), ("lead", "Sinceramente não sei se a gente precisa disso.")])
    assert (t["classification_source"], t["category"]) == ("llm", "NEED_VALUE_FIT")
    assert _classifier_calls(provider) == 1 and s.fast_path_counters == {"attempts": 1, "hits": 0,
                                                                          "llm_calls_saved": 0}


def test_authority_discovery_still_gives_no_recommendation(kb):
    s, _, clock = _session(kb)  # not fast-pathed; the LLM (fake, like qwen3) says AUTHORITY; the gate drops it
    t = _live(s, clock, [("closer", "Além de você, alguém participa da decisão?"), ("lead", "Sim, meu sócio.")])
    assert (t["classification_source"], t["reason"], s.current()) == ("llm", "UNCORROBORATED_CATEGORY", None)
    assert s.commercial.view()["objections"] == []


def test_a_continuation_is_never_fast_pathed(kb):
    s, _, clock = _session(kb)
    _say(s, clock, 1, "lead", "Eu gostei bastante do que vi.")  # read alone: no objection
    _say(s, clock, 2, "lead", "Gostei da proposta, mas achei muito caro.")  # two new lead lines in one analysis
    t = s.analyze()
    assert t["classification_source"] == "llm"


def test_fast_path_can_be_turned_off(kb):
    s, provider, clock = _session(kb, fast_path=False)
    t = _live(s, clock, [("lead", "Gostei da proposta, mas achei muito caro.")])
    assert t["classification_source"] == "llm" and _classifier_calls(provider) == 1
    assert s.fast_path_counters["attempts"] == 0


def test_separate_classifier_model_gets_only_the_classifier_call(kb):
    main, small = FakeProvider(), FakeProvider()
    s, _, clock = _session(kb, main, classifier=small, fast_path=False)
    _live(s, clock, [("lead", "Gostei da proposta, mas achei muito caro.")])
    assert _classifier_calls(small) == 1 and small.guidance_calls() == 0
    assert _classifier_calls(main) == 0 and main.guidance_calls() == 1  # guidance stays on the main model


def test_default_is_one_model_for_everything(kb):
    s, provider, _ = _session(kb)
    assert s.classifier is provider
    rt = Runtime(provider, LiveConfig(), {"Matheus"}, log=lambda _: None)
    assert rt.session("m").classifier is provider and LiveConfig().fast_path is True


def test_runtime_passes_the_classifier_model_to_sessions(kb):
    main, small = FakeProvider(), FakeProvider()
    rt = Runtime(main, LiveConfig(fast_path=False), {"Matheus"}, log=lambda _: None, classifier_provider=small)
    rt.knowledge = kb
    rt.receive(parse_utterance({"meeting_id": "m", "speaker": "Lead", "text": "Gostei da proposta, mas achei muito caro.",
                                "sequence": 1}, rt.closer_names, 1.0), background=False)
    assert _classifier_calls(small) == 1 and _classifier_calls(main) == 0
    assert rt.sessions["m"].current().category == "PRICE_BUDGET"


def test_post_call_brief_is_the_same_with_the_fast_path(kb):
    briefs = []
    for fast in (True, False):
        s, _, clock = _session(kb, fast_path=fast)
        _live(s, clock, [("closer", "O que achou?"), ("lead", "Gostei da proposta, mas achei muito caro.")])
        b = s.finalize()
        briefs.append((b.facts, [r.code for r in b.risks], b.recommendation_stats["recommendations_by_category"]))
    assert briefs[0] == briefs[1]
