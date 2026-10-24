"""Real Call Validation & Calibration v1: replay, annotation contract, metrics, report, compare."""
from __future__ import annotations

import json
import re
import time

import pytest
from test_live_session import SCRIPT, FakeProvider  # same folder

from closer_ai.live import eval as ev
from closer_ai.live import eval_metrics as em
from closer_ai.live.session import LiveConfig

PRICE = "Mas está acima do que eu consigo investir agora."
TIMING = "Agora não é o momento, talvez no próximo trimestre."
NOISE = "Pera aí, travou tudo aqui."


def _rows(mid, lines, gap=None):
    rows = [{"meeting_id": mid, "speaker": "Closer A" if r == "closer" else "Lead B", "role": r, "text": t,
             "sequence": i} for i, (r, t) in enumerate(lines, 1)]
    if gap is not None:
        for i, r in enumerate(rows):
            r["timestamp"] = 1_000.0 + i * gap
    return rows


def _run(calls, provider=None, annotations=()):
    trace, sessions = ev.run(calls, provider or FakeProvider(), LiveConfig())
    return trace, sessions, em.compute(calls, list(annotations), trace, sessions)


# --- import / ordering ------------------------------------------------------------------------------

def test_load_sorts_by_sequence_and_rejects_bad_rows(tmp_path):
    f = tmp_path / "c.jsonl"
    rows = _rows("m", [("closer", "Oi, tudo bem?"), ("lead", PRICE)])
    f.write_text("".join(json.dumps(r) + "\n" for r in reversed(rows)), encoding="utf-8")
    assert [r["sequence"] for r in ev.load_calls(f)["m"]] == [1, 2]
    assert ev.validate_rows([{**rows[0], "role": "boss"}, rows[0]]) == [
        "row 0: role must be one of ('closer', 'lead', 'other')", "duplicate (meeting_id, sequence)"]
    f.write_text(json.dumps({**rows[0], "sequence": "1"}) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="sequence must be int"):
        ev.load_calls(f)


def test_calibration_kit_adapter_reads_the_12_calls_in_place():
    calls = ev.load_calls(ev.KIT)
    assert sorted(calls) == [f"CAL{i:02d}" for i in range(1, 13)]
    assert calls["CAL01"][1] == {"meeting_id": "CAL01", "speaker": "CAL01_LEAD", "role": "lead", "sequence": 2,
                                 "segment_ref": "CAL01_S01", "text": calls["CAL01"][1]["text"]}
    ann = em.load_annotations([ev.KIT], [])
    roles = {(r["meeting_id"], r["sequence"]): r["role"] for rows in calls.values() for r in rows}
    labels = [a for a in ann if "sequence" in a]
    assert labels and all(roles[(a["meeting_id"], a["sequence"])] == "lead" for a in labels)


def test_replay_feeds_one_utterance_at_a_time_in_order():
    calls = {"m": _rows("m", [("closer", "O que achou?"), ("lead", PRICE), ("closer", "Entendo."), ("lead", NOISE)])}
    trace, sessions, _ = _run(calls)
    utt = [e for e in trace if e["kind"] == "utterance"]
    assert [e["sequence"] for e in utt] == [1, 2, 3, 4]
    assert [e["runtime_role"] for e in utt] == ["closer", "lead", "closer", "lead"]
    a = next(e for e in trace if e["kind"] == "analysis" and e["sequence"] == 2)
    assert trace.index(a) > trace.index(utt[1]) and trace.index(a) < trace.index(utt[2])  # before the next line
    assert utt[1]["objection"]["detected"] and utt[1]["objection"]["category"] == "PRICE_BUDGET"
    assert utt[1]["objection"]["recommendation_state"] == "ACTIVE" and utt[1]["timings"]["displayed_ms"] is not None
    assert utt[3]["objection"]["analyzed"] == "ANALYZED" and not utt[3]["objection"]["detected"]
    assert sessions[0]["lead_utterances"] == 2 and sessions[0]["objections_detected"] == 1


class Slow(FakeProvider):
    def classify(self, prompt, **kw):
        if not prompt.startswith(("GUIDANCE TASK", "COMMERCIAL FACTS TASK")):
            time.sleep(0.3)
        return super().classify(prompt, **kw)


def test_lines_said_during_an_analysis_wait_and_the_latest_wins():
    # 0.05 s apart, analysis 0.3 s: line 2 is analyzed, 3 waits and is replaced by 4 (coalesced)
    calls = {"m": _rows("m", [("closer", "E aí?"), ("lead", NOISE), ("lead", PRICE), ("lead", TIMING)], gap=0.05)}
    trace, _, _ = _run(calls, Slow())
    utt = {e["sequence"]: e for e in trace if e["kind"] == "utterance"}
    assert utt[2]["objection"]["analyzed"] == "ANALYZED"
    assert utt[3]["objection"]["analyzed"] == "COALESCED"
    assert utt[4]["objection"]["analyzed"] == "ANALYZED"
    assert utt[3]["visible_at"] >= 1_000.3  # its snapshot waits for the running job (documented limit)


def test_virtual_clock_keeps_ttl_semantics():
    # the same recommendation is gone 100 s later (TTL 90 s) even though the replay takes milliseconds
    calls = {"m": _rows("m", [("closer", "O que achou?"), ("lead", PRICE), ("closer", "Ok"), ("closer", "Ok então")],
                        gap=50)}
    trace, _, _ = _run(calls)
    utt = [e for e in trace if e["kind"] == "utterance"]
    shown = next(e for e in trace if e["kind"] == "analysis")
    assert shown["seller_action"]["source"] == "OBJECTION" and utt[2]["seller_action"]["source"] == "OBJECTION"
    assert utt[3]["seller_action"] is None


def test_sampling_is_deterministic_and_diverse():
    calls = {f"c{i}": _rows(f"c{i}", [("lead", t)]) for i, t in enumerate(
        ["Achei caro.", "Preciso falar com meu sócio.", "Vou pensar.", "Bom dia."] * 3)}
    a, b = ev.select_calls(calls, 4, "s"), ev.select_calls(calls, 4, "s")
    assert a == b and len(a) == 4
    assert {t for m in a for t in ev.call_tags(calls[m])} >= {"price", "authority", "think"}
    assert ev.select_calls(calls, 0) == sorted(calls)


# --- annotation contract ----------------------------------------------------------------------------

def test_readme_example_and_fixtures_follow_the_schema():
    readme = (ev.ROOT / "evals" / "real_calls" / "README.md").read_text(encoding="utf-8")
    block = re.search(r"## Annotation contract.*?```json\n(.*?)```", readme, re.DOTALL).group(1)
    records = json.loads("[" + block.replace("}\n{", "},\n{") + "]")
    assert len(records) == 2 and all(em.validate_annotation(r) == [] for r in records)
    assert em.load_annotations([ev.FIXTURES], [])  # every fixture record validates


@pytest.mark.parametrize("record, error", [
    ({"meeting_id": "m", "sequence": 1, "expected_objection": {"present": "yes"}}, "not in"),
    ({"meeting_id": "m", "sequence": 1, "expected_objection": {"present": True, "category": "PRICE"}}, "not in"),
    ({"meeting_id": "m", "sequence": 1, "scope": {"objections": "COMPLETE"}}, "belongs to the call record"),
    ({"meeting_id": "m", "expected_facts": [{"type": "pain", "value": "x"}]}, "needs a sequence"),
    ({"meeting_id": "m", "sequence": 1, "expected_facts": [{"type": "budget", "value": "x"}]}, "not in"),
    ({"meeting_id": "m", "sequence": 1, "colour": "red"}, "unknown field"),
    ({"sequence": 1}, "missing meeting_id"),
])
def test_invalid_annotations_are_rejected(record, error):
    assert any(error in e for e in em.validate_annotation(record))


# --- metrics ----------------------------------------------------------------------------------------

def test_objection_counts_tp_fp_fn_duplicates_and_rates():
    calls = {"m": _rows("m", [("closer", "O que achou?"), ("lead", PRICE), ("closer", "Ok"), ("lead", TIMING),
                              ("closer", "Certo"), ("lead", NOISE), ("lead", "Agora não é um bom momento. Vamos falar mês que vem.")])}
    ann = [{"meeting_id": "m", "scope": {"objections": "COMPLETE"}},
           {"meeting_id": "m", "sequence": 2, "expected_objection": {"present": True, "category": "PRICE_BUDGET"}},
           {"meeting_id": "m", "sequence": 4, "expected_objection": {"present": False}},
           {"meeting_id": "m", "sequence": 6, "expected_objection": {"present": True, "category": "TRUST_RISK"},
            "accept_at": [7]}]
    _, _, m = _run(calls, annotations=ann)
    o = m["objections"]
    # 2 = TP; 4 = FP (explicit negative); 6 missed, but 7 (TIMING) lands in its span -> TP, wrong category
    assert (o["tp"], o["fp"], o["fn"]) == (2, 1, 0)
    assert (o["precision"], o["recall"], o["labeled_negatives"], o["false_positive_rate"]) == (0.667, 1.0, 1, 1.0)
    assert o["category_accuracy"] == 0.5 and o["category_confusion"] == {"TRUST_RISK -> TIMING_PRIORITY": 1}
    assert o["fp_by_category"] == {"TIMING_PRIORITY": 1}
    fp = m["_false_positives"][0]
    assert (fp["sequence"], fp["text"], fp["classifier_source"]) == (4, TIMING, "llm")
    assert [p["sequence"] for p in fp["previous"]] == [1, 2, 3]


def test_unlabeled_calls_are_reported_unlabeled_not_scored():
    calls = {"m": _rows("m", [("closer", "O que achou?"), ("lead", PRICE)])}
    trace, _, m = _run(calls)
    assert m["objections"] == {"status": "UNLABELED", "unlabeled_detections": 1}
    assert m["opportunities"]["status"] == m["commercial_state"]["status"] == m["compliance"]["status"] == "UNLABELED"
    assert m["summary"]["unlabeled_calls"] == ["m"]
    stubs = em.review_template(trace, set())
    assert stubs[0]["scope"]["objections"] == "NONE" and stubs[1]["sequence"] == 2
    assert not any("expected_objection" in s for s in stubs)  # nothing invented


def test_partial_scope_never_creates_false_positives():
    calls = {"m": _rows("m", [("closer", "O que achou?"), ("lead", PRICE), ("lead", TIMING)])}
    ann = [{"meeting_id": "m", "sequence": 2, "expected_objection": {"present": True, "category": "PRICE_BUDGET"}}]
    _, _, m = _run(calls, annotations=ann)
    assert (m["objections"]["tp"], m["objections"]["fp"], m["objections"]["unlabeled_detections"]) == (1, 0, 1)


def test_opportunity_metrics_per_op_with_resolution_and_false_opportunities():
    calls = {"m": _rows("m", [("closer", "Esse é o formato."), ("lead", "Pode pagar no cartão da empresa?"),
                              ("closer", "Faz sentido a gente seguir?"), ("lead", "Vou pensar.")])}
    ann = [{"meeting_id": "m", "scope": {"opportunities": "COMPLETE"}},
           {"meeting_id": "m", "sequence": 2, "expected_opportunities": [{"id": "OP-14", "final_status": "ACTIVE"}]},
           {"meeting_id": "m", "sequence": 1, "expected_opportunities": ["OP-03"]}]
    _, _, m = _run(calls, annotations=ann)
    op = m["opportunities"]
    assert (op["tp"], op["fp"], op["fn"], op["resolution_accuracy"]) == (1, 1, 1, 0.0)  # OP-14 was RESOLVED
    assert op["by_op"]["OP-12"]["fp"] == 1 and op["by_op"]["OP-03"]["fn"] == 1
    patterns = {i["pattern"] for i in m["issues"]}
    assert {"FALSE_OPPORTUNITY", "MISSED_DECISION_DEPENDENCY", "WRONG_RESOLUTION"} <= patterns


def test_fact_and_compliance_metrics():
    from closer_ai.live.eval_metrics import compliance_metrics, fact_metrics
    sessions = [{"meeting_id": "m", "final": {"opportunities": [], "rules": {"E6-R1": "SATISFIED", "E6-R2": "PENDING"},
                                              "facts": {"stakeholders": [{"value": "sócio", "segment_ids": ["seg_2"]}],
                                                        "pain_points": [{"value": "planilha", "segment_ids": ["seg_3"]}]}}}]
    trace = [{"kind": "utterance", "meeting_id": "m", "segment_id": f"seg_{i}", "sequence": i} for i in (1, 2, 3)]
    calls = {"m": {"scope": {"facts": "COMPLETE"}, "expected_rules": {"E6-R1": "SATISFIED", "E6-R2": "SATISFIED"}}}
    utts = {"m": [{"meeting_id": "m", "sequence": 2, "expected_facts": [{"type": "stakeholder", "value": "Sócio"}]},
                  {"meeting_id": "m", "sequence": 3, "expected_facts": [{"type": "impact", "value": "3 horas"}]}]}
    issues = []
    f = fact_metrics(calls, utts, trace, sessions, issues)
    assert f["by_type"]["stakeholder"]["recall"] == 1.0 and f["by_type"]["impact"]["recall"] == 0.0
    assert f["by_type"]["pain"]["precision"] == 0.0 and f["recall"] == 0.5
    c = compliance_metrics(calls, sessions, issues)
    assert c["correct_by_status"]["SATISFIED"] == {"correct": 1, "total": 2, "accuracy": 0.5}
    assert c["coverage"]["rules_evaluated"] == 2 and c["coverage"]["rules_in_playbook"] > 19


def test_latency_stats_by_path_never_mix_no_recommendation():
    assert em.stats([]) is None and em.stats([None]) is None
    s = em.stats(list(range(1, 101)))
    assert (s["median"], s["p90"], s["p95"], s["max"]) == (50.5, 90, 95, 100)
    calls = {"m": _rows("m", [("closer", "O que achou?"), ("lead", PRICE), ("lead", NOISE),
                              ("lead", "Pode pagar no cartão da empresa?")])}
    _, _, m = _run(calls)
    lat = m["latency"]
    assert sum((lat[p] or {"n": 0})["n"] for p in ("FAST_PATH", "LLM_CLASSIFIER")) == 1  # only the price line
    assert lat["NO_RECOMMENDATION"]["n"] == 2 and lat["OPPORTUNITY_ONLY"]["n"] == 1


def test_seller_action_metrics_and_stale_cards():
    trace = [{"kind": "utterance", "meeting_id": "m", "sequence": 1, "visible_at": 1.0, "recommendation": {"category": "PRICE_BUDGET"},
              "seller_action": {"source": "OBJECTION", "source_id": "rec:1"}},
             {"kind": "utterance", "meeting_id": "m", "sequence": 2, "visible_at": 2.0, "recommendation": None,
              "seller_action": {"source": "OPPORTUNITY", "source_id": "OP-14:call#1"}},
             {"kind": "utterance", "meeting_id": "m", "sequence": 3, "visible_at": 3.0, "recommendation": {"category": "PRICE_BUDGET"},
              "seller_action": {"source": "OBJECTION", "source_id": "rec:1"}},
             {"kind": "utterance", "meeting_id": "m", "sequence": 4, "visible_at": 4.0, "recommendation": {"category": "PRICE_BUDGET"},
              "seller_action": {"source": "OBJECTION", "source_id": "rec:2"}}]
    utts = {"m": [{"meeting_id": "m", "sequence": 2, "expected_seller_action": {"source": "OPPORTUNITY", "id": "OP-14"}},
                  {"meeting_id": "m", "sequence": 3, "expected_seller_action": {"source": "NONE"},
                   "seller_action_quality": "BAD"}]}
    issues = []
    s = em.seller_metrics({}, utts, trace, issues)
    assert (s["stale_card"], s["duplicate_card"]) == (1, 1)
    assert (s["correct_source"], s["correct_priority"], s["action_available_when_needed"]) == (0.5, 1.0, 1.0)
    assert s["quality_labels"] == {"BAD": 1}
    assert {i["kind"] for i in issues} == {"STALE_CARD", "DUPLICATE_CARD", "WRONG_CARD"}


# --- known regressions, patterns, report, compare ---------------------------------------------------

def test_known_failures_are_tracked_not_hidden(monkeypatch):
    monkeypatch.setitem(SCRIPT, "Não achei caro.", "PRICE_BUDGET")  # the classifier's known mistake
    monkeypatch.setitem(SCRIPT, "Mas preciso falar com ele antes de fechar.", "AUTHORITY_INTERNAL_BUY_IN")
    calls = ev.load_calls(ev.FIXTURES)
    _, _, m = _run(calls, annotations=em.load_annotations([ev.FIXTURES], []))
    status = {r["case"]: r["status"] for r in m["known_regressions"]}
    assert status["KR-NEGATED-PRICE"] == "KNOWN_FAILURE"
    assert status["KR-AUTHORITY-BLOCKER"] == "PASS"
    assert status["KR-STALE-AUTHORITY"] == "PASS"  # the AUTHORITY card never comes back
    assert m["confusion_report"]["NEGATION"] == 1
    monkeypatch.delitem(SCRIPT, "Não achei caro.")
    _, _, m = _run({"KR-NEGATED-PRICE": calls["KR-NEGATED-PRICE"]},
                   annotations=em.load_annotations([ev.FIXTURES], []))
    assert m["known_regressions"][0]["status"] == "UNEXPECTED_PASS"


def test_report_and_compare(tmp_path, monkeypatch):
    calls = {"m": _rows("m", [("closer", "O que achou?"), ("lead", PRICE), ("lead", TIMING)])}
    ann = [{"meeting_id": "m", "scope": {"objections": "COMPLETE"}},
           {"meeting_id": "m", "sequence": 2, "expected_objection": {"present": True, "category": "PRICE_BUDGET"}}]
    runs = []
    for label in ("baseline", "candidate"):
        if label == "candidate":
            monkeypatch.setitem(SCRIPT, TIMING, None)  # the "fix": no more false TIMING objection
        trace, sessions = ev.run(calls, FakeProvider(), LiveConfig())
        out = ev.new_run_dir(label, tmp_path)
        ev.write_run(out, label, calls, ann, trace, sessions, {"model": "fake"})
        runs.append(out)
    md = (runs[0] / "EVAL_REPORT.md").read_text(encoding="utf-8")
    for section in ("## Summary", "## Objections", "## Opportunities", "## Commercial State", "## Compliance",
                    "## Seller Actions", "## Latency", "## Top False Positives", "## Top False Negatives",
                    "## Known Failures", "## Sessions"):
        assert section in md
    assert len((runs[0] / "false_positives.jsonl").read_text(encoding="utf-8").splitlines()) == 1
    cmp = em.compare(*runs)
    assert "| objections.precision | 0.500 | 1.000 | 0.500 |" in cmp and "Warning" not in cmp
    assert ev.new_run_dir("baseline", tmp_path) != runs[0]  # never overwrites


def test_an_interrupted_run_keeps_finished_calls_and_can_be_rescored(tmp_path):
    src = tmp_path / "calls.jsonl"
    rows = _rows("a", [("closer", "O que achou?"), ("lead", PRICE)]) + _rows("b", [("lead", TIMING)])
    src.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    (tmp_path / "calls.annotations.jsonl").write_text(json.dumps(
        {"meeting_id": "a", "sequence": 2, "expected_objection": {"present": True, "category": "PRICE_BUDGET"}}) + "\n",
        encoding="utf-8")
    out = tmp_path / "run"
    out.mkdir()
    (out / "config.json").write_text(json.dumps({
        "label": "x", "status": "RUNNING", "model": "fake", "num_ctx": 4096, "fast_path": True,
        "commercial_facts": True, "gap_s": 6.0, "sample": 0, "seed": "v1", "inputs": [str(src)]}), encoding="utf-8")
    calls = ev.load_calls(src)
    ev.run({"a": calls["a"]}, FakeProvider(), LiveConfig(), out=out)  # "b" never ran (interrupted)
    assert ev.main(["--rescore", str(out)]) == 0
    cfg = json.loads((out / "config.json").read_text(encoding="utf-8"))
    m = json.loads((out / "metrics.json").read_text(encoding="utf-8"))
    assert cfg["not_replayed"] == ["b"] and cfg["calls"] == ["a"]
    assert (m["objections"]["tp"], m["objections"]["fn"]) == (1, 0)
    assert (out / "EVAL_REPORT.md").exists()
