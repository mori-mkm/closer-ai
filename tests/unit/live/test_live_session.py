"""Live Meet Copilot v0: session state, trigger, emission policy, lifecycle, local HTTP. No real Ollama."""
from __future__ import annotations

import json
import re
import threading
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from closer_ai.ai.objection_guidance import load_objection_knowledge
from closer_ai.demo.analyze_call import CLASSIFICATION_KB, GUIDANCE_KB
from closer_ai.live.server import Runtime, make_handler, parse_utterance, role_for
from closer_ai.live.session import LiveConfig, LiveSalesSession, LiveUtterance

_SEG = re.compile(r"\[(seg_\d+) \| (\w+)\]\n(.*)")
SCRIPT = {  # lead text -> category the fake classifier reports
    "Gostei da proposta, mas achei muito caro.": "PRICE_BUDGET",
    "Gostei, mas achei muito caro.": "PRICE_BUDGET",
    "Continua caro demais pra gente.": "PRICE_BUDGET",
    "Preciso falar com meu sócio antes de fechar.": "AUTHORITY_INTERNAL_BUY_IN",
    "A gente perde bastante tempo com isso.": "IMPLEMENTATION_INTEGRATION",  # qwen3 over-detection
    "Não temos equipe pra implantar isso agora.": "IMPLEMENTATION_INTEGRATION",
    "Gostei, mas achei caro demais.": "NEED_VALUE_FIT",  # real-Meet E1 mislabel, normalized by the live policy
    "Não sei se isso resolve meu problema.": "NEED_VALUE_FIT",
    "Pera aí, travou tudo aqui.": None,  # noise: long enough to trigger, no objection
    "Preciso falar com o meu sócio antes": "TIMING_PRIORITY",  # real-Meet E1 mislabel (caption cut at "antes")
    "Agora não é um bom momento. Vamos falar mês que vem.": "TIMING_PRIORITY",
    "Preciso validar com minha sócia.": "AUTHORITY_INTERNAL_BUY_IN",
    "Mas o principal problema para mim ainda é o preço.": "PRICE_BUDGET",
    "Agora não é o momento, talvez no próximo trimestre.": "TIMING_PRIORITY",
    "Sinceramente não sei se a gente precisa disso.": "NEED_VALUE_FIT",
    "Mas está acima do que eu consigo investir agora.": "PRICE_BUDGET",
    "Sim, meu sócio.": "AUTHORITY_INTERNAL_BUY_IN",
}
ANSWERS = {
    "PRICE_BUDGET": ("PRICE_BUDGET.M2", "O lead disse que achou caro.", "Caro em relação a quê?"),
    "IMPLEMENTATION_INTEGRATION": ("IMPLEMENTATION_INTEGRATION.M1", "O lead disse que não tem equipe para isso.",
                                   "O que precisaria estar pronto do lado de vocês para começar?"),
    "NEED_VALUE_FIT": ("NEED_VALUE_FIT.M1", "O lead não sabe se resolve o problema.", "Qual problema precisa resolver?"),
    "AUTHORITY_INTERNAL_BUY_IN": ("AUTHORITY_INTERNAL_BUY_IN.M1", "O lead quer falar com o sócio.",
                                  "Quem mais participa dessa decisão?"),
    "TIMING_PRIORITY": ("TIMING_PRIORITY.M1", "O lead disse que agora não é um bom momento.",
                        "O que precisa acontecer para ser um bom momento?"),
}


class FakeProvider:
    """Classifier: the newest lead line, looked up in SCRIPT (citing earlier lines as context, like
    qwen3 does live). Guidance: a canned answer for the category, or `bad_guidance` if set."""

    name, model = "fake", "fake-1"

    def __init__(self, bad_guidance: str | None = None):
        self.prompts: list[str] = []
        self.bad_guidance = bad_guidance

    def classify(self, prompt: str, **_):
        self.prompts.append(prompt)
        segs = _SEG.findall(prompt)
        if prompt.startswith("COMMERCIAL FACTS TASK"):  # commercial facts: see test_commercial_state.py
            return {"events": []}
        if prompt.startswith("GUIDANCE TASK"):
            category = re.search(r"Objection category \(classifier\): (\w+)", prompt).group(1)
            move, rationale, question = ANSWERS[category]
            return {"move_id": move, "rationale": rationale, "suggested_question": self.bad_guidance or question,
                    "evidence_segment_ids": [segs[0][0]]}
        lead = [s for s in segs if s[1] == "lead"]
        category = SCRIPT.get(lead[-1][2]) if lead else None
        if not category:
            return {"call_detection": "NO_OBJECTION", "episodes": [], "uncertain_spans": []}
        return {"call_detection": "OBJECTIONS_FOUND", "uncertain_spans": [], "episodes": [{
            "prediction_id": "p1", "objection_segment_ids": [lead[-1][0]],
            "context_segment_ids": [s[0] for s in segs if s[0] != lead[-1][0]],  # before the anchor
            "category_status": "PRESENT", "category": category, "category_candidates": [],
            "reaction_status": "ABSENT", "reaction": None, "reaction_candidates": [],
            "resolution_status": "unknown", "summary": "Objeção do lead."}]}

    def guidance_calls(self) -> int:
        return sum(p.startswith("GUIDANCE TASK") for p in self.prompts)


class Clock:
    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture(scope="module")
def kb():
    return load_objection_knowledge(GUIDANCE_KB)


def _session(kb, provider=None, **cfg) -> tuple[LiveSalesSession, FakeProvider, Clock]:
    provider, clock = provider or FakeProvider(), Clock()
    return LiveSalesSession("m1", provider, kb, CLASSIFICATION_KB, LiveConfig(**cfg), clock=clock), provider, clock


def _say(s: LiveSalesSession, clock: Clock, seq: int, role: str, text: str) -> bool:
    return s.add(LiveUtterance("m1", role.title(), role, text, clock.now, seq, clock.now))


def test_caption_becomes_live_utterance():
    u = parse_utterance({"meeting_id": "abc-defg-hij", "speaker": "Ana Lima", "text": " preciso falar com meu sócio ",
                         "timestamp": 1_700_000_000_000, "sequence": 42}, {"matheus", "você"}, 5.0)
    assert (u.speaker, u.role, u.text, u.timestamp, u.sequence, u.received_at) == (
        "Ana Lima", "lead", "preciso falar com meu sócio", 1_700_000_000.0, 42, 5.0)
    assert role_for("Você", {"você"}) == "closer"
    assert role_for("unknown", set()) == "unknown"
    assert parse_utterance({"meeting_id": "m", "text": "oi", "sequence": 1}, set(), 1.0).speaker == "unknown"
    with pytest.raises(TypeError):
        parse_utterance({"meeting_id": "m", "text": "oi", "sequence": "1"}, set(), 1.0)


def test_duplicate_caption_is_not_added(kb):
    s, _, clock = _session(kb)
    assert _say(s, clock, 1, "lead", "Achei caro.")
    assert not _say(s, clock, 1, "lead", "Achei caro.")  # same sequence
    assert not _say(s, clock, 2, "lead", "achei  caro.")  # Meet re-sent the same caption
    assert len(s.utterances) == 1


def test_ordering_follows_sequence(kb):
    s, _, clock = _session(kb)
    for seq in (1, 3, 2):
        _say(s, clock, seq, "closer", f"fala {seq}")
    assert [u.sequence for u in s.utterances] == [1, 2, 3]


def test_rolling_window_keeps_only_recent_context(kb):
    s, _, clock = _session(kb, window_seconds=60, max_window_utterances=3)
    for seq in range(1, 6):
        _say(s, clock, seq, "closer", f"fala {seq}")
        clock.now += 40
    assert [u.sequence for u in s.recent_window()] == [4, 5]  # 1-3 are older than 60 s
    s2, _, clock2 = _session(kb, window_seconds=60, max_window_utterances=3)
    for seq in range(1, 6):
        _say(s2, clock2, seq, "closer", f"fala {seq}")
    assert [u.sequence for u in s2.recent_window()] == [3, 4, 5]


def test_seller_utterance_does_not_trigger_analysis(kb):
    s, provider, clock = _session(kb)
    _say(s, clock, 1, "closer", "Gostei da proposta, mas achei muito caro.")
    assert not s.should_analyze()
    _say(s, clock, 2, "lead", "Ok.")  # too short to be substantive
    assert not s.should_analyze()
    assert provider.prompts == []


def test_lead_objection_gives_one_grounded_recommendation(kb):
    s, provider, clock = _session(kb)
    _say(s, clock, 1, "closer", "Como vocês fazem isso hoje?")
    _say(s, clock, 2, "lead", "Gostei da proposta, mas achei muito caro.")
    assert s.should_analyze()
    t = s.analyze()
    assert (t["outcome"], t["category"]) == ("RECOMMENDED", "PRICE_BUDGET")
    view = s.current().view()
    assert view["state"] == "ACTIVE" and view["category"] == "PRICE_BUDGET" and view["label"]
    assert view["question"] == "Caro em relação a quê?" and view["move"] and view["rationale"]
    # seller card: the lead's own objection words + the suggestion's objective
    assert view["lead_said"] == "Gostei da proposta, mas achei muito caro."
    assert view["objective"] and view["objective"][0].islower()
    [g_prompt] = [p for p in provider.prompts if p.startswith("GUIDANCE TASK")]
    assert "one short sentence in Portuguese" in g_prompt  # live asks for a brief rationale
    assert s.current_objection == "PRICE_BUDGET" and s.open_objections == ["PRICE_BUDGET"]
    assert not s.should_analyze()  # already analyzed
    assert {"queue_wait_ms", "classifier_latency_ms", "guidance_latency_ms", "end_to_end_latency_ms",
            "classifier", "guidance"} <= set(t)
    assert "text" not in json.dumps(t)  # timings only, no transcript content


def test_epoch_ms_sequences_still_give_short_segment_ids(kb):
    # Real Meet regression: the extension's sequences are epoch-ms; as segment ids ("seg_1792615952359")
    # qwen3:8b answered evidence_segment_ids as integers and every guidance was rejected.
    s, provider, clock = _session(kb)
    base = 1_792_615_952_358
    _say(s, clock, base, "closer", "Como vocês fazem isso hoje?")
    _say(s, clock, base + 1, "lead", "Gostei da proposta, mas achei muito caro.")
    assert s.analyze()["outcome"] == "RECOMMENDED"
    assert all(str(base) not in p for p in provider.prompts)
    assert "[seg_2 | lead]" in provider.prompts[-1]


def test_over_detected_category_needs_the_leads_own_words(kb):
    s, provider, clock = _session(kb)
    _say(s, clock, 1, "lead", "A gente perde bastante tempo com isso.")  # pain, not resistance
    t = s.analyze()
    assert (t["outcome"], t["reason"]) == ("NO_RECOMMENDATION", "UNCORROBORATED_CATEGORY")
    assert provider.guidance_calls() == 0
    _say(s, clock, 2, "lead", "Não temos equipe pra implantar isso agora.")
    assert s.analyze()["outcome"] == "RECOMMENDED"
    assert s.current().category == "IMPLEMENTATION_INTEGRATION"


def test_no_objection_gives_no_recommendation(kb):
    s, provider, clock = _session(kb)
    _say(s, clock, 1, "lead", "Hoje usamos uma planilha, mas ninguém atualiza.")
    t = s.analyze()
    assert (t["outcome"], t["reason"]) == ("NO_RECOMMENDATION", "NO_OBJECTION")
    assert s.current() is None and provider.guidance_calls() == 0


def test_cooldown_keeps_a_single_recommendation(kb):
    s, provider, clock = _session(kb, cooldown_seconds=25)
    _say(s, clock, 1, "lead", "Gostei da proposta, mas achei muito caro.")
    s.analyze()
    clock.now += 10
    _say(s, clock, 2, "lead", "Continua caro demais pra gente.")
    t = s.analyze()
    assert (t["outcome"], t["reason"]) == ("KEPT", "COOLDOWN")
    assert s.current().id == 1 and provider.guidance_calls() == 1


def test_new_objection_replaces_the_previous_one(kb):
    s, _, clock = _session(kb)
    _say(s, clock, 1, "lead", "Gostei da proposta, mas achei muito caro.")
    s.analyze()
    first = s.current_recommendation
    clock.now += 5
    _say(s, clock, 2, "lead", "Preciso falar com meu sócio antes de fechar.")
    s.analyze()
    assert s.current().category == "AUTHORITY_INTERNAL_BUY_IN" and first.state == "REPLACED"
    assert s.open_objections == ["PRICE_BUDGET", "AUTHORITY_INTERNAL_BUY_IN"]


def test_old_objection_in_the_window_is_not_shown_again(kb):
    s, _, clock = _session(kb)
    _say(s, clock, 1, "lead", "Gostei da proposta, mas achei muito caro.")
    s.analyze()
    s.dismiss()
    _say(s, clock, 2, "lead", "Hoje usamos uma planilha para controlar.")
    t = s.analyze()  # the window still holds the price line, but it is not new
    assert t["outcome"] == "NO_RECOMMENDATION" and s.current() is None


def test_grounding_failure_is_not_shown(kb):
    s, _, clock = _session(kb, provider=FakeProvider(bad_guidance="Podemos fechar até sexta-feira?"))
    _say(s, clock, 1, "lead", "Gostei da proposta, mas achei muito caro.")
    t = s.analyze()
    assert (t["outcome"], t["reason"]) == ("NO_RECOMMENDATION", "GUIDANCE_INVALID_RESPONSE")
    assert s.current() is None


def test_recommendation_expires_and_can_be_dismissed(kb):
    s, _, clock = _session(kb, ttl_seconds=60)
    _say(s, clock, 1, "lead", "Gostei da proposta, mas achei muito caro.")
    s.analyze()
    clock.now += 61
    assert s.current() is None and s.current_recommendation.state == "EXPIRED"
    clock.now += 1
    _say(s, clock, 2, "lead", "Preciso falar com meu sócio antes de fechar.")
    s.analyze()
    s.dismiss()
    assert s.current() is None and s.current_recommendation.state == "DISMISSED"


def test_local_http_runtime_end_to_end(kb):
    runtime = Runtime(FakeProvider(), LiveConfig(), {"matheus"}, log=lambda _: None)
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(runtime))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"

    def call(path, body=None, header=True):
        headers = {"X-AI-Closer": "1"} if header else {}
        data = None
        if body is not None:
            headers["Content-Type"], data = "application/json", json.dumps(body).encode()
        req = urllib.request.Request(base + path, data=data, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    try:
        assert call("/recommendation?meeting_id=m", header=False)[0] == 403
        for seq, (speaker, text) in enumerate([("Matheus", "Como vocês fazem hoje?"),
                                               ("Ana", "Gostei da proposta, mas achei muito caro.")], 1):
            status, body = call("/live-utterance", {"meeting_id": "m", "speaker": speaker, "text": text,
                                                    "timestamp": 1_700_000_000 + seq, "sequence": seq})
            assert (status, body) == (200, {"accepted": True, "status": "ACCEPTED", "id": seq,
                                            "role": "closer" if seq == 1 else "lead"})
        # a retry of the same utterance (same id) is confirmed as a duplicate and never added twice
        status, body = call("/live-utterance", {"meeting_id": "m", "speaker": "Ana", "sequence": 2,
                                                "text": "Gostei da proposta, mas achei muito caro."})
        assert (body["accepted"], body["status"], body["id"]) == (False, "DUPLICATE_SEQUENCE", 2)
        status, health = call("/health", header=False)  # no header needed, no call data
        assert status == 200 and set(health) == {"status", "runtime", "model", "model_state", "instance"}
        assert (health["status"], health["runtime"], health["model"]) == ("ok", "ready", "fake-1")
        for _ in range(100):  # analysis runs in the background worker
            status, rec = call("/recommendation?meeting_id=m")
            if rec["state"] == "ACTIVE":
                break
            threading.Event().wait(0.05)
        assert rec["category"] == "PRICE_BUDGET"
        assert rec["status"] == "RECOMMENDATION_READY"
        # the sidebar's data comes from the pipeline: retrieved unit/move and the session's own utterances
        assert (rec["knowledge_unit"], rec["move_id"], rec["move_code"], rec["grounding"]) == (
            "guidance.PRICE_BUDGET", "PRICE_BUDGET.M2", "CLARIFY", "VALID")
        assert rec["question"] == "Caro em relação a quê?"
        assert rec["transcript"] == [{"role": "closer", "text": "Como vocês fazem hoje?"},
                                     {"role": "lead", "text": "Gostei da proposta, mas achei muito caro."}]
        assert runtime.sessions["m"].timings[-1]["displayed_latency_ms"] >= 0
        assert call("/dismiss", {"meeting_id": "m"})[0] == 200
        after = call("/recommendation?meeting_id=m")[1]
        assert (after["state"], after["status"], len(after["transcript"])) == ("NONE", "CAPTURING", 2)
        assert call("/health", header=False)[1]["model_state"] == "ready"  # an analysis ran
        assert call("/recommendation?meeting_id=other")[1] == {"state": "NONE", "status": "CAPTURING", "transcript": [],
                                                               "instance": runtime.instance}
        assert call("/live-utterance", {"meeting_id": "m"})[0] == 400
    finally:
        server.shutdown()


def test_sidebar_status_and_debug_speaker(kb):
    rt = Runtime(FakeProvider(), LiveConfig(), {"Matheus"}, log=lambda s: None, debug=True)
    rt.knowledge = kb
    say = lambda seq, sp, tx: rt.receive(parse_utterance(
        {"meeting_id": "m", "speaker": sp, "text": tx, "sequence": seq}, rt.closer_names, 1.0), background=False)
    say(1, "Você", "Como vocês fazem isso hoje?")
    view = rt.recommendation("m")
    assert view["status"] == "CAPTURING"
    assert view["transcript"] == [{"role": "closer", "text": "Como vocês fazem isso hoje?", "speaker": "Você"}]
    say(2, "Matheus Mori", "Faz sentido, gostei bastante.")  # no objection
    assert rt.recommendation("m")["status"] == "NO_RECOMMENDATION"
    latency = rt.recommendation("m")["debug"]["latency"]  # last analysis, for the advanced panel
    assert {"queue_wait_ms", "classifier_latency_ms", "end_to_end_latency_ms"} <= set(latency)
    rt.sessions["m"].pending_lead_seq = 2  # a lead line waiting for the worker is already ANALYZING
    assert rt.recommendation("m")["status"] == "ANALYZING"
    rt.sessions["m"].pending_lead_seq = None
    rt.sessions["m"].last_outcome = "NO_RECOMMENDATION:ERROR:OllamaError"
    assert rt.recommendation("m")["status"] == "ERROR"


# --- real-Meet blockers (Oct 2026) ---------------------------------------------------------------

def test_closer_utterance_never_triggers_even_with_a_lead_pending(kb):
    s, _, clock = _session(kb)
    _say(s, clock, 1, "lead", "Gostei da proposta, mas achei muito caro.")
    assert s.last_trigger_reason is None and s.pending_lead_seq == 1
    _say(s, clock, 2, "closer", "E como isso impacta vocês?")
    assert s.last_trigger_reason == "NOT_LEAD"
    assert s.pending_lead_seq == 1  # still the lead line, not the closer's


def test_latest_wins_one_pending_lead_and_one_analysis(kb):
    s, provider, clock = _session(kb)
    _say(s, clock, 1, "lead", "Pera aí, travou tudo aqui.")
    _say(s, clock, 2, "lead", "Foi mal.")  # too short: not eligible, pending unchanged
    assert (s.last_trigger_reason, s.pending_lead_seq) == ("LEAD_UTTERANCE_TOO_SHORT", 1)
    _say(s, clock, 3, "closer", "Podemos continuar?")
    _say(s, clock, 4, "lead", "Gostei da proposta, mas achei muito caro.")
    assert s.pending_lead_seq == 4  # the newest eligible lead replaced the noise
    clock.now += 18
    t = s.analyze()
    assert (t["outcome"], t["category"], t["sequence"], t["superseded_leads"]) == ("RECOMMENDED", "PRICE_BUDGET", 4, 1)
    assert t["queue_wait_ms"] == 18_000
    assert not s.should_analyze()  # no backlog of older analyses
    assert [u.sequence for u in s.utterances] == [1, 2, 3, 4]  # transcript keeps everything
    assert sum(not p.startswith("GUIDANCE TASK") for p in provider.prompts) == 1


def test_busy_runtime_analyzes_only_the_latest_lead_next(kb):
    gate, started = threading.Event(), threading.Event()

    class Slow(FakeProvider):
        def classify(self, prompt, **_):
            if not started.is_set():
                started.set()
                gate.wait(5)  # the first (noise) analysis is still running
            return super().classify(prompt)

    # objection queue only: the commercial-facts worker would keep it busy until the call pauses
    rt = Runtime(Slow(), LiveConfig(commercial_facts=False), {"Matheus"}, log=lambda s: None)
    rt.knowledge = kb
    say = lambda seq, sp, tx: rt.receive(parse_utterance(
        {"meeting_id": "m", "speaker": sp, "text": tx, "sequence": seq}, rt.closer_names, 1.0))
    say(1, "Lead Teste", "Pera aí, travou tudo aqui.")
    assert started.wait(5)
    say(2, "Lead Teste", "Hoje usamos uma planilha para controlar.")  # pending, then superseded
    say(3, "Você", "E como isso impacta vocês?")
    say(4, "Lead Teste", "Gostei da proposta, mas achei muito caro.")
    gate.set()
    for _ in range(100):
        if "m" not in rt._busy:
            break
        threading.Event().wait(0.02)
    timings = rt.sessions["m"].timings
    assert [t["sequence"] for t in timings] == [1, 4]  # two analyses, not three
    assert timings[-1]["category"] == "PRICE_BUDGET" and timings[-1]["superseded_leads"] == 1


def test_explicit_price_words_win_over_need_value_fit(kb):
    from closer_ai.live.session import price_override
    assert price_override("NEED_VALUE_FIT", "Gostei da proposta, mas achei muito caro.") == "PRICE_BUDGET"
    assert price_override("NEED_VALUE_FIT", "Não cabe no nosso orçamento agora.") == "PRICE_BUDGET"
    assert price_override("NEED_VALUE_FIT", "Não sei se isso resolve meu problema.") == "NEED_VALUE_FIT"
    assert price_override("NEED_VALUE_FIT", "Cara, não sei se faz diferença pra gente.") == "NEED_VALUE_FIT"
    assert price_override("NEED_VALUE_FIT", "Não preciso disso, e ainda é caro.") == "NEED_VALUE_FIT"  # mixed
    assert price_override("TRUST_RISK", "É caro e tenho medo de não funcionar.") == "TRUST_RISK"  # only NVF

    s, _, clock = _session(kb)
    _say(s, clock, 1, "lead", "Gostei, mas achei caro demais.")
    t = s.analyze()
    assert (t["category_before"], t["category"], t["outcome"]) == ("NEED_VALUE_FIT", "PRICE_BUDGET", "RECOMMENDED")
    assert s.current().knowledge_unit == "guidance.PRICE_BUDGET"
    s, _, clock = _session(kb)
    _say(s, clock, 1, "lead", "Não sei se isso resolve meu problema.")
    t = s.analyze()
    assert (t["category"], "category_before" in t) == ("NEED_VALUE_FIT", False)


def test_explicit_third_party_decision_wins_over_timing(kb):
    from closer_ai.live.session import authority_override, price_override

    def norm(category, text):  # the live policy applies both, in this order
        return authority_override(price_override(category, text), text)

    # the classifier label each line got (or could get) -> the category the live policy uses
    assert norm("TIMING_PRIORITY", "Preciso falar com o meu sócio antes de fechar.") == "AUTHORITY_INTERNAL_BUY_IN"
    assert norm("TIMING_PRIORITY", "Preciso falar com o meu sócio antes") == "AUTHORITY_INTERNAL_BUY_IN"
    assert norm("TIMING_PRIORITY", "Tenho que validar isso com meu chefe antes de decidir.") == "AUTHORITY_INTERNAL_BUY_IN"
    assert norm("TIMING_PRIORITY", "Quem decide isso é a diretoria.") == "AUTHORITY_INTERNAL_BUY_IN"
    assert norm("TIMING_PRIORITY", "Preciso conversar com meu marido antes.") == "AUTHORITY_INTERNAL_BUY_IN"
    assert norm("AUTHORITY_INTERNAL_BUY_IN", "Preciso falar com o meu sócio antes de fechar.") == "AUTHORITY_INTERNAL_BUY_IN"
    assert norm("TIMING_PRIORITY", "Agora não é um bom momento. Vamos falar mês que vem.") == "TIMING_PRIORITY"
    assert norm("NEED_VALUE_FIT", "Não sei se isso resolve meu problema.") == "NEED_VALUE_FIT"
    assert norm("NEED_VALUE_FIT", "Gostei, mas achei muito caro.") == "PRICE_BUDGET"
    # a role word alone, or a dependency plus an explicit time, is not overridden
    assert norm("TIMING_PRIORITY", "Meu sócio gostou, mas agora não dá.") == "TIMING_PRIORITY"
    assert norm("TIMING_PRIORITY", "Meu sócio está viajando e só volta mês que vem, então vamos deixar para novembro."
                ) == "TIMING_PRIORITY"
    assert norm("TIMING_PRIORITY", "Vou falar com meu sócio em novembro.") == "TIMING_PRIORITY"
    assert norm("NEED_VALUE_FIT", "Preciso falar com meu sócio antes.") == "NEED_VALUE_FIT"  # only TIMING is touched

    # through the session: normalized before retrieval, so the AUTHORITY knowledge unit is used
    s, provider, clock = _session(kb)
    _say(s, clock, 1, "lead", "Preciso falar com o meu sócio antes")
    t = s.analyze()
    assert (t["category_before"], t["category"], t["outcome"]) == ("TIMING_PRIORITY", "AUTHORITY_INTERNAL_BUY_IN",
                                                                   "RECOMMENDED")
    assert s.current().knowledge_unit == "guidance.AUTHORITY_INTERNAL_BUY_IN"
    assert "Objection category (classifier): AUTHORITY_INTERNAL_BUY_IN" in provider.prompts[-1]
    s, _, clock = _session(kb)
    _say(s, clock, 1, "lead", "Agora não é um bom momento. Vamos falar mês que vem.")
    t = s.analyze()
    assert (t["category"], "category_before" in t) == ("TIMING_PRIORITY", False)
    assert s.current().knowledge_unit == "guidance.TIMING_PRIORITY"


def test_guidance_may_reuse_facts_said_earlier_in_the_window(kb):
    question = "Comparado ao tempo que vocês perdem hoje, caro em relação a quê?"
    s, _, clock = _session(kb, provider=FakeProvider(bad_guidance=question))
    _say(s, clock, 1, "closer", "Como vocês fazem esse processo hoje?")
    _say(s, clock, 2, "lead", "Hoje a gente perde bastante tempo fazendo isso manualmente.")
    _say(s, clock, 3, "closer", "E como isso impacta vocês?")
    s.analyze()
    _say(s, clock, 4, "lead", "Gostei da proposta, mas achei muito caro.")
    t = s.analyze()
    assert (t["outcome"], t["reason"]) == ("RECOMMENDED", "GUIDED")
    assert s.current().question == question
    assert s.last_guidance.objection_evidence[0].text == "Gostei da proposta, mas achei muito caro."
    # the same "hoje" with no captured line saying it is still rejected (fail closed)
    s, _, clock = _session(kb, provider=FakeProvider(bad_guidance=question))
    _say(s, clock, 1, "lead", "Gostei da proposta, mas achei muito caro.")
    assert s.analyze()["reason"] == "GUIDANCE_INVALID_RESPONSE"


def test_active_analysis_is_never_confused_with_the_last_completed_one(kb):
    gate, in_price = threading.Event(), threading.Event()
    guidance_gate, in_guidance = threading.Event(), threading.Event()

    class Slow(FakeProvider):
        def classify(self, prompt, **_):
            if not prompt.startswith("GUIDANCE TASK") and "achei muito caro" in prompt:
                in_price.set()
                gate.wait(5)  # hold the price analysis open while the sidebar polls
            if prompt.startswith("GUIDANCE TASK") and "caro" in prompt:
                in_guidance.set()
                guidance_gate.wait(5)  # hold the guidance open: objection known, suggestion not ready
            return super().classify(prompt)

    rt = Runtime(Slow(), LiveConfig(), {"Matheus"}, log=lambda s: None)
    rt.knowledge = kb
    for seq, (sp, tx) in enumerate([("Você", "Como vocês fazem esse processo hoje?"),
                                    ("Lead Teste", "A gente perde bastante tempo com isso."),
                                    ("Você", "E como isso impacta vocês?"),
                                    ("Lead Teste", "Gostei da proposta, mas achei muito caro.")], 1):
        rt.receive(parse_utterance({"meeting_id": "m", "speaker": sp, "text": tx, "sequence": seq},
                                   rt.closer_names, 1.0))
        if seq == 2:  # let the pain-line analysis finish first, as in the real Meet
            for _ in range(100):
                if rt.sessions["m"].last_completed_analysis:
                    break
                threading.Event().wait(0.02)
    assert in_price.wait(5)
    during = rt.recommendation("m")
    assert during["status"] == "ANALYZING" and during["state"] == "NONE"
    assert (during["active_analysis"]["segment_id"], during["active_analysis"]["role"],
            during["active_analysis"]["text_preview"]) == ("seg_4", "lead", "Gostei da proposta, mas achei muito caro.")
    assert {k: during["last_completed_analysis"][k] for k in ("segment_id", "category", "outcome", "reason")} == {
        "segment_id": "seg_2", "category": "IMPLEMENTATION_INTEGRATION", "outcome": "NO_RECOMMENDATION",
        "reason": "UNCORROBORATED_CATEGORY"}
    assert "detected_category" not in during["active_analysis"]  # classifier still running
    gate.set()
    assert in_guidance.wait(5)
    detected = rt.recommendation("m")  # policy decided, guidance not ready: the sidebar's red state
    assert detected["state"] == "NONE" and detected["active_analysis"]["detected_category"] == "PRICE_BUDGET"
    assert detected["active_analysis"]["label"] == "Preço / orçamento"
    guidance_gate.set()
    for _ in range(100):
        after = rt.recommendation("m")
        if after["active_analysis"] is None:
            break
        threading.Event().wait(0.02)
    assert after["state"] == "ACTIVE" and after["category"] == "PRICE_BUDGET"
    assert {k: after["last_completed_analysis"][k] for k in ("segment_id", "category", "outcome")} == {
        "segment_id": "seg_4", "category": "PRICE_BUDGET", "outcome": "RECOMMENDED"}


# --- P0 reliability ---------------------------------------------------------------------------------

def test_second_runtime_on_the_same_port_fails_clearly(kb):
    from closer_ai.live.server import bind_or_explain
    rt = Runtime(FakeProvider(), LiveConfig(), {"Matheus"}, log=lambda s: None)
    first = bind_or_explain(0, make_handler(rt))
    port = first.server_address[1]
    threading.Thread(target=first.serve_forever, daemon=True).start()
    try:
        with pytest.raises(SystemExit) as exc:
            bind_or_explain(port, make_handler(rt))
        assert f"ERROR: AI Closer runtime already running on 127.0.0.1:{port}" in str(exc.value)
    finally:
        first.shutdown()
        first.server_close()


def test_retries_are_idempotent_and_counted(kb):
    s, _, clock = _session(kb)
    assert _say(s, clock, 1, "closer", "Como vocês fazem isso hoje?")
    assert not _say(s, clock, 1, "closer", "Como vocês fazem isso hoje?")  # retry, same id
    assert s.last_add_status == "DUPLICATE_SEQUENCE"
    assert not _say(s, clock, 2, "closer", "Como vocês fazem isso hoje?")  # caption repeated, new id
    assert s.last_add_status == "DUPLICATE_TEXT"
    assert not _say(s, clock, 3, "lead", "   ")
    assert s.last_add_status == "EMPTY"
    assert len(s.utterances) == 1
    assert {k: s.counters[k] for k in ("received", "accepted", "duplicates_suppressed", "rejected")} == {
        "received": 4, "accepted": 1, "duplicates_suppressed": 2, "rejected": 1}
    _say(s, clock, 4, "lead", "Gostei da proposta, mas achei muito caro.")
    s.analyze()
    assert {k: s.counters[k] for k in ("analyses_started", "analyses_completed", "recommendations_created")} == {
        "analyses_started": 1, "analyses_completed": 1, "recommendations_created": 1}


def test_an_unexpected_error_never_leaves_the_dock_stuck_analyzing(kb):
    class Broken(FakeProvider):
        def classify(self, prompt, **_):
            raise KeyError("boom")  # not an Ollama/format error: a bug anywhere in the pipeline

    s, _, clock = _session(kb, provider=Broken())
    _say(s, clock, 1, "lead", "Gostei da proposta, mas achei muito caro.")
    t = s.analyze()
    assert (t["outcome"], t["reason"]) == ("NO_RECOMMENDATION", "ERROR:UNEXPECTED:KeyError")
    assert s.active_analysis is None and s.last_completed_analysis["reason"] == "ERROR:UNEXPECTED:KeyError"
    assert s.counters["analysis_errors"] == 1
    assert s.error_reasons == {"OTHER": 1} and "KeyError" in s.error_examples["OTHER"]  # counted by type, not lumped


# --- session recovery after a runtime restart ---------------------------------------------------------

MEETING = [(1, "Você", "Como vocês fazem esse processo hoje?"), (2, "Lead Teste", "Hoje temos cinco pessoas no time."),
           (3, "Lead Teste", "Gostei da proposta, mas achei muito caro.")]


def _payload(seq, speaker, text):
    return {"speaker": speaker, "text": text, "timestamp": 1_700_000_000 + seq, "sequence": seq}


def test_restart_rehydration_restores_context_without_reanalysis(kb):
    old = Runtime(FakeProvider(), LiveConfig(), {"Matheus"}, log=lambda s: None)
    old.knowledge = kb
    for seq, sp, tx in MEETING:  # 1. the meeting had 3 utterances (the lead lines were analyzed live)
        assert old.receive(parse_utterance({"meeting_id": "m", **_payload(seq, sp, tx)}, old.closer_names, 1.0),
                           background=False) == "ACCEPTED"
    assert old.sessions["m"].current() is not None

    provider = FakeProvider()  # 2. runtime restarted: new process, empty sessions, a new instance id
    new = Runtime(provider, LiveConfig(), {"Matheus"}, log=lambda s: None)
    new.knowledge = kb
    assert new.instance != old.instance and new.recommendation("m")["transcript"] == []

    out = new.rehydrate("m", [_payload(*u) for u in MEETING])  # 3. the extension sends them back
    s = new.sessions["m"]
    assert out["rehydrated"] == 3 and out["utterances"] == 3
    view = new.recommendation("m")
    assert [u["text"] for u in view["transcript"]] == [tx for _, _, tx in MEETING]  # 4. history kept, in order
    assert [u["role"] for u in view["transcript"]] == ["closer", "lead", "lead"]
    # 5. no analysis (only the background commercial-state rebuild may read the lines)
    assert not [p for p in provider.prompts if not p.startswith("COMMERCIAL FACTS TASK")]
    assert not s.should_analyze() and view["status"] == "CAPTURING"
    assert (view["state"], view["last_completed_analysis"]) == ("NONE", None)  # nothing invented
    assert (s.counters["received"], s.counters["accepted"], s.counters["rehydrated"]) == (0, 0, 3)  # not live delivery

    assert new.rehydrate("m", [_payload(*u) for u in MEETING])["rehydrated"] == 0  # 7. idempotent (resent twice)
    status = new.receive(parse_utterance({"meeting_id": "m", **_payload(4, "Lead Teste",
                                          "Se der certo, eu quero avançar ainda esse mês.")}, new.closer_names, 2.0),
                         background=False)
    assert status == "ACCEPTED" and len(s.utterances) == 4  # 6. a new line is the fourth...
    assert [u.sequence for u in s.utterances] == [1, 2, 3, 4]
    assert len(provider.prompts) >= 1  # ...and is analyzed live, as usual
    assert new.receive(parse_utterance({"meeting_id": "m", **_payload(3, "Lead Teste", MEETING[2][2])},
                                       new.closer_names, 2.0)) == "DUPLICATE_SEQUENCE"  # a late retry: no duplicate
    assert len(s.utterances) == 4
    assert new.recommendation("other")["transcript"] == []  # 8. another meeting inherits nothing


def test_rehydrated_lines_never_reanalyzed_even_if_a_live_retry_came_first(kb):
    s, provider, clock = _session(kb)
    _say(s, clock, 5, "lead", "Gostei da proposta, mas achei muito caro.")  # an old line retried live after restart
    assert s.should_analyze()
    added = s.rehydrate([LiveUtterance("m1", "Lead", "lead", "Hoje temos cinco pessoas no time.", 1.0, 4, 1.0),
                         LiveUtterance("m1", "Lead", "lead", "Preciso falar com meu sócio antes de fechar.", 1.0, 6, 1.0)])
    assert added == 2 and [u.sequence for u in s.utterances] == [4, 5, 6]
    assert not s.should_analyze()  # line 5 is older than what the previous runtime had already seen
    assert provider.prompts == []


def test_rehydrate_endpoint_over_http(kb):
    rt = Runtime(FakeProvider(), LiveConfig(), {"Matheus"}, log=lambda s: None)
    rt.knowledge = kb
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(rt))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        body = json.dumps({"meeting_id": "m", "utterances": [_payload(*u) for u in MEETING]}).encode()
        req = urllib.request.Request(base + "/rehydrate", data=body,
                                     headers={"X-AI-Closer": "1", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as r:
            out = json.loads(r.read())
        assert (out["rehydrated"], out["utterances"], out["instance"]) == (3, 3, rt.instance)
        with urllib.request.urlopen(base + "/health", timeout=5) as r:
            assert json.loads(r.read())["instance"] == rt.instance
    finally:
        server.shutdown()


# --- latest-utterance anchoring: the NEW lead line is the target, the window is context -------------

def _episode(objection, category, context=()):
    return {"prediction_id": f"p{objection[0]}", "objection_segment_ids": list(objection),
            "context_segment_ids": list(context), "category_status": "PRESENT", "category": category,
            "category_candidates": [], "reaction_status": "ABSENT", "reaction": None, "reaction_candidates": [],
            "resolution_status": "unknown", "summary": "Objeção do lead."}


class Scripted(FakeProvider):
    """Classifier answers come from `answer(prompt)` (to play a misbehaving model); guidance as FakeProvider."""

    def __init__(self, answer):
        super().__init__()
        self.answer = answer

    def classify(self, prompt, **kw):
        if prompt.startswith("GUIDANCE TASK"):
            return super().classify(prompt, **kw)
        self.prompts.append(prompt)
        episodes = self.answer(prompt)
        return {"call_detection": "OBJECTIONS_FOUND" if episodes else "NO_OBJECTION", "episodes": episodes,
                "uncertain_spans": []}


def _live(s, clock, lines):
    """Feed (role, text) lines as a call, analyzing after each lead line; returns the last lead line's analysis."""
    t = None
    for seq, (role, text) in enumerate(lines, len(s.utterances) + 1):  # continues the session's numbering
        clock.now += 8
        _say(s, clock, seq, role, text)
        if s.should_analyze():
            t = s.analyze()
    return t


def test_the_prompt_targets_only_the_new_lead_line(kb):
    s, provider, clock = _session(kb)
    _live(s, clock, [("lead", "Gostei da proposta, mas achei muito caro."), ("closer", "Entendi."),
                     ("lead", "Preciso falar com meu sócio antes de fechar.")])
    first, second = [p for p in provider.prompts if not p.startswith("GUIDANCE TASK")]
    assert "LIVE TARGET" in first and "The lead just said: seg_1." in first
    assert "The lead just said: seg_3." in second  # the old objection is context, not a target
    assert "Gostei da proposta" in second  # ...but still visible as context


def test_price_then_authority_gives_authority_in_the_same_session(kb):
    s, _, clock = _session(kb)
    t1 = _live(s, clock, [("lead", "Gostei da proposta, mas achei muito caro.")])
    assert (t1["category"], s.current().category) == ("PRICE_BUDGET", "PRICE_BUDGET")
    t2 = _live(s, clock, [("lead", "Preciso falar com meu sócio antes de fechar.")])
    assert (t2["category"], t2["outcome"]) == ("AUTHORITY_INTERNAL_BUY_IN", "RECOMMENDED")
    assert s.current().category == "AUTHORITY_INTERNAL_BUY_IN"  # replaced the PRICE recommendation


def test_authority_then_price_gives_price(kb):
    s, _, clock = _session(kb)
    t = _live(s, clock, [("lead", "Preciso validar com minha sócia."), ("closer", "Claro, faz sentido."),
                         ("lead", "Mas o principal problema para mim ainda é o preço.")])
    assert (t["category"], s.current().category) == ("PRICE_BUDGET", "PRICE_BUDGET")


def test_timing_and_need_value_fit_still_classified(kb):
    s, _, clock = _session(kb)
    assert _live(s, clock, [("lead", "Hoje temos cinco pessoas no time."), ("closer", "E o momento de vocês?"),
                            ("lead", "Agora não é o momento, talvez no próximo trimestre.")])["category"] == \
        "TIMING_PRIORITY"
    s, _, clock = _session(kb)
    assert _live(s, clock, [("lead", "Gostei da proposta, mas achei muito caro."), ("closer", "Entendi."),
                            ("lead", "Sinceramente não sei se a gente precisa disso.")])["category"] == \
        "NEED_VALUE_FIT"


def test_an_old_objection_never_satisfies_a_new_analysis(kb):
    # the model re-annotates only the old PRICE line (the real-Meet failure): no new episode, nothing reused
    old_only = Scripted(lambda prompt: [_episode(["seg_1"], "PRICE_BUDGET")])
    s, _, clock = _session(kb, provider=old_only)
    t = _live(s, clock, [("lead", "Está muito caro, de verdade."), ("closer", "Entendi."),
                         ("lead", "Hoje temos cinco pessoas no time.")])
    assert (t["outcome"], t["reason"]) == ("NO_RECOMMENDATION", "NO_QUALIFYING_EPISODE")


def test_a_neutral_line_folded_into_an_old_objection_is_rejected(kb):
    # the model "folds" the new neutral line into the old PRICE episode across the closer's turn
    def folded(prompt):
        ids = [i for i, role, _ in _SEG.findall(prompt) if role == "lead"]
        return [_episode(ids, "PRICE_BUDGET")]

    s, provider, clock = _session(kb, provider=Scripted(folded))
    first = _live(s, clock, [("lead", "Está muito caro, de verdade.")])
    assert first["category"] == "PRICE_BUDGET"
    clock.now += 60  # past the cooldown, so a repeated PRICE would be shown again
    t = _live(s, clock, [("closer", "Entendi."), ("lead", "Hoje temos cinco pessoas no time.")])
    assert (t["outcome"], t["reason"]) == ("NO_RECOMMENDATION", "NO_QUALIFYING_EPISODE")
    assert provider.guidance_calls() == 1  # no second PRICE guidance


def test_a_continuation_in_the_same_lead_turn_is_kept(kb):
    # "Eu gostei." is too short to be analyzed alone; the next line completes it in the same turn
    cont = Scripted(lambda prompt: [_episode(["seg_1", "seg_2"], "PRICE_BUDGET")] if "seg_2" in prompt else [])
    s, _, clock = _session(kb, provider=cont)
    t = _live(s, clock, [("lead", "Eu gostei."), ("lead", "Mas está acima do que eu consigo investir agora.")])
    assert (t["category"], t["outcome"]) == ("PRICE_BUDGET", "RECOMMENDED")


def test_a_continuation_of_an_already_analyzed_line_in_the_same_turn_is_kept(kb):
    two = Scripted(lambda prompt: [_episode(["seg_1", "seg_2"], "PRICE_BUDGET")] if "seg_2" in prompt else [])
    s, _, clock = _session(kb, provider=two)
    t = _live(s, clock, [("lead", "Eu gostei bastante do que vi aqui."),  # analyzed: no objection
                         ("lead", "Mas está acima do que eu consigo investir agora.")])
    assert (t["category"], t["outcome"]) == ("PRICE_BUDGET", "RECOMMENDED")


def test_a_short_answer_to_a_context_question_is_interpretable(kb):
    s, provider, clock = _session(kb)
    t = _live(s, clock, [("closer", "Além de você, alguém participa da decisão?"), ("lead", "Sim, meu sócio.")])
    assert (t["category"], t["outcome"]) == ("AUTHORITY_INTERNAL_BUY_IN", "RECOMMENDED")
    prompt = next(p for p in provider.prompts if not p.startswith("GUIDANCE TASK"))
    assert "Além de você, alguém participa da decisão?" in prompt and "The lead just said: seg_2." in prompt


def test_neutral_lines_only_give_no_recommendation(kb):
    s, _, clock = _session(kb)
    t = _live(s, clock, [("lead", "Hoje temos cinco pessoas no time."), ("closer", "Legal."),
                         ("lead", "A gente usa uma planilha compartilhada.")])
    assert (t["outcome"], s.current()) == ("NO_RECOMMENDATION", None)
