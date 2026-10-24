"""Opportunity Detection v1 + Seller Action Arbitration + new compliance rules. Deterministic; no real Ollama."""
from __future__ import annotations

import dataclasses
import json
import re
import time

import pytest
from test_live_commercial_state import _SEG, Facts, _payload, _targets  # same folder
from test_live_session import _say
from test_playbook_compliance import MARKDOWN

from closer_ai.ai.objection_guidance import load_objection_knowledge
from closer_ai.demo.analyze_call import CLASSIFICATION_KB, GUIDANCE_KB
from closer_ai.live import signals as sig
from closer_ai.live.bench import SALES_SCENARIOS, run_sales, sales_summary
from closer_ai.live.commercial_state import CommercialEvent, CommercialState, objection_event
from closer_ai.live.opportunities import (
    Opportunity,
    OpportunityState,
    arbitrate,
    evaluate_opportunities,
    superseding,
)
from closer_ai.live.playbook import PLAYBOOK, evaluate, load_playbook, parse_playbook
from closer_ai.live.post_call_brief import render_markdown
from closer_ai.live.server import Runtime, parse_utterance
from closer_ai.live.session import LiveConfig, LiveSalesSession


@pytest.fixture(scope="module")
def kb():
    return load_objection_knowledge(GUIDANCE_KB)


def _facts(*events: CommercialEvent) -> dict:
    s = CommercialState()
    for e in events:
        s.apply(e)
    return s.view()


def _ev(etype, value, ids, role=None):
    return CommercialEvent(etype, value, tuple(ids), "lead", "OBSERVED", role)


def _segs(lines):
    return [(f"seg_{i}", role, text) for i, (role, text) in enumerate(lines, 1)]


def _ops(lines, facts=None, playbook=None):
    return evaluate_opportunities(playbook or load_playbook(), facts or _facts(), _segs(lines))


def _status(state) -> dict[str, str]:
    return {o.playbook_op_id: o.status for o in state.opportunities}


def _rule(lines, rule_id, facts=None):
    return next(r for r in evaluate(load_playbook(), facts or _facts(), _segs(lines)).rule_results
                if r.rule_id == rule_id)


SOCIO = _facts(_ev("STAKEHOLDER_IDENTIFIED", "sócio", ["seg_1", "seg_2"], "decision_participant"))


# --- machine-readable opportunities -----------------------------------------------------------------

def test_every_op_of_the_markdown_is_in_the_json_with_a_status():
    if not MARKDOWN.exists():
        pytest.skip("human playbook not in this checkout")
    ids = set(re.findall(r"\| (OP-\d{2}) \|", MARKDOWN.read_text(encoding="utf-8")))
    pb = load_playbook()
    assert ids == {o.id for o in pb.opportunities} and len(ids) == 22
    impl = {o.id for o in pb.opportunities if o.implementation == "IMPLEMENTED"}
    assert impl == {"OP-01", "OP-03", "OP-04", "OP-06", "OP-07", "OP-10", "OP-11", "OP-12", "OP-14"}
    assert {o.implementation for o in pb.opportunities} == {"IMPLEMENTED", "DEFERRED_LOW_CONFIDENCE",
                                                             "BLOCKED_BUSINESS_CONFIRMATION"}


def test_opportunity_schema_is_validated():
    data = json.loads(PLAYBOOK.read_text(encoding="utf-8"))
    op = next(o for o in data["opportunities"] if o["id"] == "OP-03")
    for broken in ({**op, "id": "OP-3"}, {**op, "action_type": "OFFER_DISCOUNT"}, {**op, "triggers": ["VIBES"]},
                   {**op, "resolved_by": [{"signal": "MAGIC"}]}, {**op, "requires_knowledge": ["unknown_item"]}):
        with pytest.raises(ValueError):
            parse_playbook({**data, "opportunities": [broken]})
    with pytest.raises(ValueError):
        parse_playbook({**data, "opportunities": [op, op]})
    with pytest.raises(ValueError):  # a deferred OP must say why
        parse_playbook({**data, "opportunities": [{"id": "OP-08", "implementation": "DEFERRED_LOW_CONFIDENCE"}]})


def test_active_needs_evidence():
    with pytest.raises(ValueError):
        Opportunity("OP-03:x#1", "OP-03", "ACTIVE", 2, "x", "t", "q", "a", "o", [])


# --- triggers: true and false positives -------------------------------------------------------------

@pytest.mark.parametrize(("line", "party"), [("Preciso falar com meu sócio antes de fechar.", "socio"),
                                             ("A decisão é do meu pai.", "pai"),
                                             ("Meu diretor precisa aprovar.", "diretor"),
                                             ("Mas preciso falar com ele antes de fechar.", None),
                                             ("Não posso decidir isso sozinho.", None)])
def test_decision_dependency(line, party):
    assert sig.decision_dependency(line) == (True, party)


@pytest.mark.parametrize("line", ["Meu sócio.", "Sim, meu sócio.", "Eu e minha esposa.", "O financeiro também participa.",
                                  "Meu sócio gostou bastante."])
def test_discovery_is_not_a_decision_dependency(line):
    assert sig.decision_dependency(line) == (False, None)


@pytest.mark.parametrize(("kind", "yes", "no"), [
    ("THINK_IT_OVER", ["Vou pensar.", "Preciso avaliar com calma.", "Me manda por escrito.", "Me manda tudo por e-mail."],
     ["Pensei nisso ontem.", "Avaliamos outras opções no passado."]),
    ("BUYING_QUESTION", ["Pode ser no cartão da empresa?", "E se eu pagar no cartão da empresa?", "Como faço para entrar?",
                         "Quando eu começo?", "Em quantas parcelas dá?", "Quando é o próximo encontro?"],
     ["Gostei bastante.", "Interessante, quero saber mais.", "O cartão de vacina está em dia."]),
    ("OWNER_DEPENDENCY", ["Tudo depende de mim.", "Não consigo sair da operação.", "O gerente não decide nada."],
     ["Depende do clima.", "Eu cuido da parte comercial."]),
    ("FINANCIAL_BLINDNESS", ["Eu nem sei minha margem.", "Não sei quanto sobra no fim do mês.",
                             "Não tenho controle do custo."], ["Sei bem minha margem.", "Não sei se vale a pena."]),
    ("TIME_CONCERN", ["Não tenho tempo para mais um programa.", "Quanto tempo isso toma por semana?"],
     ["Isso faz a equipe perder muito tempo.", "Faz tempo que penso nisso."]),
    ("PRIOR_BAD_EXPERIENCE", ["Já fiz duas mentorias e não coloquei nada em prática.",
                              "Já comprei um curso e não usei."], ["Já fiz uma mentoria muito boa.", "Fiz faculdade."]),
    ("SUCCESSION", ["Meu filho vai assumir a fazenda.", "Estou passando a gestão para meu genro."],
     ["Meu filho estuda fora.", "Passei na fazenda ontem."]),
    ("CASH_TIGHT", ["O caixa está apertado.", "A safra só entra em março."], ["O caixa da fazenda é organizado."]),
])
def test_lead_trigger_signals(kind, yes, no):
    for line in yes:
        assert kind in {s.type for s in sig.extract([("seg_1", "lead", line)])}, line
    for line in no:
        assert kind not in {s.type for s in sig.extract([("seg_1", "lead", line)])}, line
    assert not sig.extract([("seg_1", "closer", yes[0])]) or kind not in {
        s.type for s in sig.extract([("seg_1", "closer", yes[0])])}  # the closer saying it is not a trigger


@pytest.mark.parametrize(("kind", "yes", "no"), [
    ("DECISION_ASK", ["Faz sentido a gente seguir?", "Vamos fechar?", "Você quer entrar?", "Faz sentido a gente seguir então?"],
     ["Faz sentido isso aqui?", "Vamos seguir para o próximo slide.", "Vamos seguir com a apresentação?"]),
    ("CAUSE_PROBE", ["O que exatamente você precisa pensar?", "O que está na balança?", "Caro em relação a quê?",
                     "O que você precisa avaliar?"], ["Pensa com calma.", "Vou te mandar o material."]),
    ("PRICE_PRESENTED", ["O investimento é de 63 mil à vista.", "Fica em R$ 53.000 à vista."],
     ["Você disse que perde R$ 10 mil por ano.", "Uma consultoria individual começa em R$ 400 mil."]),
    ("PAYMENT_TERMS_MENTIONED", ["Pode ser em 12x no cartão.", "Aceitamos Pix ou boleto."], ["Vamos conversar."]),
    ("SECOND_SEAT_OFFERED", ["A segunda cadeira é para o seu sócio.", "Traga seu sócio."], ["Na segunda-feira te ligo."]),
])
def test_closer_signals(kind, yes, no):
    for line in yes:
        assert kind in {s.type for s in sig.extract([("seg_1", "closer", line)])}, line
    for line in no:
        assert kind not in {s.type for s in sig.extract([("seg_1", "closer", line)])}, line


# --- OP-03 -----------------------------------------------------------------------------------------

def test_op03_not_on_discovery():
    state = _ops([("closer", "Quem participa da decisão?"), ("lead", "Meu sócio.")], SOCIO)
    assert state.opportunities == ()


def test_op03_blocker_active_then_resolved_by_a_meeting_with_a_pronoun():
    lines = [("closer", "Quem participa da decisão?"), ("lead", "Meu sócio."),
             ("lead", "Mas preciso falar com ele antes de fechar.")]
    state = _ops(lines, SOCIO)
    (o,) = state.opportunities
    assert (o.playbook_op_id, o.status, o.subject, o.trigger_segment_ids) == ("OP-03", "ACTIVE", "socio", ["seg_3"])
    assert "2ª cadeira" in o.action  # second_chair is CONFIRMED business knowledge
    (o,) = _ops([*lines, ("closer", "Vamos marcar com ele terça às 14h.")], SOCIO).opportunities
    assert (o.status, o.resolution_reason, o.resolved_sequence) == ("RESOLVED", "DECISION_MEETING_SCHEDULED [seg_4]", 4)


def test_op03_from_the_objection_engine_and_the_lexical_signal_is_one_opportunity():
    facts = _facts(objection_event("AUTHORITY_INTERNAL_BUY_IN", ["seg_2"]))
    lines = [("closer", "O que achou?"), ("lead", "Preciso falar com meu sócio antes de fechar."),
             ("closer", "Entendo."), ("lead", "Vou conversar com ele hoje à noite."),
             ("lead", "Preciso falar com meu sócio, de verdade.")]
    (o,) = _ops(lines, facts).opportunities
    assert o.trigger_segment_ids == ["seg_2"] and o.supporting_segment_ids == ["seg_5"]  # dedup, no second OP-03


def test_op03_resolved_by_the_second_seat_only_while_it_is_confirmed(monkeypatch):
    lines = [("lead", "Preciso falar com meu sócio antes de fechar."), ("closer", "A segunda cadeira é para o seu sócio.")]
    assert _status(_ops(lines)) == {"OP-03": "RESOLVED"}
    pb = load_playbook()
    pending = dataclasses.replace(pb, business_knowledge=tuple(
        {**i, "business_status": "PENDING_CONFIRMATION"} if i["id"] == "second_chair" else i
        for i in pb.business_knowledge))
    (o,) = _ops(lines, playbook=pending).opportunities
    assert o.status == "ACTIVE" and "2ª cadeira" not in o.action  # never suggests pending knowledge


def test_op03_already_covered_before_the_blocker_is_suppressed():
    lines = [("closer", "A segunda cadeira é para o seu sócio."), ("lead", "Preciso falar com meu sócio antes de fechar.")]
    (o,) = _ops(lines).opportunities
    assert o.status == "SUPPRESSED" and o.supporting_segment_ids == ["seg_1"]


# --- OP-12, OP-14 and the others: trigger -> resolve -------------------------------------------------

@pytest.mark.parametrize(("op", "trigger", "resolve"), [
    ("OP-12", "Vou pensar.", "O que exatamente você precisa pensar?"),
    ("OP-14", "Pode ser no cartão da empresa?", "Faz sentido a gente seguir?"),
    ("OP-06", "Tudo depende de mim.", "Isso é exatamente o pilar Fazenda Autônoma."),
    ("OP-07", "Eu nem sei minha margem.", "E qual é o seu custo por arroba?"),
    ("OP-10", "Não tenho tempo para mais um programa.", "O problema é a agenda ou a prioridade?"),
    ("OP-11", "Já fiz duas mentorias e não coloquei nada em prática.", "O que faltou para colocar em prática?"),
    ("OP-04", "Meu filho vai assumir a fazenda.", "Isso entra no pilar Alavanca do Legado."),
    ("OP-01", "O caixa está apertado.", "Quando entra o caixa da safra?"),
])
def test_trigger_then_resolve(op, trigger, resolve):
    lines = [("closer", "Como está hoje?"), ("lead", trigger)]
    assert _status(_ops(lines)) == {op: "ACTIVE"}
    assert _status(_ops([*lines, ("closer", "Entendi.")])) == {op: "ACTIVE"}  # an acknowledgement is not coverage
    assert _status(_ops([*lines, ("closer", resolve)])) == {op: "RESOLVED"}


def test_event_like_opportunities_reopen_only_on_a_new_trigger_after_resolution():
    lines = [("lead", "Vou pensar."), ("lead", "Vou pensar mesmo."), ("closer", "O que está na balança?")]
    assert [o.status for o in _ops(lines).opportunities] == ["RESOLVED"]  # repeated trigger: one OP-12
    later = [*lines, ("lead", "Ok. Mas ainda vou pensar.")]
    assert [(o.id, o.status) for o in _ops(later).opportunities] == [("OP-12:call#1", "RESOLVED"),
                                                                     ("OP-12:call#2", "ACTIVE")]
    state_like = [("lead", "Tudo depende de mim."), ("closer", "É o pilar Fazenda Autônoma."),
                  ("lead", "Tudo depende de mim, de verdade.")]
    assert [o.status for o in _ops(state_like).opportunities] == ["RESOLVED"]  # never reopens


def test_buying_signal_from_the_commercial_state():
    facts = _facts(_ev("BUYING_SIGNAL_DETECTED", "quero começar este mês", ["seg_1"]))
    assert _status(_ops([("lead", "Se der certo, quero começar este mês.")], facts)) == {"OP-14": "ACTIVE"}


def test_no_opportunity_from_generic_interest_or_neutral_lines():
    lines = [("lead", "Gostei bastante da apresentação."), ("lead", "Interessante."),
             ("lead", "Isso faz a equipe perder muito tempo."), ("lead", "Eu e minha esposa."),
             ("closer", "Não tenho tempo, preciso falar com meu sócio.")]  # the closer's words never trigger
    assert _ops(lines).opportunities == ()


# --- business safety --------------------------------------------------------------------------------

def test_no_opportunity_suggests_pending_business_information():
    pb = load_playbook()
    pending_words = ("12x", "5.700", "53", "63", "30 dias", "2 h", "Turci", "Caires", "sem juros", "presencia")
    for od in pb.opportunities:
        if od.implementation != "IMPLEMENTED":
            continue
        assert pb.confirmed(od.requires_knowledge), od.id
        for text in (od.action, *(v["action"] for v in od.variants)):
            assert not any(w in text for w in pending_words), (od.id, text)
    blocked = [od for od in pb.opportunities if od.implementation == "BLOCKED_BUSINESS_CONFIRMATION"]
    assert blocked and all(not pb.confirmed(od.requires_knowledge) for od in blocked)


def test_an_opportunity_whose_knowledge_becomes_pending_is_suppressed():
    pb = load_playbook()
    pending = dataclasses.replace(pb, business_knowledge=tuple(
        {**i, "business_status": "PENDING_CONFIRMATION"} if i["id"] == "pillar_fazenda_autonoma" else i
        for i in pb.business_knowledge))
    (o,) = _ops([("lead", "Tudo depende de mim.")], playbook=pending).opportunities
    assert o.status == "SUPPRESSED" and "BLOCKED_BUSINESS_CONFIRMATION" in o.reason
    assert arbitrate(None, None, _ops([("lead", "Tudo depende de mim.")], playbook=pending)) is None


# --- arbitration -----------------------------------------------------------------------------------

REC = {"id": 7, "category": "AUTHORITY_INTERNAL_BUY_IN", "label": "Decisão / aprovação interna",
       "lead_said": "Preciso falar com meu sócio antes de fechar.", "question": "Quem mais participa dessa decisão?",
       "objective": None}


def test_one_seller_action_with_a_deterministic_priority():
    lines = [("lead", "Preciso falar com meu sócio antes de fechar."), ("lead", "Vou pensar."),
             ("lead", "Pode ser no cartão da empresa?")]
    state = _ops(lines)
    assert [o.playbook_op_id for o in state.active()] == ["OP-14", "OP-03", "OP-12"]
    a = arbitrate(None, None, state)
    assert (a.source, a.source_id, a.action) == ("OPPORTUNITY", "OP-14:call#1", "Há sinal de compra. Peça a decisão.")
    assert arbitrate(None, None, state, {"OP-14:call#1"}).source_id == "OP-03:socio#1"  # dismissed -> next


def test_the_objection_card_wins_over_its_own_structural_opportunity():
    state = _ops([("lead", "Preciso falar com meu sócio antes de fechar.")])
    a = arbitrate(REC, 1, state)
    assert (a.source, a.source_id, a.action) == ("OBJECTION", "rec:7", REC["question"])  # OP-03 stays internal
    assert arbitrate(None, None, state).source_id == "OP-03:socio#1"  # after the card is gone


def test_a_newer_buying_signal_takes_over_an_older_objection_card():
    state = _ops([("lead", "Preciso falar com meu sócio antes de fechar."), ("lead", "Pode ser no cartão da empresa?")])
    assert arbitrate(REC, 1, state).source_id == "OP-14:call#1"
    assert arbitrate(REC, 2, state).source == "OBJECTION"  # same line: the objection guidance wins


# --- new compliance rules ---------------------------------------------------------------------------

def test_e5_r1_timing_before_price():
    probe, price = ("closer", "Isso é prioridade neste semestre?"), ("closer", "O investimento é de 63 mil à vista.")
    assert _rule([probe, price], "E5-R1").status == "SATISFIED"
    assert _rule([price, probe], "E5-R1").status == "PENDING"  # never a violation (limited recall)
    assert _rule([probe], "E5-R1").status == "SATISFIED"


def test_e9_price_rules_ignore_the_leads_money():
    lead_money = ("lead", "A gente perde uns R$ 10 mil por ano.")
    assert _rule([lead_money], "E9-R1").status == "PENDING"
    lines = [lead_money, ("closer", "O investimento é de 63 mil à vista ou em 12x.")]
    assert _rule(lines, "E9-R1").status == "SATISFIED" and _rule(lines, "E9-R3").status == "SATISFIED"
    assert _rule([("closer", "O valor do programa é R$ 63.000.")], "E9-R3").status == "PENDING"
    assert _rule([("closer", "A segunda cadeira é para o seu sócio.")], "E9-R4").status == "SATISFIED"


def test_e11_rules():
    price, ask = ("closer", "O investimento é de 63 mil à vista."), ("closer", "Faz sentido a gente seguir?")
    assert _rule([ask], "E11-R1").status == "NOT_APPLICABLE"
    assert _rule([price, ask], "E11-R1").status == "SATISFIED" and _rule([price], "E11-R1").status == "PENDING"
    think = ("lead", "Vou pensar.")
    assert _rule([think], "E11-R2").status == "PENDING"
    assert _rule([think, ("closer", "O que está na balança?")], "E11-R2").status == "SATISFIED"
    buy = ("lead", "Pode ser no cartão da empresa?")
    assert _rule([buy, ask], "E11-R4").status == "SATISFIED"
    late = [buy, ("closer", "Sim."), ("lead", "Ok."), ("closer", "Deixa eu mostrar."), ("lead", "Certo."), ask]
    assert _rule(late, "E11-R4").status == "PENDING"  # asked after more than 2 closer turns


def test_e12_r3_and_e7_r1():
    assert _rule([("closer", "Eu te ligo terça às 14h.")], "E12-R3").status == "SATISFIED"
    assert _rule([("lead", "Eu te ligo terça às 14h.")], "E12-R3").status == "PENDING"
    blocks = [("closer", "São três pilares: Lucro Incontestável, Fazenda Autônoma e Legado."),
              ("closer", "Você começa com um projeto de 6 semanas e placar semanal."),
              ("closer", "E tem os encontros presenciais ao longo do ano.")]
    assert _rule(blocks[:2], "E7-R1").status == "PENDING" and _rule(blocks, "E7-R1").status == "SATISFIED"


# --- live session / runtime -------------------------------------------------------------------------

EXTRACTOR = {  # lead text -> extractor answer (event_type, value, role, cite the previous line)
    "Preciso falar com meu sócio antes de fechar.": [
        ("STAKEHOLDER_IDENTIFIED", "meu sócio", "decision_participant", False),
        ("DECISION_PROCESS_IDENTIFIED", "falar com meu sócio", "none", False)],
    "Meu sócio.": [("STAKEHOLDER_IDENTIFIED", "Meu sócio", "decision_participant", True)],
    "Mas preciso falar com ele antes de fechar.": [("DECISION_PROCESS_IDENTIFIED", "falar com ele", "none", False)],
    "Achei caro e preciso falar com meu sócio.": [("STAKEHOLDER_IDENTIFIED", "meu sócio", "mentioned", False),
                                                  ("DECISION_PROCESS_IDENTIFIED", "falar com meu sócio", "none", False)],
    "Eu e minha esposa.": [("STAKEHOLDER_IDENTIFIED", "minha esposa", "mentioned", False)],
    "O financeiro também participa.": [("STAKEHOLDER_IDENTIFIED", "O financeiro", "decision_participant", False)],
    "Isso faz a equipe perder muito tempo.": [("IMPACT_IDENTIFIED", "a equipe perder muito tempo", "none", False)],
}


def _extractor(prompt):
    targets, segs = _targets(prompt), _SEG.findall(prompt)
    events = []
    for i, (sid, _, text) in enumerate(segs):
        if sid in targets:
            for etype, value, role, prev in EXTRACTOR.get(text, []):
                events.append({"event_type": etype, "value": value, "stakeholder_role": role,
                               "segment_ids": [segs[i - 1][0], sid] if prev and i else [sid]})
    return {"events": events}


def _runtime(kb):
    rt = Runtime(Facts(_extractor), LiveConfig(), {"Matheus", "Closer Teste"}, log=lambda _: None)
    rt.knowledge = kb
    return rt


def test_replay_scenarios_with_a_fake_model(kb):
    rt = _runtime(kb)
    rows = [run_sales(rt, name, lines, expect, cps, check_objections=False) for name, lines, expect, cps in SALES_SCENARIOS]
    assert [(r["scenario"], r["errors"]) for r in rows if not r["ok"]] == []
    summary = sales_summary(rows)
    assert (summary["false_opportunities"], summary["duplicate_opportunities"], summary["seller_action_conflicts"]) == (0, 0, 0)
    assert {r["scenario"]: r["missed_at_finalize"] for r in rows}["no_decision_ask"] == ["OP-14"]
    assert len(rows) >= 10


def test_acceptance_call_end_to_end(kb):
    rt = _runtime(kb)
    name, lines, expect, cps = next(x for x in SALES_SCENARIOS if x[0] == "acceptance")
    row = run_sales(rt, name, lines, expect, cps, check_objections=False)
    assert row["ok"], row["errors"]
    s = next(iter(rt.sessions.values()))
    assert s.counters["recommendations_created"] <= 1  # only the authority blocker can be an objection
    md = render_markdown(s.finalize()).splitlines()
    for line in ("## Opportunities", "### Resolved", "### Missed", "### Suppressed"):
        assert line in md, line
    assert md[md.index("### Missed") + 1] == "- -"  # everything was covered
    assert any(x.startswith("- OP-03 — Decisor ainda não envolvido: coberto (DECISION_MEETING_SCHEDULED [seg_4])")
               for x in md)
    assert "Oportunidades aproveitadas: OP-03 (Decisor ainda não envolvido); OP-14 (Sinal de compra)." in s.brief.summary


def test_finalize_lists_active_opportunities_as_missed_only_then(kb):
    rt = _runtime(kb)
    for seq, (role, text) in enumerate([("closer", "Esse é o formato."), ("lead", "Quando eu começo, se eu entrar?")], 1):
        rt.receive(parse_utterance(_payload(seq, role, text), rt.closer_names, 1.0), background=False)
    view = rt.recommendation("m")
    assert view["opportunities"]["opportunities"][0]["status"] == "ACTIVE"  # during the call: never "missed"
    assert view["seller_action"]["source_id"] == "OP-14:call#1"
    brief = rt.sessions["m"].finalize()
    assert [o["playbook_op_id"] for o in brief.opportunities["missed"]] == ["OP-14"]
    assert "Oportunidades não aproveitadas: OP-14 (Sinal de compra)." in brief.summary


def test_dismissing_an_opportunity_hides_it_from_the_dock(kb):
    rt = _runtime(kb)
    for seq, (role, text) in enumerate([("lead", "Vou pensar."), ("lead", "Tudo depende de mim.")], 1):
        rt.receive(parse_utterance(_payload(seq, role, text), rt.closer_names, 1.0), background=False)
    first = rt.recommendation("m")["seller_action"]["source_id"]
    assert first == "OP-12:call#1"
    rt.sessions["m"].dismiss(first)
    view = rt.recommendation("m")
    assert view["seller_action"]["source_id"] == "OP-06:call#1"
    assert {o["id"]: o["status"] for o in view["opportunities"]["opportunities"]}[first] == "ACTIVE"  # still known
    assert view.get("debug") is None  # counters only with --debug


def test_recovery_rebuilds_opportunities_without_recommendations(kb):
    lines = [("closer", "Quem participa da decisão?"), ("lead", "Meu sócio."), ("lead", "Vou pensar."),
             ("lead", "Tudo depende de mim.")]
    old = _runtime(kb)
    for seq, (role, text) in enumerate(lines, 1):
        old.receive(parse_utterance(_payload(seq, role, text), old.closer_names, 1.0), background=False)
    before = old.recommendation("m")["opportunities"]
    new = _runtime(kb)
    new.rehydrate("m", [_payload(seq, r, t) for seq, (r, t) in enumerate(lines, 1)])
    deadline = time.time() + 5
    while "m" in new._busy and time.time() < deadline:
        time.sleep(0.01)
    s = new.sessions["m"]
    after = new.recommendation("m")["opportunities"]
    assert after == before and {o["playbook_op_id"] for o in after["opportunities"]} == {"OP-12", "OP-06"}
    assert (s.counters["analyses_started"], s.counters["recommendations_created"]) == (0, 0)
    new.rehydrate("m", [_payload(seq, r, t) for seq, (r, t) in enumerate(lines, 1)])  # resent: no duplicates
    assert new.recommendation("m")["opportunities"] == before


def test_debug_view_has_the_counters_and_timings(kb):
    rt = Runtime(Facts(_extractor), LiveConfig(), {"Matheus"}, log=lambda _: None, debug=True)
    rt.knowledge = kb
    rt.receive(parse_utterance(_payload(1, "lead", "Vou pensar."), rt.closer_names, 1.0), background=False)
    d = rt.recommendation("m")["debug"]
    assert d["seller_action_source"] == "OPPORTUNITY" and d["seller_action_priority"] == 3
    assert d["opportunity_counters"]["opportunities_created"] == 1 and d["seller_actions_from_opportunity"] == 1
    assert {"compliance_ms", "opportunity_ms", "arbitration_ms"} <= set(d)


def test_overhead_is_well_under_a_millisecond_per_typical_call(kb):
    s = LiveSalesSession("m1", Facts(_extractor), kb, CLASSIFICATION_KB, LiveConfig())
    clock = type("C", (), {"now": 1.0})()
    for seq in range(1, 41):
        _say(s, clock, seq, "closer" if seq % 2 else "lead", f"Linha {seq} sobre a fazenda, a equipe e os custos.")
    timings = []
    for _ in range(20):
        s.intelligence()
        timings.append(s.compliance_ms + s.opportunity_ms + s.arbitration_ms)
    assert min(timings) < 20  # measured ~1 ms for 40 lines; loose bound for slow CI


# --- found with the real qwen3:8b (Commercial State extraction varies) ------------------------------

def test_e6_r1_from_the_answer_to_who_decides_even_without_an_extracted_fact():
    lines = [("closer", "Além de você, quem participa da decisão?"), ("lead", "Meu sócio.")]
    r = _rule(lines, "E6-R1")  # no Commercial State fact at all
    assert (r.status, r.segment_ids) == ("SATISFIED", ("seg_1", "seg_2"))
    assert _ops(lines).opportunities == ()  # discovery: still no OP-03
    assert _rule([("closer", "Como foi a semana?"), ("lead", "Meu sócio viajou.")], "E6-R1").status == "PENDING"


def test_e6_r2_follows_the_leads_own_dependency_when_the_extractor_says_only_mentioned():
    facts = _facts(_ev("STAKEHOLDER_IDENTIFIED", "sócio", ["seg_2"], "mentioned"))
    lines = [("closer", "O que achou?"), ("lead", "Preciso falar com meu sócio antes de fechar.")]
    assert _rule(lines, "E6-R1", facts).status == "SATISFIED" and _rule(lines, "E6-R2", facts).status == "PENDING"
    done = [*lines, ("closer", "Vamos marcar com seu sócio terça às 14h?")]
    assert _rule(done, "E6-R2", facts).status == "SATISFIED" and _status(_ops(done, facts)) == {"OP-03": "RESOLVED"}


def test_a_pronoun_dependency_points_to_the_latest_person_mentioned():
    facts = _facts(_ev("STAKEHOLDER_IDENTIFIED", "pai", ["seg_2"], "mentioned"))
    lines = [("closer", "E a fazenda?"), ("lead", "É do meu pai."), ("lead", "Preciso falar com ele antes de fechar."),
             ("closer", "Vamos marcar com seu pai quinta às 10h?")]
    assert _rule(lines, "E6-R2", facts).status == "SATISFIED"
    (o,) = _ops(lines, facts).opportunities
    assert (o.subject, o.status) == ("pai", "RESOLVED")


def test_in_the_session_a_newer_buying_signal_takes_over_the_active_objection_card(kb):
    rt = _runtime(kb)
    for seq, (role, text) in enumerate([("closer", "O que achou?"), ("lead", "Preciso falar com meu sócio antes de fechar.")], 1):
        rt.receive(parse_utterance(_payload(seq, role, text), rt.closer_names, 1.0), background=False)
    assert rt.recommendation("m")["seller_action"]["source"] == "OBJECTION"  # OP-03 is internal meanwhile
    rt.receive(parse_utterance(_payload(3, "lead", "Pode ser no cartão da empresa?"), rt.closer_names, 1.0),
               background=False)
    view = rt.recommendation("m")
    assert view["state"] == "ACTIVE" and view["seller_action"]["source_id"] == "OP-14:call#1"


# --- stale objection recommendations (semantic lifecycle) -------------------------------------------

def _stream(rt, lines):
    views = []
    for seq, (role, text) in enumerate(lines, 1):
        rt.receive(parse_utterance(_payload(seq, role, text), rt.closer_names, 1.0), background=False)
        views.append(rt.recommendation("m"))
    return views


def _card(view):
    sa = view["seller_action"]
    return None if sa is None else "OBJECTION" if sa["source"] == "OBJECTION" else sa["source_id"].split(":")[0]


def test_authority_card_does_not_resurface_after_op03_resolved(kb):
    rt = _runtime(kb)
    # the full acceptance call (with "Meu sócio." first) runs with the real qwen3:8b: see the bench
    views = _stream(rt, [("closer", "O que achou?"), ("lead", "Mas preciso falar com meu sócio antes de fechar."),
                         ("closer", "Vamos marcar com ele terça às 14h."),
                         ("lead", "E se eu pagar no cartão da empresa?"), ("closer", "Faz sentido a gente seguir?")])
    assert [_card(v) for v in views] == [None, "OBJECTION", None, "OP-14", None]
    s = rt.sessions["m"]
    assert (s.current_recommendation.state, s.current_recommendation.superseded_by) == ("SUPERSEDED", "OP-03:socio#1")
    assert views[-1]["state"] == "NONE" and s.counters["recommendations_superseded"] == 1


def test_price_card_retires_after_a_newer_buying_signal_turned_into_a_decision_ask(kb):
    rt = _runtime(kb)
    views = _stream(rt, [("closer", "O investimento é de 63 mil."), ("lead", "Achei caro pra gente."),
                         ("closer", "Entendo. Caro comparando com o quê?"),
                         ("lead", "Posso pagar no cartão da empresa?"), ("closer", "Faz sentido a gente seguir?")])
    assert [_card(v) for v in views] == [None, "OBJECTION", "OBJECTION", "OP-14", None]
    assert rt.sessions["m"].current_recommendation.superseded_by == "OP-14:call#1"


def test_price_card_stays_after_a_neutral_fact(kb):
    rt = _runtime(kb)
    views = _stream(rt, [("closer", "O investimento é de 63 mil."), ("lead", "Achei caro pra gente."),
                         ("closer", "Entendo."), ("lead", "Hoje temos cinco pessoas no time.")])
    assert [_card(v) for v in views][1:] == ["OBJECTION"] * 3
    assert rt.sessions["m"].counters["recommendations_superseded"] == 0


def _op(op_id, status, created, resolved=None):
    return Opportunity(f"{op_id}:x#1", op_id, status, 1, "x", "t", "q", "a", "o", ["seg_1"],
                       created_sequence=created, resolved_sequence=resolved)


def test_superseding_needs_progress_after_the_objection_line():
    def by(cat, seq, *ops):
        o = superseding(cat, seq, OpportunityState(tuple(ops), {}))
        return o and o.playbook_op_id

    assert by("AUTHORITY_INTERNAL_BUY_IN", 3, _op("OP-03", "RESOLVED", 3, 4)) == "OP-03"
    assert by("PRICE_BUDGET", 3, _op("OP-03", "RESOLVED", 3, 4)) is None  # not its structural OP
    assert by("AUTHORITY_INTERNAL_BUY_IN", 5, _op("OP-03", "RESOLVED", 2, 4)) is None  # resolved before it
    assert by("PRICE_BUDGET", 2, _op("OP-14", "RESOLVED", 4, 5)) == "OP-14"
    assert by("PRICE_BUDGET", 4, _op("OP-14", "RESOLVED", 2, 5)) is None  # buying signal BEFORE the objection
    assert by("PRICE_BUDGET", 2, _op("OP-14", "ACTIVE", 4)) is None  # no decision ask yet (OP-14 shows anyway)
    assert by("NEED_TO_THINK", 2, _op("OP-12", "RESOLVED", 2, 3)) is None  # a probe never retires
    assert by("PRICE_BUDGET", None, _op("OP-14", "RESOLVED", 4, 5)) is None  # unknown line: conservative


def test_replay_has_no_stale_resurfacing(kb):
    rows = [run_sales(_runtime(kb), n, ls, e, c, check_objections=False) for n, ls, e, c in SALES_SCENARIOS]
    summary = sales_summary(rows)
    assert summary["stale_recommendation_resurfacing"] == 0
    assert summary["recommendations_superseded"] >= 2  # acceptance + price_then_buying_signal


# --- captions without "?" ---------------------------------------------------------------------------

@pytest.mark.parametrize("text, kind", [
    ("Qual é a sua prioridade hoje", "TIMING_PROBE"),
    ("Entendo. Como está o seu caixa este ano", "TIMING_PROBE"),
    ("E qual seria o seu custo por arroba hoje", "NUMBER_PROBE"),
    ("Quanto tempo você consegue dedicar por semana", "TIME_PROBE"),
    ("O que faltou para colocar em prática", "EXPERIENCE_PROBE"),
])
def test_probes_without_question_mark_by_interrogative_structure(text, kind):
    assert kind in {s.type for s in sig.line_signals("seg_1", "closer", text)}


@pytest.mark.parametrize("text", [
    "O momento é agora.", "Como eu falei, o tempo é curto.", "A prioridade é sua.", "A margem melhora muito.",
    "Quando você entrar, a agenda é fixa.", "Vamos seguir.",
])
def test_statements_are_not_probes(text):
    probes = {"TIMING_PROBE", "NUMBER_PROBE", "TIME_PROBE", "EXPERIENCE_PROBE", "DECISION_ASK"}
    assert not probes & {s.type for s in sig.line_signals("seg_1", "closer", text)}
