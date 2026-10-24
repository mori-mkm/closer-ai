"""Post-call Brief v0: a grounded presentation of the CommercialState. No real Ollama, no LLM in the brief."""
from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest
from test_live_commercial_state import _SEG, Facts, _run, _session, _targets  # same folder

from closer_ai.ai.objection_guidance import load_objection_knowledge
from closer_ai.demo.analyze_call import GUIDANCE_KB
from closer_ai.live.commercial_state import CommercialEvent, CommercialState, objection_event
from closer_ai.live.post_call_brief import (
    REBUILT_NOTE,
    build_brief,
    derive_risks,
    render_markdown,
    summary_is_grounded,
)
from closer_ai.live.server import Runtime, make_handler, parse_utterance
from closer_ai.live.session import LiveConfig


@pytest.fixture(scope="module")
def kb():
    return load_objection_knowledge(GUIDANCE_KB)


def _state(*events: CommercialEvent) -> dict:
    s = CommercialState()
    for e in events:
        s.apply(e)
    return s.view()


def _ev(etype, value, ids, role=None):
    return CommercialEvent(etype, value, tuple(ids), "lead", "OBSERVED", role)


RICH = _state(_ev("PAIN_IDENTIFIED", "processo manual", ["seg_2"]),
              _ev("IMPACT_IDENTIFIED", "perde muito tempo", ["seg_3"]),
              _ev("STAKEHOLDER_IDENTIFIED", "sócio", ["seg_1", "seg_2"], "decision_participant"),
              _ev("BUYING_SIGNAL_DETECTED", "quer começar este mês", ["seg_6"]),
              objection_event("PRICE_BUDGET", ["seg_5"]))


def _brief(facts, **kw):
    return build_brief("m1", facts, kw.pop("timings", []), kw.pop("counters", {}), 1_000.0, **kw)


def _codes(brief):
    return [r.code for r in brief.risks]


def test_rich_call_brief_reflects_the_state_facts_with_evidence():
    b = _brief(RICH)
    assert b.facts == RICH  # the state, unchanged: every fact keeps its segment_ids
    assert b.summary == ("O lead relatou como dor: “processo manual”. Impacto relatado: “perde muito tempo”. "
                         "Outras pessoas citadas: sócio (participa da decisão). Sinal de compra: "
                         "“quer começar este mês”. Objeções detectadas: preço / orçamento.")
    assert _codes(b) == ["OBJECTION_RAISED", "DECISION_PROCESS_NOT_RECORDED", "NO_NEXT_STEP_RECORDED"]
    assert b.risks[0].segment_ids == ("seg_5",) and b.risks[1].segment_ids == ("seg_1", "seg_2")
    j = b.to_json()
    assert j["stakeholders"] == [{"value": "sócio", "segment_ids": ["seg_1", "seg_2"], "status": "OBSERVED",
                                  "role": "decision_participant"}]
    json.dumps(j)  # serializable as is


def test_neutral_call_brief_stays_conservative():
    b = _brief(CommercialState().view())
    assert b.summary == "Nenhum fato comercial registrado nesta call."
    assert all(v == [] for v in b.facts.values())
    assert _codes(b) == ["NO_NEXT_STEP_RECORDED"]  # only the absence; no specific risk invented


def test_next_step_present_has_no_missing_next_step_risk():
    facts = _state(_ev("NEXT_STEP_IDENTIFIED", "quinta às 10", ["seg_1", "seg_2"]))
    assert "NO_NEXT_STEP_RECORDED" not in _codes(_brief(facts))


def test_known_stakeholder_is_not_called_decision_maker_nor_a_risk_by_itself():
    b = _brief(_state(_ev("STAKEHOLDER_IDENTIFIED", "sócio", ["seg_2"], "mentioned")))
    assert "Outras pessoas citadas: sócio." in b.summary
    assert "palavra final" not in b.summary and "decisão" not in b.summary
    assert "DECISION_PROCESS_NOT_RECORDED" not in _codes(b)  # no one said they take part in the decision
    # a decision participant with a recorded decision process is not a risk either
    facts = _state(_ev("STAKEHOLDER_IDENTIFIED", "sócio", ["seg_2"], "decision_participant"),
                   _ev("DECISION_PROCESS_IDENTIFIED", "validar com meu sócio", ["seg_2"]))
    assert "DECISION_PROCESS_NOT_RECORDED" not in _codes(_brief(facts))
    assert "dá a palavra final" not in _brief(facts).summary


def test_summary_grounding_fails_closed(monkeypatch):
    assert summary_is_grounded(_brief(RICH).summary, RICH)
    assert not summary_is_grounded("O “CFO” precisa aprovar “R$ 10.000”.", RICH)
    import closer_ai.live.post_call_brief as pcb
    monkeypatch.setattr(pcb, "build_summary", lambda facts, *_: "O lead disse “o CFO aprova R$ 10.000”.")
    b = pcb.build_brief("m1", RICH, [], {}, 1.0)
    assert b.summary == "Resumo indisponível (validação de grounding falhou)." and "CFO" not in render_markdown(b)


def test_markdown_has_every_section_and_the_evidence():
    md = render_markdown(_brief(RICH))
    for line in ("# Post-call Brief", "## Summary", "## Pain", "- processo manual [seg_2]", "## Impact",
                 "- sócio (participa da decisão) [seg_1, seg_2]", "## Buying Signals", "## Objections",
                 "- PRICE_BUDGET (preço / orçamento) [seg_5]", "## Commercial Terms", "## Next Steps", "## Risks",
                 "- NO_NEXT_STEP_RECORDED: nenhum próximo passo registrado", "## Recommendation Stats"):
        assert line in md.splitlines(), line
    assert md.split("## Commercial Terms\n")[1].startswith("- -")


def test_derive_risks_is_pure():
    assert derive_risks(RICH) == derive_risks(RICH)


# --- session / runtime ------------------------------------------------------------------------------

VALIDATION = [  # spec section 11 (synthetic)
    ("closer", "Além de você, alguém participa da decisão?"),
    ("lead", "Sim, meu sócio."),
    ("lead", "Fazemos tudo manualmente."),
    ("lead", "Isso faz a equipe perder muito tempo."),
    ("lead", "Gostei da proposta, mas achei muito caro."),
    ("lead", "Se der certo, quero começar ainda este mês."),
]
EXTRACTOR = {  # what a well-behaved extractor returns for each target line
    "Sim, meu sócio.": ("STAKEHOLDER_IDENTIFIED", "meu sócio", "decision_participant"),
    "Fazemos tudo manualmente.": ("PAIN_IDENTIFIED", "tudo manualmente", "none"),
    "Isso faz a equipe perder muito tempo.": ("IMPACT_IDENTIFIED", "equipe perder muito tempo", "none"),
    "Se der certo, quero começar ainda este mês.": ("BUYING_SIGNAL_DETECTED", "quero começar ainda este mês", "none"),
}


def extractor(prompt):
    targets = _targets(prompt)
    events = []
    for sid, _, text in _SEG.findall(prompt):
        if sid in targets and text in EXTRACTOR:
            etype, value, role = EXTRACTOR[text]
            events.append({"event_type": etype, "value": value, "segment_ids": [sid], "stakeholder_role": role})
    return {"events": events}


def test_validation_sequence_brief(kb):
    s, _, clock = _session(kb, Facts(extractor))
    _run(s, clock, VALIDATION)
    b = s.finalize()
    assert {k: [f["value"] for f in v] for k, v in b.facts.items() if v} == {
        "pain_points": ["tudo manualmente"], "impacts": ["equipe perder muito tempo"], "stakeholders": ["sócio"],
        # "Sim, meu sócio." is a stakeholder, not an AUTHORITY objection (the classifier's label is gated)
        "buying_signals": ["quero começar ainda este mês"], "objections": ["PRICE_BUDGET"]}
    assert _codes(b) == ["OBJECTION_RAISED", "DECISION_PROCESS_NOT_RECORDED", "NO_NEXT_STEP_RECORDED"]
    assert b.recommendation_stats["recommendations_by_category"] == {"PRICE_BUDGET": 1}
    assert b.recommendation_stats["recommendations_created"] == s.counters["recommendations_created"]


def test_stakeholder_answer_brief_has_the_stakeholder_and_no_objection(kb):
    s, _, clock = _session(kb, Facts(extractor))
    _run(s, clock, VALIDATION[:2])
    b = s.finalize()
    assert b.facts["stakeholders"] == [{"value": "sócio", "segment_ids": ["seg_2"], "status": "OBSERVED",
                                        "role": "decision_participant"}]
    assert b.facts["objections"] == [] and "OBJECTION_RAISED" not in _codes(b)
    assert b.recommendation_stats["recommendations_created"] == 0
    assert "- sócio (participa da decisão) [seg_2]" in render_markdown(b).splitlines()


def test_finalize_is_idempotent_and_reads_the_last_lines_first(kb):
    s, provider, clock = _session(kb, Facts(extractor))
    _run(s, clock, VALIDATION[:-1])
    clock.now += 1
    from test_live_session import _say
    _say(s, clock, len(s.utterances) + 1, "lead", VALIDATION[-1][1])  # not extracted yet (no pause)
    b1 = s.finalize()
    assert [f["value"] for f in b1.facts["buying_signals"]] == ["quero começar ainda este mês"]  # flushed
    calls, counters, facts = len(provider.prompts), dict(s.counters), s.commercial.view()
    clock.now += 60
    b2 = s.finalize()
    assert b2 is b1 and b2.finalized_at == b1.finalized_at  # the same brief, not a new one
    assert (len(provider.prompts), dict(s.counters), s.commercial.view()) == (calls, counters, facts)  # no effects


def _payload(seq, role, text):
    return {"meeting_id": "m", "speaker": "Matheus" if role == "closer" else "Lead Teste", "text": text,
            "timestamp": 1_700_000_000 + seq * 8, "sequence": seq}


def test_finalize_after_restart_uses_the_rebuilt_state_without_reanalysis(kb):
    provider = Facts(extractor)
    rt = Runtime(provider, LiveConfig(), {"Matheus"}, log=lambda _: None)
    rt.knowledge = kb
    rt.rehydrate("m", [_payload(seq, r, t) for seq, (r, t) in enumerate(VALIDATION, 1)])
    out = rt.finalize("m")
    brief = out["brief"]
    assert brief["stakeholders"][0]["value"] == "sócio" and brief["buying_signals"]
    assert brief["objections"] == []  # known limitation: objections before a restart are not rebuilt
    assert brief["notes"] == [REBUILT_NOTE]
    assert brief["recommendation_stats"]["recommendations_created"] == 0 and rt.sessions["m"].current() is None
    assert all(p.startswith("COMMERCIAL FACTS TASK") for p in provider.prompts)  # nothing re-classified
    assert rt.finalize("m") == out  # twice: identical


def test_finalize_endpoint_over_http(kb):
    rt = Runtime(Facts(extractor), LiveConfig(), {"Matheus"}, log=lambda _: None)
    rt.knowledge = kb
    for seq, (r, t) in enumerate(VALIDATION[:3], 1):
        rt.receive(parse_utterance(_payload(seq, r, t), rt.closer_names, 1.0), background=False)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(rt))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"

    def post(meeting_id):
        req = urllib.request.Request(base + "/finalize", data=json.dumps({"meeting_id": meeting_id}).encode(),
                                     headers={"X-AI-Closer": "1", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read())

    try:
        first = post("m")
        assert first["markdown"].startswith("# Post-call Brief") and first["brief"]["pain_points"]
        assert post("m") == first
        with pytest.raises(urllib.error.HTTPError) as e:
            post("nope")
        assert e.value.code == 404
        req = urllib.request.Request(base + "/recommendation?meeting_id=m", headers={"X-AI-Closer": "1"})
        with urllib.request.urlopen(req, timeout=5) as r:
            assert json.loads(r.read())["post_call_brief"]["markdown"] == first["markdown"]
    finally:
        srv.shutdown()


def test_finalize_waits_for_the_analysis_in_progress(kb):
    gate = threading.Event()

    class Slow(Facts):
        def classify(self, prompt, **kw):
            if not prompt.startswith("COMMERCIAL FACTS TASK"):
                gate.wait(5)
            return super().classify(prompt, **kw)

    rt = Runtime(Slow(extractor), LiveConfig(), {"Matheus"}, log=lambda _: None)
    rt.knowledge = kb
    rt.receive(parse_utterance(_payload(1, "lead", "Gostei da proposta, mas achei muito caro."), rt.closer_names,
                               time.time()))
    threading.Timer(0.3, gate.set).start()
    brief = rt.finalize("m")["brief"]
    assert [f["value"] for f in brief["objections"]] == ["PRICE_BUDGET"]  # the running analysis made it in
    with pytest.raises(TimeoutError):
        stuck = Runtime(Slow(extractor), LiveConfig(), {"Matheus"}, log=lambda _: None)
        stuck.knowledge = kb
        gate.clear()
        stuck.receive(parse_utterance(_payload(1, "lead", "Gostei da proposta, mas achei muito caro."),
                                      stuck.closer_names, time.time()))
        stuck.finalize("m", wait_seconds=0.2)
    gate.set()
