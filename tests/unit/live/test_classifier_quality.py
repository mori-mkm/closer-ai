"""Classifier Quality v1: the non-objection guard, the category normalizations and gates, the lexical buying
signal in the Commercial State, and the synthetic matrix (evals/real_calls/matrix) for the deterministic step."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from test_live_session import SCRIPT, Clock, FakeProvider, _say  # same folder

from closer_ai.ai.objection_classifier import build_prompt
from closer_ai.ai.objection_guidance import load_objection_knowledge
from closer_ai.demo.analyze_call import CLASSIFICATION_KB, GUIDANCE_KB
from closer_ai.live import signals
from closer_ai.live.session import (
    LABELS,
    REJECTION_REASONS,
    LiveConfig,
    LiveSalesSession,
    fast_path_category,
    non_objection_guard,
    price_override,
    screen,
)

ROOT = Path(__file__).resolve().parents[3]
MATRIX = ROOT / "evals" / "real_calls" / "matrix"
P, A, I, C, N = ("PRICE_BUDGET", "AUTHORITY_INTERNAL_BUY_IN", "IMPLEMENTATION_INTEGRATION",
                 "COMPETITION_EXISTING_SOLUTION", "NEED_VALUE_FIT")


def _matrix() -> list[tuple[str, str, dict]]:
    lines = {r["meeting_id"]: r["text"] for r in map(json.loads, (MATRIX / "classifier_guard_v1.jsonl").open(
        encoding="utf-8")) if r["role"] == "lead"}
    labels = {r["meeting_id"]: r["expected_objection"] for r in map(json.loads, (
        MATRIX / "classifier_guard_v1.annotations.jsonl").open(encoding="utf-8")) if "sequence" in r}
    return [(mid, lines[mid], labels[mid]) for mid in sorted(lines)]


MATRIX_CASES = _matrix()


def test_the_matrix_is_large_and_covers_every_group():
    groups = {mid.split("-")[1] for mid, _, _ in MATRIX_CASES}
    assert len(MATRIX_CASES) >= 50 and groups == {
        "PRICE", "AUTHORITY", "DISCOVERY", "IMPLEMENTATION", "COMPETITION", "NEED_VALUE", "TIMING", "PAIN",
        "INFORMATION", "BUYING", "NEGATION", "NEUTRAL"}


@pytest.mark.parametrize("mid,text,label", MATRIX_CASES, ids=[m for m, _, _ in MATRIX_CASES])
def test_matrix_deterministic_step(mid, text, label):
    """Objections keep the classifier's category (or an accepted one). Questions, negations, buying signals
    and pains are rejected WHATEVER category the classifier proposes; a discovery answer is never AUTHORITY.
    Neutral lines are left to the classifier (no deterministic claim)."""
    group = mid.split("-")[1]
    if label["present"]:
        category, rejection = screen(label["category"], text)
        assert rejection is None and category in (label["category"], *label.get("acceptable_categories", []))
    elif group in ("NEGATION", "INFORMATION", "BUYING", "PAIN"):
        assert all(screen(cat, text)[1] for cat in LABELS), [c for c in LABELS if not screen(c, text)[1]]
    elif group == "DISCOVERY":
        assert screen(A, text)[1] == "UNCORROBORATED_CATEGORY"


@pytest.mark.parametrize("text,reason", [
    ("Quanto custa?", "NON_OBJECTION_INFORMATION_REQUEST"),
    ("E no plano anual sai por quanto?", "NON_OBJECTION_INFORMATION_REQUEST"),
    ("Quanto custa a licença para cinco usuários?", "NON_OBJECTION_INFORMATION_REQUEST"),
    ("Entendi. Qual a diferença de vocês para o sistema que a gente usa hoje?", "NON_OBJECTION_INFORMATION_REQUEST"),
    ("quanto fica para cinco usuários", "NON_OBJECTION_INFORMATION_REQUEST"),  # Meet dropped the "?"
    ("Não achei caro.", "NEGATED_RESISTANCE"),
    ("O preço não é problema.", "NEGATED_RESISTANCE"),
    ("Quando abrimos, esse tipo de sistema estava fora do nosso alcance. Hoje o orçamento comporta.",
     "NEGATED_RESISTANCE"),
])
def test_guard_rejects_information_requests_and_negated_resistance(text, reason):
    assert non_objection_guard(text) == reason


@pytest.mark.parametrize("text", [
    "Por que está tão caro?", "Como eu vou pagar esse valor?", "Você não acha 63 mil muito caro?",
    "E se o sistema cair no fechamento do mês?",  # a worried "e se", not "e se eu pagar"
    "Mesmo com 10%, são quase 3.500 por mês. Onde uma clínica do nosso tamanho arruma isso?",
    "Não achei caro, mas não cabe no orçamento agora.", "Não achei barato.", "Não cabe no orçamento.",
    "Não tenho verba.", "Preciso falar com meu sócio, tudo bem?",
])
def test_guard_keeps_real_resistance_even_as_a_question_or_with_a_negation(text):
    assert non_objection_guard(text) is None


def test_pain_is_not_need_value_fit_but_a_negative_evaluation_is():
    assert screen(N, "Hoje tudo depende de mim na fazenda.") == (N, "PAIN_NOT_OBJECTION")
    assert screen(P, "Tenho dificuldade para controlar custos.")[1] == "PAIN_NOT_OBJECTION"  # price word, still pain
    assert screen(N, "A gente perde muito tempo, mas não temos como trocar agora.") == (N, None)  # pain + blocker
    for line in ("Não vejo necessidade disso.", "Isso não resolve meu problema.", "Não vejo valor nisso.",
                 "Não sei se isso faz sentido para a gente.", "Não acho que vamos usar."):
        assert screen(N, line) == (N, None)
    assert screen(N, "Estamos vendo outra proposta também, só para ter base de comparação.") == (
        N, "UNCORROBORATED_CATEGORY")


def test_money_barriers_win_over_need_value_fit_and_unsupported_implementation():
    line = "Olha, para a licença a gente tinha reservado bem menos do que isso, e cada usuário extra ainda encarece."
    assert price_override(N, line) == P
    assert price_override(N, "Não preciso disso e ainda está caro.") == N  # mixed: left as classified
    assert screen(N, "Não preciso disso e ainda está caro.") == (N, None)
    assert price_override(N, "Não é questão de custo, não vejo valor nisso.") == N  # negated price word
    assert screen(I, "Antecipado não. Pagar o ano todo adiantado não cabe no nosso fluxo de caixa.") == (P, None)
    assert screen(I, "Não temos equipe pra implantar e o valor pesa demais.") == (I, None)  # its own gate holds


def test_attachment_to_the_current_solution_is_competition_a_mention_is_not():
    for line in ("Não é questão de custo nem de trabalho. Estamos bem com o que temos.",
                 "O escritório roda nesse sistema desde o primeiro dia, a equipe domina, e a gente não vai sair dele.",
                 "A equipe domina o sistema atual e não vamos trocar."):
        assert screen(N, line) == (C, None)
    assert screen(C, "O concorrente também mandou proposta.") == (C, "UNCORROBORATED_CATEGORY")
    assert screen(C, "Qual a diferença para o sistema que usamos?")[1] == "NON_OBJECTION_INFORMATION_REQUEST"


def test_authority_board_and_signature_blockers_pass_discovery_does_not():
    board = ("Eu gostei bastante. Só que compra desse porte passa pelo conselho da rede, e eu não posso "
             "comprometer a empresa sem a assinatura deles.")
    for line in (board, "Precisa passar pelo conselho.",
                 "Depende do comitê.", "Não posso comprometer sem aprovação."):
        assert screen(A, line) == (A, None), line
    for line in ("Meu sócio.", "Eu e meu diretor.", "Meu diretor participa.", "Sim, meu sócio participa."):
        assert screen(A, line) == (A, "UNCORROBORATED_CATEGORY"), line


def test_implementation_blocker_passes_a_question_about_it_does_not():
    assert screen(I, "Quem tocaria essa troca? A equipe já está no limite com o dia a dia; sem alguém dedicado "
                     "a isso, não tenho como seguir.") == (I, None)
    assert screen(I, "Sem alguém dedicado para implantar, não consigo seguir.") == (I, None)
    assert screen(I, "Quem faz a implantação?") == (I, "NON_OBJECTION_INFORMATION_REQUEST")


@pytest.mark.parametrize("text", [
    "Treinar a equipe em sistema novo sempre dá um trabalhinho, né.", "Treinar a equipe dá um trabalhinho.",
    "Quem faz a implantação?", "Como funciona o onboarding?", "Quanto tempo leva a implantação?"])
def test_an_implementation_topic_is_not_an_implementation_blocker(text):
    assert screen(I, text)[1] is not None


@pytest.mark.parametrize("text", [
    "Não temos equipe para implantar isso.", "Sem alguém dedicado não consigo seguir.",
    "A integração não funciona com o sistema que usamos.", "Não temos como fazer essa migração agora."])
def test_an_implementation_blocker_resists(text):
    assert screen(I, text) == (I, None)


def test_a_cash_flow_barrier_is_price_a_postponement_stays_timing():
    T = "TIMING_PRIORITY"
    assert screen(T, "Pagar o ano todo adiantado não cabe no nosso fluxo de caixa.") == (P, None)
    assert screen(T, "Não cabe no orçamento.") == (P, None)
    for line in ("Agora não, talvez depois da safra.", "Está caro agora, deixa para o ano que vem.",
                 "Por enquanto não cabe no caixa, mais para frente a gente vê."):
        assert screen(T, line) == (T, None), line


def test_negated_price_is_never_fast_pathed():
    for line in ("Não achei caro.", "Não está caro.", "O preço não é problema.", "Hoje o orçamento comporta."):
        assert fast_path_category(line) is None


def test_guard_costs_well_under_a_millisecond():
    texts = [t for _, t, _ in MATRIX_CASES]
    t0 = time.perf_counter()
    for t in texts:
        screen(N, t)
    assert (time.perf_counter() - t0) / len(texts) * 1000 < 1.0


# --- in the live session ------------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def kb():
    return load_objection_knowledge(GUIDANCE_KB)


def _session(kb, **cfg):
    provider, clock = FakeProvider(), Clock()
    return LiveSalesSession("m1", provider, kb, CLASSIFICATION_KB, LiveConfig(**cfg), clock=clock), provider, clock


def test_live_prompt_says_questions_buying_signals_and_negations_are_not_objections(kb):
    s, provider, clock = _session(kb, fast_path=False)
    _say(s, clock, 1, "lead", "Quanto custa a licença?")
    s.analyze()
    prompt = provider.prompts[0]
    assert "A question asking for information" in prompt and '"não achei caro"' in prompt
    assert "Annotate only resistance, rejection, hesitation or a blocking dependency" in prompt
    call = s._window_call(s.utterances)
    assert "A question asking for information" not in build_prompt(call, "E1")  # eval/post-call arms unchanged


def test_a_rejected_candidate_is_no_recommendation_with_its_reason_and_counted(kb, monkeypatch):
    monkeypatch.setitem(SCRIPT, "E no plano anual sai por quanto?", P)  # what qwen3 said in the baseline
    s, provider, clock = _session(kb)
    _say(s, clock, 1, "lead", "E no plano anual sai por quanto?")
    t = s.analyze()
    assert (t["outcome"], t["reason"], t["category"]) == ("NO_RECOMMENDATION", "NON_OBJECTION_INFORMATION_REQUEST", P)
    assert 0 <= t["guard_ms"] < 5 and provider.guidance_calls() == 0 and s.current() is None
    assert s.commercial.view()["objections"] == []  # never recorded as an objection
    assert s.guard_counters == {"classifier_candidates": 1, "classifier_guard_rejections": 1, "category_overrides": 0}
    assert s.guard_rejections_by_reason == {"NON_OBJECTION_INFORMATION_REQUEST": 1}


def test_pain_line_leaves_the_opportunity_as_the_seller_action(kb, monkeypatch):
    monkeypatch.setitem(SCRIPT, "Hoje tudo depende de mim na fazenda.", N)  # the known PAIN_AS_OBJECTION failure
    s, _, clock = _session(kb)
    _say(s, clock, 1, "closer", "Como funciona a rotina da fazenda?")
    clock.now += 6
    _say(s, clock, 2, "lead", "Hoje tudo depende de mim na fazenda.")
    t = s.analyze()
    assert (t["outcome"], t["reason"]) == ("NO_RECOMMENDATION", "PAIN_NOT_OBJECTION")
    _, ops, action = s.intelligence()
    assert "OP-06" in {o.playbook_op_id for o in ops.opportunities}
    assert (action.source, action.source_id.split(":")[0]) == ("OPPORTUNITY", "OP-06")


def test_competition_override_is_counted_and_recommended(kb, monkeypatch):
    monkeypatch.setitem(SCRIPT, "A equipe domina o sistema atual e não vamos trocar.", N)
    s, _, clock = _session(kb)
    _say(s, clock, 1, "lead", "A equipe domina o sistema atual e não vamos trocar.")
    t = s.analyze()
    assert (t["category_before"], t["category"]) == (N, C)
    assert t["reason"] not in REJECTION_REASONS and s.guard_counters["category_overrides"] == 1
    assert s.commercial.view()["objections"][0]["value"] == C  # accepted: recorded under the normalized category


def test_a_new_information_question_does_not_replace_the_open_objection(kb, monkeypatch):
    """Latest Utterance Anchoring + guard: the new line is a question; the earlier PRICE card stays."""
    monkeypatch.setitem(SCRIPT, "E quanto fica a parcela no plano anual?", P)
    s, _, clock = _session(kb)
    _say(s, clock, 1, "lead", "Gostei da proposta, mas achei muito caro.")
    assert s.analyze()["outcome"] == "RECOMMENDED"
    rec = s.current()
    clock.now += 30  # past the cooldown: a new PRICE episode would replace the card
    _say(s, clock, 2, "closer", "Temos o plano anual com desconto.")
    _say(s, clock, 3, "lead", "E quanto fica a parcela no plano anual?")
    t = s.analyze()
    assert (t["reason"], s.current()) == ("NON_OBJECTION_INFORMATION_REQUEST", rec)


def test_fast_path_candidates_pass_the_same_guard(kb):
    s, _, clock = _session(kb)
    _say(s, clock, 1, "lead", "Está muito caro.")
    t = s.analyze()
    assert (t["classification_source"], t["outcome"]) == ("deterministic_fast_path", "RECOMMENDED")
    assert s.guard_counters["classifier_candidates"] == 1 and "guard_ms" in t


def test_buying_question_is_a_buying_signal_in_the_commercial_state_and_op14_is_the_card(kb, monkeypatch):
    monkeypatch.setitem(SCRIPT, "Pode pagar no cartão da empresa?", I)  # what qwen3 said in the baseline
    s, _, clock = _session(kb)
    _say(s, clock, 1, "closer", "O investimento é de 12 mil no plano anual.")
    clock.now += 6
    _say(s, clock, 2, "lead", "Pode pagar no cartão da empresa?")
    assert s.analyze()["reason"] == "NON_OBJECTION_INFORMATION_REQUEST"
    t = s.extract()  # the fake facts model returns nothing: the lexical signal alone records it
    assert t["lexical_buying_signals"] == 1
    assert s.commercial.view()["buying_signals"] == [{"value": "Pode pagar no cartão da empresa",
                                                      "segment_ids": ["seg_2"], "status": "OBSERVED"}]
    _, ops, action = s.intelligence()
    assert "OP-14" in {o.playbook_op_id for o in ops.opportunities}
    assert (action.source, action.source_id.split(":")[0]) == ("OPPORTUNITY", "OP-14")


@pytest.mark.parametrize("line,value", [
    ("Pode pagar no cartão da empresa?", "Pode pagar no cartão da empresa"), ("Quando eu começo?", "Quando eu começo"),
    ("Como faço para entrar?", "Como faço para entrar"), ("Quando é o próximo encontro?", "Quando é o próximo encontro"),
    ("Como funciona o onboarding?", "Como funciona o onboarding"),
    ("Ótimo. Se eu fechar hoje, quando começo?", "Se eu fechar hoje, quando começo"),
    ("Quanto custa?", None), ("Vocês parcelam?", None), ("Achei caro.", None),  # not every price question
])
def test_buying_signal_value_is_the_leads_own_sentence(line, value):
    assert signals.buying_signal_value(line) == value
