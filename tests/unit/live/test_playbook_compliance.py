"""Machine-readable playbook + Playbook Compliance Engine v1. Deterministic; no real Ollama."""
from __future__ import annotations

import re
import time
from pathlib import Path

import pytest
from test_live_commercial_state import _SEG, Facts, _payload, _run, _targets  # same folder

from closer_ai.ai.objection_guidance import load_objection_knowledge
from closer_ai.demo.analyze_call import CLASSIFICATION_KB, GUIDANCE_KB
from closer_ai.live.commercial_state import CommercialEvent, CommercialState, objection_event
from closer_ai.live.playbook import (
    PLAYBOOK,
    ComplianceResult,
    evaluate,
    load_playbook,
    parse_playbook,
)
from closer_ai.live.post_call_brief import render_markdown
from closer_ai.live.server import Runtime, parse_utterance
from closer_ai.live.session import LiveConfig, LiveSalesSession
from closer_ai.live.signals import phrase_hits, quantity, schedule

MARKDOWN = Path(PLAYBOOK).with_name("PLAYBOOK_COMERCIAL_AGROTALENTO_v1.md")


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


def _eval(facts=None, lines=()):
    segs = [(f"seg_{i}", role, text) for i, (role, text) in enumerate(lines, 1)]
    return evaluate(load_playbook(), facts or _facts(), segs)


def _r(state, rule_id) -> ComplianceResult:
    return next(r for r in state.rule_results if r.rule_id == rule_id)


# lead text -> extractor answer (event_type, value, role, cite the previous line); invented, no client data
TABLE = {
    "Fazemos tudo num processo manual.": [("PAIN_IDENTIFIED", "processo manual", "none", False)],
    "Isso faz a equipe perder muito tempo.": [("IMPACT_IDENTIFIED", "a equipe perder muito tempo", "none", False)],
    "A gente perde 8 horas por semana.": [("IMPACT_IDENTIFIED", "perde 8 horas por semana", "none", False)],
    "Meu sócio.": [("STAKEHOLDER_IDENTIFIED", "Meu sócio", "decision_participant", True)],
    "Sim, meu sócio.": [("STAKEHOLDER_IDENTIFIED", "meu sócio", "decision_participant", True)],
    "Preciso falar com meu sócio antes de fechar.": [
        ("STAKEHOLDER_IDENTIFIED", "meu sócio", "decision_participant", False),
        ("DECISION_PROCESS_IDENTIFIED", "falar com meu sócio", "none", False)],
    "Fechado.": [],
    "Pode ser.": [],
}


def _extractor(prompt):
    targets, segs = _targets(prompt), _SEG.findall(prompt)
    events = []
    for i, (sid, _, text) in enumerate(segs):
        if sid in targets:
            for etype, value, role, prev in TABLE.get(text, []):
                events.append({"event_type": etype, "value": value, "stakeholder_role": role,
                               "segment_ids": [segs[i - 1][0], sid] if prev and i else [sid]})
    return {"events": events}


def _live(kb):
    provider = Facts(_extractor)
    s = LiveSalesSession("m1", provider, kb, CLASSIFICATION_KB, LiveConfig(), clock=_Clock())
    return s, provider, s.clock


class _Clock:
    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now


# --- machine-readable playbook ----------------------------------------------------------------------

def test_every_rule_id_of_the_markdown_is_in_the_machine_readable_playbook():
    if not MARKDOWN.exists():
        pytest.skip("human playbook not in this checkout")
    ids = set(re.findall(r"`(E\d+-R\d+)`", MARKDOWN.read_text(encoding="utf-8")))
    ids |= set(re.findall(r"\| (N/A-\d) \|", MARKDOWN.read_text(encoding="utf-8")))
    pb = load_playbook()
    assert ids == {r.id for r in pb.rules}
    assert [s for s in pb.stages if s != "NA"] == [f"E{i}" for i in range(1, 13)]
    assert {r.rule_class for r in pb.rules} == {"REQUIRED", "RECOMMENDED", "PROHIBITED"}  # OPTIONAL: no ids yet


def test_the_schema_is_validated():
    good = {"version": "v", "stages": [{"id": "E1", "title": "Abertura"}],
            "rules": [{"id": "E1-R1", "stage": "E1", "class": "REQUIRED", "title": "x", "evidence_type": "y"}]}
    assert parse_playbook(good).rules[0].id == "E1-R1"
    for broken in ({**good, "rules": [{**good["rules"][0], "class": "OBRIGATORIO"}]},
                   {**good, "rules": [{**good["rules"][0], "stage": "E9"}]},
                   {**good, "rules": [{**good["rules"][0], "id": "R1"}]},
                   {**good, "rules": good["rules"] * 2},
                   {**good, "rules": [{**good["rules"][0], "evidence_type": "prohibited_phrase"}]},
                   {**good, "business_knowledge": [{"id": "x", "business_status": "MAYBE"}]}):
        with pytest.raises(ValueError):
            parse_playbook(broken)


def test_pending_confirmation_information_is_never_authorized():
    pb = load_playbook()
    status = {i["id"]: i["business_status"] for i in pb.business_knowledge}
    for pending in ("price_cohort", "second_chair_in_person", "guarantee_30_days"):
        assert status[pending] == "PENDING_CONFIRMATION"
    authorized = {i["id"] for i in pb.authorized_knowledge()}
    assert authorized and all(status[i] == "CONFIRMED" for i in authorized)
    assert not authorized & {"price_cohort", "second_chair_in_person", "guarantee_30_days"}


def test_satisfied_or_violated_always_needs_evidence():
    for status in ("SATISFIED", "VIOLATED"):
        with pytest.raises(ValueError):
            ComplianceResult("E3-R1", status, (), "sem evidência")
    assert ComplianceResult("E3-R1", "PENDING", (), "nenhuma dor").status == "PENDING"


# --- rules over the Commercial State ----------------------------------------------------------------

def test_pain_satisfies_e3_r1_with_the_same_evidence():
    assert _r(_eval(), "E3-R1").status == "PENDING"  # no pain: never invented
    r = _r(_eval(_facts(_ev("PAIN_IDENTIFIED", "processo manual", ["seg_2"]))), "E3-R1")
    assert (r.status, r.segment_ids) == ("SATISFIED", ("seg_2",))


def test_qualitative_impact_satisfies_e4_r1_but_not_e4_r2():
    state = _eval(_facts(_ev("IMPACT_IDENTIFIED", "a equipe perder muito tempo", ["seg_3"])))
    assert _r(state, "E4-R1").status == "SATISFIED" and _r(state, "E4-R1").segment_ids == ("seg_3",)
    assert _r(state, "E4-R2").status == "PENDING"


def test_quantified_impact_satisfies_e4_r1_and_e4_r2():
    state = _eval(_facts(_ev("IMPACT_IDENTIFIED", "perde 8 horas por semana", ["seg_3"])))
    r = _r(state, "E4-R2")
    assert _r(state, "E4-R1").status == "SATISFIED"
    assert (r.status, r.segment_ids, r.details["quantity"]) == ("SATISFIED", ("seg_3",), "8 horas")


@pytest.mark.parametrize(("text", "q"), [("perde uns R$ 10 mil por ano", "r$ 10 mil"), ("15% da margem", "15%"),
                                         ("perco uma hora por dia", "uma hora"), ("perde muito tempo", None),
                                         ("perde bastante dinheiro", None)])
def test_quantity_needs_a_number_and_a_unit(text, q):
    assert quantity(text) == q


def test_decision_participant_satisfies_e6_r1_and_leaves_e6_r2_pending():
    facts = _facts(_ev("STAKEHOLDER_IDENTIFIED", "sócio", ["seg_1", "seg_2"], "decision_participant"))
    state = _eval(facts, [("closer", "Quem participa da decisão?"), ("lead", "Meu sócio.")])
    assert (_r(state, "E6-R1").status, _r(state, "E6-R1").segment_ids) == ("SATISFIED", ("seg_1", "seg_2"))
    assert _r(state, "E6-R2").status == "PENDING"  # not inferred as absent, not satisfied without a plan


def test_a_mentioned_person_is_not_a_decider():
    state = _eval(_facts(_ev("STAKEHOLDER_IDENTIFIED", "sócio", ["seg_2"], "mentioned")))
    assert _r(state, "E6-R1").status == "PENDING" and _r(state, "E6-R2").status == "PENDING"


@pytest.mark.parametrize("closer_line", ["Vamos marcar com seu sócio terça às 14h.",
                                         "A segunda cadeira é exatamente para o seu sócio.",
                                         "Traga seu sócio, a vaga dele está incluída."])
def test_meeting_with_the_decider_or_second_chair_satisfies_e6_r2(closer_line):
    facts = _facts(_ev("STAKEHOLDER_IDENTIFIED", "sócio", ["seg_1", "seg_2"], "decision_participant"))
    state = _eval(facts, [("closer", "Quem participa da decisão?"), ("lead", "Meu sócio."), ("closer", closer_line)])
    r = _r(state, "E6-R2")
    assert r.status == "SATISFIED" and "seg_3" in r.segment_ids


def test_a_meeting_without_date_and_time_or_with_someone_else_does_not_satisfy_e6_r2():
    facts = _facts(_ev("STAKEHOLDER_IDENTIFIED", "sócio", ["seg_1"], "decision_participant"))
    for line in ("Vamos marcar com seu sócio semana que vem.", "Vamos marcar com o Miguel terça às 14h."):
        assert _r(_eval(facts, [("lead", "Meu sócio participa."), ("closer", line)]), "E6-R2").status == "PENDING"


def test_lead_deciding_alone_makes_e6_r2_not_applicable():
    state = _eval(_facts(_ev("DECISION_PROCESS_IDENTIFIED", "eu mesmo decido", ["seg_2"])))
    assert _r(state, "E6-R1").status == "SATISFIED" and _r(state, "E6-R2").status == "NOT_APPLICABLE"


@pytest.mark.parametrize(("line", "status"), [("Te ligo semana que vem.", "PENDING"),
                                              ("Eu te ligo terça às 14h.", "SATISFIED"),
                                              ("Combinado, amanhã às 10h a gente conversa.", "SATISFIED"),
                                              ("Na segunda cadeira às 10 vagas…", "PENDING")])
def test_next_step_needs_date_and_time(line, status):
    r = _r(_eval(lines=[("closer", line)]), "E12-R1")
    assert r.status == status
    if status == "SATISFIED":
        assert r.segment_ids == ("seg_1",)


def test_next_step_owner_only_when_explicit():
    r = _r(_eval(lines=[("closer", "Eu te ligo terça às 14h.")]), "E12-R1")
    assert r.details == {"date": "terca", "time": "14h", "owner": "closer"}
    assert "owner" not in _r(_eval(lines=[("closer", "Terça às 14h, combinado?")]), "E12-R1").details


def test_a_lead_next_step_confirming_the_closers_date_satisfies_e12_r1():
    facts = _facts(_ev("NEXT_STEP_IDENTIFIED", "Fechado", ["seg_1", "seg_2"]))
    r = _r(_eval(facts, [("closer", "Pode ser quinta às 10?"), ("lead", "Fechado.")]), "E12-R1")
    assert r.status == "SATISFIED" and r.segment_ids == ("seg_1", "seg_2")
    vague = _facts(_ev("NEXT_STEP_IDENTIFIED", "a gente se fala", ["seg_1"]))
    assert _r(_eval(vague, [("lead", "Depois a gente se fala.")]), "E12-R1").status == "PENDING"


@pytest.mark.parametrize(("line", "violated"), [("Isso se paga sozinho.", True), ("É risco zero pra você.", True),
                                                ("Eu garanto que sua margem sobe.", True),
                                                ("Eu não garanto resultado.", False), ("Não existe risco zero.", False),
                                                ("Temos a Garantia de Implementação.", False)])
def test_prohibited_phrases_from_the_closer(line, violated):
    state = _eval(lines=[("lead", "Oi."), ("closer", line)])
    r = _r(state, "E4-R5")
    assert (r.status == "VIOLATED") is violated
    if violated:
        assert r.segment_ids == ("seg_2",) and [v.rule_id for v in state.violations] == ["E4-R5"]


def test_the_lead_saying_a_prohibited_phrase_is_not_a_violation():
    assert _r(_eval(lines=[("lead", "Ninguém faz risco zero, né?")]), "E4-R5").status == "PENDING"
    assert phrase_hits("Isso se paga sozinho", ("se paga sozinho",)) == ("se paga sozinho",)


def test_objection_answered_and_cause_probe():
    price = _facts(objection_event("PRICE_BUDGET", ["seg_1"]))
    state = _eval(price, [("lead", "Achei caro.")])
    assert _r(state, "E10-R1").status == "PENDING" and _r(state, "E10-R2").status == "PENDING"
    state = _eval(price, [("lead", "Achei caro."), ("closer", "Caro em relação a quê?")])
    assert (_r(state, "E10-R1").status, _r(state, "E10-R1").segment_ids) == ("SATISFIED", ("seg_1", "seg_2"))
    assert (_r(state, "E10-R2").status, _r(state, "E10-R2").segment_ids) == ("SATISFIED", ("seg_1", "seg_2"))
    # an argument first, a probe only later: not judged as investigated (and never as a violation)
    state = _eval(price, [("lead", "Achei caro."), ("closer", "Mas o programa entrega muito."),
                          ("closer", "Caro em relação a quê?")])
    assert _r(state, "E10-R2").status == "UNKNOWN"
    assert _r(_eval(), "E10-R1").status == "NOT_APPLICABLE" and _r(_eval(), "E10-R2").status == "NOT_APPLICABLE"
    other = _facts(objection_event("COMPETITION_EXISTING_SOLUTION", ["seg_1"]))
    assert _r(_eval(other, [("lead", "Já uso outra coisa.")]), "E10-R2").status == "NOT_APPLICABLE"


def test_unimplemented_rules_are_listed_not_guessed():
    state = _eval()
    evaluated = {r.rule_id for r in state.rule_results}
    assert evaluated == {"E1-R5", "E3-R1", "E4-R1", "E4-R2", "E4-R5", "E5-R1", "E6-R1", "E6-R2", "E7-R1", "E9-R1",
                         "E9-R3", "E9-R4", "E10-R1", "E10-R2", "E11-R1", "E11-R2", "E11-R4", "E12-R1", "E12-R3"}
    assert not evaluated & set(state.not_evaluated) and len(evaluated) + len(state.not_evaluated) == 61
    assert state.pending_required == ["E3-R1", "E4-R1", "E4-R2", "E5-R1", "E6-R1", "E6-R2", "E7-R1", "E9-R1",
                                      "E9-R3", "E9-R4", "E12-R1"]


# --- live session -----------------------------------------------------------------------------------

DEMO = [  # the acceptance example (invented)
    ("closer", "Me conta como vocês fazem hoje."), ("lead", "Fazemos tudo num processo manual."),
    ("lead", "Isso faz a equipe perder muito tempo."), ("closer", "Quem participa da decisão?"),
    ("lead", "Meu sócio."),
]


def test_acceptance_example_compliance_grows_with_the_call(kb):
    s, provider, clock = _live(kb)
    seen = []
    for i in range(1, len(DEMO) + 1):
        _run(s, clock, DEMO[i - 1:i])
        seen.append(s.compliance().completed_required)
    assert seen == [[], ["E3-R1"], ["E3-R1", "E4-R1"], ["E3-R1", "E4-R1"], ["E3-R1", "E4-R1", "E6-R1"]]
    c = s.compliance()
    assert {r.rule_id: r.status for r in c.rule_results if r.rule_id in
            ("E3-R1", "E4-R1", "E4-R2", "E6-R1", "E6-R2", "E12-R1")} == {
        "E3-R1": "SATISFIED", "E4-R1": "SATISFIED", "E4-R2": "PENDING", "E6-R1": "SATISFIED",
        "E6-R2": "PENDING", "E12-R1": "PENDING"}
    assert _r(c, "E6-R1").segment_ids == ("seg_4", "seg_5")  # the closer's question + the lead's answer
    assert s.current() is None and s.commercial.view()["objections"] == []  # discovery: no objection
    assert s.counters["recommendations_created"] == 0 and provider.guidance_calls() == 0


def test_authority_blocker_still_works_and_compliance_agrees(kb):
    s, _, clock = _live(kb)
    _run(s, clock, [("closer", "O que achou?"), ("lead", "Preciso falar com meu sócio antes de fechar.")])
    assert s.current().category == "AUTHORITY_INTERNAL_BUY_IN"  # the objection engine is unchanged
    c = s.compliance()
    assert _r(c, "E6-R1").status == "SATISFIED" and _r(c, "E10-R1").status == "PENDING"
    _run(s, clock, [("closer", "Vamos marcar com seu sócio terça às 14h.")])
    c = s.compliance()
    assert [_r(c, x).status for x in ("E6-R2", "E10-R1", "E12-R1")] == ["SATISFIED"] * 3


def test_compliance_is_idempotent(kb):
    s, _, clock = _live(kb)
    _run(s, clock, DEMO)
    first = s.compliance().view()
    assert s.compliance().view() == first
    s.add(s.utterances[-1])  # the same utterance delivered again
    assert s.compliance().view() == first and len(first["rule_results"]) == 19


def test_recovery_rebuilds_the_compliance_state_without_recommendations(kb):
    old = Runtime(Facts(_extractor), LiveConfig(), {"Matheus"}, log=lambda _: None)
    old.knowledge = kb
    for seq, (role, text) in enumerate(DEMO, 1):
        old.receive(parse_utterance(_payload(seq, role, text), old.closer_names, 1.0), background=False)
    before = old.recommendation("m")["playbook_compliance"]
    assert before["completed_required"] == ["E3-R1", "E4-R1", "E6-R1"]

    new = Runtime(Facts(_extractor), LiveConfig(), {"Matheus"}, log=lambda _: None)
    new.knowledge = kb
    new.rehydrate("m", [_payload(seq, r, t) for seq, (r, t) in enumerate(DEMO, 1)])
    deadline = time.time() + 5
    while "m" in new._busy and time.time() < deadline:  # the background Commercial State rebuild
        time.sleep(0.01)
    s = new.sessions["m"]
    assert new.recommendation("m")["playbook_compliance"] == before
    assert (s.counters["analyses_started"], s.counters["recommendations_created"], s.current()) == (0, 0, None)


def test_post_call_brief_lists_the_compliance(kb):
    s, _, clock = _live(kb)
    _run(s, clock, DEMO)
    md = render_markdown(s.finalize()).splitlines()
    for line in ("## Playbook Compliance", "### Satisfied", "- E3-R1 — Dor identificada [seg_2]",
                 "- E6-R1 — Quem decide identificado [seg_4, seg_5]", "### Pending",
                 "- E4-R2 — Impacto quantificado: impacto ainda não quantificado (sem número do lead)",
                 "- E12-R1 — Próximo passo com data e hora: próximo passo com data e hora não registrado",
                 "### Violations"):
        assert line in md, line
    assert md[md.index("### Violations") + 1] == "- -"
    assert s.finalize().to_json()["playbook_compliance"]["completed_required"] == ["E3-R1", "E4-R1", "E6-R1"]


def test_compliance_overhead_is_milliseconds_and_off_the_recommendation_path(kb):
    s, provider, clock = _live(kb)
    _run(s, clock, DEMO)
    analysis_prompts = len(provider.prompts)
    lines = [("closer" if i % 2 else "lead", f"Linha {i} da conversa sobre a fazenda e a equipe.") for i in range(300)]
    segs = [(f"seg_{i}", r, t) for i, (r, t) in enumerate(lines)]
    started = time.perf_counter()
    evaluate(load_playbook(), s.commercial.view(), segs)
    assert (time.perf_counter() - started) * 1000 < 200  # measured ~ a few ms; loose bound for slow CI
    s.compliance()
    assert len(provider.prompts) == analysis_prompts  # no LLM call
    assert s.compliance_ms >= 0


def test_schedule_ignores_ordinals_and_vague_dates():
    assert schedule("A segunda cadeira às 10 vagas") is None
    assert schedule("Te ligo semana que vem") is None
    assert schedule("Fechado, quinta às 10.") == {"date": "quinta", "time": "as 10"}
