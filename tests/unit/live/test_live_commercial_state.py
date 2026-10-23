"""Commercial Events + Commercial State v0: grounded, incremental, deduplicated facts. No real Ollama."""
from __future__ import annotations

import re
import time

import pytest
from test_live_session import FakeProvider, _say  # same folder (pytest rootdir import)

from closer_ai.ai.objection_guidance import load_objection_knowledge
from closer_ai.demo.analyze_call import CLASSIFICATION_KB, GUIDANCE_KB
from closer_ai.live.commercial_state import CommercialState, fact_key, parse_facts
from closer_ai.live.server import Runtime, parse_utterance
from closer_ai.live.session import LiveConfig, LiveSalesSession

_TARGET = re.compile(r"^\[(seg_\d+)\] ", re.MULTILINE)  # the TARGET block's "[seg_n] text" lines
_SEG = re.compile(r"\[(seg_\d+) \| (\w+)\]\n(.*)")

# lead text -> what a well-behaved extractor returns: (event_type, value, stakeholder_role, cite_previous)
FACTS = {
    "Sim, meu sócio.": [("STAKEHOLDER_IDENTIFIED", "meu sócio", "decision_participant", True)],
    "É tudo manual.": [("PAIN_IDENTIFIED", "tudo manual", "none", True)],
    "Hoje fazemos tudo manualmente.": [("PAIN_IDENTIFIED", "fazemos tudo manualmente", "none", False)],
    "A equipe perde três horas por dia nisso.": [("IMPACT_IDENTIFIED", "perde três horas por dia", "none", False)],
    "Isso faz a equipe perder muito tempo.": [("IMPACT_IDENTIFIED", "a equipe perder muito tempo", "none", False)],
    "Se funcionar, quero começar ainda este mês.": [
        ("BUYING_SIGNAL_DETECTED", "quero começar ainda este mês", "none", False)],
    "Se a gente resolver isso, quero começar este mês.": [
        ("BUYING_SIGNAL_DETECTED", "quero começar este mês", "none", False)],
    "Meu sócio também.": [("STAKEHOLDER_IDENTIFIED", "Meu sócio", "decision_participant", True)],
    "Preciso validar com meu sócio.": [("STAKEHOLDER_IDENTIFIED", "meu sócio", "decision_participant", False),
                                       ("DECISION_PROCESS_IDENTIFIED", "validar com meu sócio", "none", False)],
    "Gostei, mas achei muito caro.": [],  # an objection: the objection engine owns it
    "Gostei, mas achei caro demais.": [],
    "Hoje temos cinco pessoas no time.": [],  # neutral
}


def _targets(prompt):
    return _TARGET.findall(prompt)


class Facts(FakeProvider):
    """FakeProvider (classifier + guidance) + a scripted commercial-facts extractor (`answer(prompt)`)."""

    def __init__(self, answer=None):
        super().__init__()
        self.answer = answer or self.scripted

    @staticmethod
    def scripted(prompt):
        targets = _targets(prompt)
        segs = _SEG.findall(prompt)
        events = []
        for i, (sid, _, text) in enumerate(segs):
            if sid in targets:
                for etype, value, role, prev in FACTS.get(text, []):
                    ids = [segs[i - 1][0], sid] if prev and i else [sid]
                    events.append({"event_type": etype, "value": value, "segment_ids": ids, "stakeholder_role": role})
        return {"events": events}

    def classify(self, prompt, **kw):
        if prompt.startswith("COMMERCIAL FACTS TASK"):
            self.prompts.append(prompt)
            return self.answer(prompt)
        return super().classify(prompt, **kw)

    def facts_calls(self) -> int:
        return sum(p.startswith("COMMERCIAL FACTS TASK") for p in self.prompts)


class Clock:
    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture(scope="module")
def kb():
    return load_objection_knowledge(GUIDANCE_KB)


def _session(kb, provider=None):
    provider, clock = provider or Facts(), Clock()
    return LiveSalesSession("m1", provider, kb, CLASSIFICATION_KB, LiveConfig(), clock=clock), provider, clock


def _run(s, clock, lines, analyze=True):
    """Feed (role, text) lines like the runtime worker: objection analysis first, then commercial facts."""
    for role, text in lines:
        clock.now += 8
        _say(s, clock, len(s.utterances) + 1, role, text)
        if analyze and s.should_analyze():
            s.analyze()
        while s.should_extract():
            s.extract()
    return s.commercial.view()


def _values(view, field):
    return [f["value"] for f in view[field]]


def test_stakeholder_from_a_short_answer_is_a_fact_without_any_recommendation(kb):
    s, provider, clock = _session(kb)
    view = _run(s, clock, [("closer", "Além de você, alguém participa da decisão?"), ("lead", "Sim, meu sócio.")],
                analyze=False)
    assert view["stakeholders"] == [{"value": "sócio", "segment_ids": ["seg_1", "seg_2"], "status": "OBSERVED",
                                     "role": "decision_participant"}]
    assert "seg_2" in view["stakeholders"][0]["segment_ids"]  # the lead's own line is evidence
    assert s.current() is None and s.counters["recommendations_created"] == 0  # a fact, not a suggestion
    assert s.counters["analyses_started"] == 0 and provider.guidance_calls() == 0


def test_pain_is_recorded_and_not_turned_into_an_objection(kb):
    s, _, clock = _session(kb)
    view = _run(s, clock, [("lead", "Hoje fazemos tudo manualmente.")])
    assert _values(view, "pain_points") == ["fazemos tudo manualmente"]
    assert view["objections"] == [] and s.current() is None


def test_impact_and_buying_signal(kb):
    s, _, clock = _session(kb)
    view = _run(s, clock, [("lead", "A equipe perde três horas por dia nisso."), ("closer", "E se resolver?"),
                           ("lead", "Se funcionar, quero começar ainda este mês.")])
    assert _values(view, "impacts") == ["perde três horas por dia"]
    assert _values(view, "buying_signals") == ["quero começar ainda este mês"]


def test_objection_comes_from_the_objection_engine_not_from_a_new_classification(kb):
    s, provider, clock = _session(kb)
    view = _run(s, clock, [("lead", "Gostei, mas achei muito caro.")])
    assert view["objections"] == [{"value": "PRICE_BUDGET", "segment_ids": ["seg_1"], "status": "CONFIRMED"}]
    # one classifier call (the objection engine) + one facts call that never asks for objections
    assert sum(p.startswith("COMMERCIAL FACTS TASK") for p in provider.prompts) == 1
    facts_prompt = next(p for p in provider.prompts if p.startswith("COMMERCIAL FACTS TASK"))
    assert "OBJECTION_IDENTIFIED" not in facts_prompt and "never record them" in facts_prompt


def test_normalized_objection_category_is_what_the_state_gets(kb):
    s, _, clock = _session(kb)  # E1 says NEED_VALUE_FIT; the live policy normalizes it to PRICE_BUDGET
    view = _run(s, clock, [("lead", "Gostei, mas achei caro demais.")])
    assert _values(view, "objections") == ["PRICE_BUDGET"]


def test_neutral_line_gives_no_commercial_fact(kb):
    s, _, clock = _session(kb)
    view = _run(s, clock, [("lead", "Hoje temos cinco pessoas no time.")])
    assert len(s.commercial) == 0 and all(v == [] for v in view.values())


def test_the_same_fact_repeated_is_one_item_with_all_its_evidence(kb):
    s, _, clock = _session(kb)
    view = _run(s, clock, [("closer", "Quem participa da decisão?"), ("lead", "Sim, meu sócio."),
                           ("closer", "Certo."), ("lead", "Meu sócio também."),
                           ("lead", "Preciso validar com meu sócio.")])
    assert view["stakeholders"] == [{"value": "sócio", "segment_ids": ["seg_1", "seg_2", "seg_3", "seg_4", "seg_5"],
                                     "status": "OBSERVED", "role": "decision_participant"}]
    assert _values(view, "decision_process") == ["validar com meu sócio"]
    assert fact_key("sócio") == fact_key("meu sócio") == fact_key("Meu sócio também") == "socio"


def test_new_information_updates_a_fact_without_losing_old_evidence(kb):
    def extractor(prompt):
        if _targets(prompt) == ["seg_4"]:  # "Ele é quem dá a palavra final."
            return {"events": [{"event_type": "STAKEHOLDER_IDENTIFIED", "value": "sócio",
                                "segment_ids": ["seg_2", "seg_4"], "stakeholder_role": "final_decision_maker"}]}
        return Facts.scripted(prompt)

    s, _, clock = _session(kb, Facts(extractor))
    view = _run(s, clock, [("closer", "Alguém participa da decisão?"), ("lead", "Sim, meu sócio."),
                           ("closer", "Entendi, e qual o papel dele?"), ("lead", "Ele é quem dá a palavra final.")],
                analyze=False)
    assert view["stakeholders"] == [{"value": "sócio", "segment_ids": ["seg_1", "seg_2", "seg_4"],
                                     "status": "OBSERVED", "role": "final_decision_maker"}]
    assert [e["result"] for e in s.commercial.events] == ["ADDED", "UPDATED"]


# --- grounding: a misbehaving extractor never puts an unsupported fact in the state -----------------

def _call(lines):
    s, clock = LiveSalesSession("m1", None, None, None), Clock()
    for role, text in lines:
        clock.now += 8
        _say(s, clock, len(s.utterances) + 1, role, text)
    return s._window_call(s.utterances)


def _parse(lines, events, targets=("seg_2",), state=None):
    return parse_facts(_call(lines), targets, {"events": events}, state or CommercialState())


QA = [("closer", "Além de você, alguém participa da decisão?"), ("lead", "Sim, meu sócio.")]


def _ev(etype, value, ids, role="none"):
    return {"event_type": etype, "value": value, "segment_ids": ids, "stakeholder_role": role}


def test_invented_values_and_roles_are_rejected_or_downgraded():
    accepted, rejected = _parse(QA, [
        _ev("STAKEHOLDER_IDENTIFIED", "CFO", ["seg_2"]),  # not said
        _ev("STAKEHOLDER_IDENTIFIED", "sócio", ["seg_2"], "final_decision_maker"),  # nobody said he decides
    ])
    assert [r["reason"] for r in rejected] == ["UNGROUNDED"]
    assert [(e.value, e.stakeholder_role) for e in accepted] == [("sócio", "decision_participant")]
    accepted, _ = _parse([("closer", "Como foi a reunião?"), ("lead", "Sim, meu sócio.")],
                         [_ev("STAKEHOLDER_IDENTIFIED", "sócio", ["seg_2"], "decision_participant")])
    assert accepted[0].stakeholder_role == "mentioned"  # no decision cue in the call: role not invented


def test_evidence_must_exist_and_include_the_new_lead_line():
    accepted, rejected = _parse(QA, [
        _ev("PAIN_IDENTIFIED", "participa da decisão", ["seg_1"]),  # only the closer's words, no target
        _ev("STAKEHOLDER_IDENTIFIED", "sócio", ["seg_9"]),  # unknown segment
        _ev("OBJECTION_IDENTIFIED", "PRICE_BUDGET", ["seg_2"]),  # the objection engine owns objections
        _ev("STAKEHOLDER_IDENTIFIED", "só", ["seg_2"]),  # partial word, not the lead's words
        _ev("STAKEHOLDER_IDENTIFIED", "sócio", []),  # uncited, but the target line says it: cited for it
    ])
    assert [r["reason"] for r in rejected] == ["NOT_IN_TARGET", "BAD_EVIDENCE", "UNKNOWN_TYPE", "UNGROUNDED"]
    assert [(e.value, e.segment_ids) for e in accepted] == [("sócio", ("seg_2",))]
    with pytest.raises(TypeError):
        parse_facts(_call(QA), ("seg_2",), {"facts": []}, CommercialState())


def test_a_commercial_term_must_name_something_concrete():
    lines = [("closer", "O que achou do valor?"), ("lead", "Achei caro, hoje pagamos dois mil por mês.")]
    accepted, rejected = _parse(lines, [_ev("COMMERCIAL_TERM_MENTIONED", "Achei caro", ["seg_2"]),
                                        _ev("COMMERCIAL_TERM_MENTIONED", "pagamos dois mil por mês", ["seg_2"])])
    assert [r["reason"] for r in rejected] == ["NOT_A_TERM"]  # the objection is the objection engine's
    assert [e.value for e in accepted] == ["pagamos dois mil por mês"]


def test_a_decision_process_must_say_how_the_decision_is_made():
    lines = [("closer", "E quando vocês decidem?"), ("lead", "Agora não é o momento, preciso falar com meu sócio.")]
    accepted, rejected = _parse(lines, [_ev("DECISION_PROCESS_IDENTIFIED", "Agora não é o momento", ["seg_2"]),
                                        _ev("DECISION_PROCESS_IDENTIFIED", "falar com meu sócio", ["seg_2"])])
    assert [r["reason"] for r in rejected] == ["NOT_A_DECISION_STEP"]  # a timing objection, not a step
    assert [e.value for e in accepted] == ["falar com meu sócio"]


def test_an_old_fact_cannot_be_extracted_again_from_context():
    lines = [("lead", "É tudo manual."), ("closer", "Entendi."), ("lead", "Hoje temos cinco pessoas no time.")]
    accepted, rejected = _parse(lines, [_ev("PAIN_IDENTIFIED", "tudo manual", ["seg_1", "seg_3"])],
                                targets=("seg_3",))
    assert accepted == [] and [r["reason"] for r in rejected] == ["NOT_IN_TARGET"]


def test_an_earlier_line_of_the_same_lead_turn_is_not_re_cited():
    # real qwen3 run: reading "Fazemos tudo manualmente." it re-emitted the stakeholder of the line before
    lines = [("closer", "Além de você, alguém participa da decisão?"), ("lead", "Sim, meu sócio."),
             ("lead", "Fazemos tudo manualmente.")]
    state = CommercialState()
    accepted, _ = _parse(lines, [_ev("STAKEHOLDER_IDENTIFIED", "sócio", ["seg_2"], "decision_participant")],
                         state=state)
    state.apply(accepted[0])
    accepted, rejected = _parse(lines, [_ev("STAKEHOLDER_IDENTIFIED", "meu sócio", ["seg_2", "seg_3"],
                                            "decision_participant"),
                                        _ev("PAIN_IDENTIFIED", "tudo manualmente", ["seg_3"])],
                                targets=("seg_3",), state=state)
    assert [r["reason"] for r in rejected] == ["NOT_IN_TARGET"]
    assert [e.value for e in accepted] == ["tudo manualmente"]


def test_every_fact_in_the_state_has_segment_ids(kb):
    s, _, clock = _session(kb)
    view = _run(s, clock, MANUAL_SEQUENCE)
    facts = [f for items in view.values() for f in items]
    assert facts and all(f["segment_ids"] for f in facts)


# --- the manual evaluation sequence (spec section 12) -----------------------------------------------

MANUAL_SEQUENCE = [
    ("closer", "Como vocês fazem isso hoje?"),
    ("lead", "É tudo manual."),
    ("lead", "Isso faz a equipe perder muito tempo."),
    ("closer", "Quem participa da decisão?"),
    ("lead", "Meu sócio também."),
    ("lead", "Gostei, mas achei muito caro."),
    ("lead", "Se a gente resolver isso, quero começar este mês."),
]


def test_manual_sequence_final_state(kb):
    s, _, clock = _session(kb)
    view = _run(s, clock, MANUAL_SEQUENCE)
    assert view == {
        "pain_points": [{"value": "tudo manual", "segment_ids": ["seg_1", "seg_2"], "status": "OBSERVED"}],
        "impacts": [{"value": "equipe perder muito tempo", "segment_ids": ["seg_3"], "status": "OBSERVED"}],
        "stakeholders": [{"value": "sócio", "segment_ids": ["seg_4", "seg_5"], "status": "OBSERVED",
                          "role": "decision_participant"}],
        "decision_process": [],
        "buying_signals": [{"value": "quero começar este mês", "segment_ids": ["seg_7"], "status": "OBSERVED"}],
        "objections": [{"value": "PRICE_BUDGET", "segment_ids": ["seg_6"], "status": "CONFIRMED"}],
        "commercial_terms": [],
        "next_steps": [],
    }


# --- recovery: restart -> rehydrate -> state rebuilt by extraction only -----------------------------

def _payload(seq, role, text):
    return {"meeting_id": "m", "speaker": "Matheus" if role == "closer" else "Lead Teste", "text": text,
            "timestamp": 1_700_000_000 + seq * 8, "sequence": seq}


def test_restart_rebuilds_the_commercial_state_without_recommendations_or_duplicates(kb):
    old = Runtime(Facts(), LiveConfig(), {"Matheus"}, log=lambda _: None)
    old.knowledge = kb
    for seq, (role, text) in enumerate(MANUAL_SEQUENCE[:5], 1):  # objection-free part of the meeting
        old.receive(parse_utterance(_payload(seq, role, text), old.closer_names, 1.0), background=False)
    before = old.recommendation("m")["commercial_state"]

    provider = Facts()
    new = Runtime(provider, LiveConfig(), {"Matheus"}, log=lambda _: None)
    new.knowledge = kb
    assert new.rehydrate("m", [_payload(seq, r, t) for seq, (r, t) in enumerate(MANUAL_SEQUENCE[:5], 1)])[
        "rehydrated"] == 5
    deadline = time.time() + 5
    while "m" in new._busy and time.time() < deadline:  # the background rebuild
        time.sleep(0.01)
    s = new.sessions["m"]
    assert new.recommendation("m")["commercial_state"] == before  # same facts, same evidence
    assert s.fact_counters["rebuild_extractions"] >= 1 and s.fact_counters["extractions"] == 0  # not live work
    assert (s.counters["analyses_started"], s.counters["recommendations_created"], s.current()) == (0, 0, None)
    assert provider.facts_calls() == len(provider.prompts)  # no objection classification, no guidance

    calls = provider.facts_calls()
    assert new.rehydrate("m", [_payload(seq, r, t) for seq, (r, t) in enumerate(MANUAL_SEQUENCE[:5], 1)])[
        "rehydrated"] == 0  # resent: nothing added, nothing extracted again
    assert provider.facts_calls() == calls and new.recommendation("m")["commercial_state"] == before


def test_extraction_errors_are_recorded_and_never_break_the_session(kb):
    s, _, clock = _session(kb, Facts(lambda prompt: {"unexpected": True}))
    _say(s, clock, 1, "lead", "Hoje fazemos tudo manualmente.")
    t = s.extract()
    assert (t["outcome"], t["error_type"]) == ("ERROR", "OTHER")
    assert s.fact_counters["extraction_errors"] == 1 and not s.should_extract()  # not retried in a loop


def test_single_word_lead_lines_cost_no_llm_call(kb):
    s, provider, clock = _session(kb)
    _say(s, clock, 1, "lead", "Ok.")
    assert s.extract()["outcome"] == "SKIPPED_SHORT" and provider.facts_calls() == 0


def test_lines_are_read_once_live(kb):
    s, provider, clock = _session(kb)
    _run(s, clock, [("lead", "Hoje fazemos tudo manualmente."), ("lead", "A equipe perde três horas por dia nisso.")])
    assert not s.should_extract()
    assert [_targets(p) for p in provider.prompts if p.startswith("COMMERCIAL")] == [["seg_1"], ["seg_2"]]


def test_background_extraction_waits_for_a_pause_after_speech_and_after_an_analysis(kb):
    s, _, clock = _session(kb)
    _say(s, clock, 1, "lead", "Gostei, mas achei muito caro.")
    assert s.should_extract() and not s.facts_idle()  # the conversation is flowing
    clock.now += 2
    s.analyze()  # the recommendation is out: the closer answers now, the lead may reply
    clock.now += 3.9
    assert not s.facts_idle()
    clock.now += 0.2
    assert s.facts_idle()
    assert not LiveSalesSession("m1", None, None, None, LiveConfig(commercial_facts=False)).should_extract()
