"""Synthetic call -> objection -> knowledge retrieval -> commercial guidance -> next steps/risks.

Fake provider routed by prompt header; no Ollama, no network. Inputs are the demo transcripts in
examples/calls/ (synthetic).
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from closer_ai.ai.objection_guidance import load_objection_knowledge
from closer_ai.ai.post_call import analyze_call, render_markdown
from closer_ai.demo import analyze_call as cli
from closer_ai.demo.analyze_call import CLASSIFICATION_KB, GUIDANCE_KB, parse_transcript

EXAMPLES = Path(__file__).resolve().parents[2] / "examples" / "calls"

# example file -> (category, objection segment indexes, chosen move, next step owner/action/due/segment)
CASES = {
    "authority_partner": ("AUTHORITY_INTERNAL_BUY_IN", [5], "AUTHORITY_INTERNAL_BUY_IN.M1",
                          ("lead", "conversar com o sócio", None, 9)),
    "price_budget": ("PRICE_BUDGET", [1], "PRICE_BUDGET.M3",
                     ("closer", "enviar simulação", "quinta-feira", 6)),
    "timing_priority": ("TIMING_PRIORITY", [3], "TIMING_PRIORITY.M3",
                        ("closer", "ligar para retomar", "primeira semana de abril", 6)),
}


@pytest.fixture(scope="module")
def kb():
    return load_objection_knowledge(GUIDANCE_KB)


def _call(name: str):
    return parse_transcript((EXAMPLES / f"{name}.txt").read_text(encoding="utf-8"), name)


def _episode(call, category, indexes, resolution="unknown"):
    return {
        "prediction_id": "p1",
        "objection_segment_ids": [call.segments[i].segment_id for i in indexes],
        "context_segment_ids": [call.segments[indexes[-1] + 1].segment_id],
        "category_status": "PRESENT", "category": category, "category_candidates": [],
        "reaction_status": "ABSENT", "reaction": None, "reaction_candidates": [],
        "resolution_status": resolution, "summary": "Objeção sintética.",
    }


class RoutedProvider:
    """Answers each pipeline stage by the prompt's first line."""

    name = "fake"
    model = "fake-1"

    def __init__(self, classification, guidance, post_call):
        self.by_header = {"TASK RULES": classification, "GUIDANCE TASK": guidance, "POST-CALL TASK": post_call}
        self.headers: list[str] = []

    def classify(self, prompt):
        header = prompt.split("\n", 1)[0]
        self.headers.append(header)
        return self.by_header[header]


def _provider(call, name, *, steps=None, stakeholders=(), detection="OBJECTIONS_FOUND", episodes=None):
    category, indexes, move, (owner, action, due, step_i) = CASES[name]
    seg = [s.segment_id for s in call.segments]
    if episodes is None:
        episodes = [_episode(call, category, indexes)]
    return RoutedProvider(
        classification={"call_detection": detection, "episodes": episodes, "uncertain_spans": []},
        guidance={"move_id": move, "rationale": "O lead disse isso na call.",
                  "suggested_question": "O que precisaria ser verdade pra avançar?",
                  "evidence_segment_ids": [seg[indexes[0]]]},
        post_call={
            "lead_end_position": {"value": "CONSIDERING", "segment_ids": [seg[-1]]},
            "stakeholders": list(stakeholders),
            "next_steps": steps if steps is not None else [
                {"owner": owner, "action": action, "due_date": due, "segment_ids": [seg[step_i]]}],
        },
    )


@pytest.mark.parametrize("name", list(CASES))
def test_end_to_end_objection_to_grounded_guidance(kb, name):
    call = _call(name)
    category, indexes, move, (owner, action, due, step_i) = CASES[name]
    provider = _provider(call, name)
    pci = analyze_call(call, provider, CLASSIFICATION_KB, kb)

    assert provider.headers == ["TASK RULES", "GUIDANCE TASK", "POST-CALL TASK"]
    assert not pci.errors, pci.errors
    [objection] = pci.objections
    assert objection.category == category
    assert objection.evidence[0].text == call.segments[indexes[0]].text

    [g] = pci.commercial_guidance
    unit = kb.retrieve(category)
    assert g.status == "GUIDED" and g.recommended_move in unit.recommended_moves
    assert g.recommended_move.id == move and g.knowledge_grade == unit.move(move).evidence_grade
    assert g.avoid == unit.do_not

    [step] = pci.next_steps
    assert (step.owner, step.action, step.due_date) == (owner, action, due)
    assert step.evidence[0].text == call.segments[step_i].text
    assert pci.provenance["classifier_arm"] == "E2"
    assert pci.provenance["guidance_knowledge_sha256"] == kb.sha256

    md = render_markdown(pci)
    assert category in md and call.segments[indexes[0]].text in md
    assert g.generated_guidance.suggested_question in md and unit.do_not[0].guidance in md
    assert ("data não definida" in md) == (due is None)
    json.loads(pci.to_json())


def test_next_step_without_date_and_stakeholder_become_risks(kb):
    call = _call("authority_partner")
    seg = [s.segment_id for s in call.segments]
    provider = _provider(call, "authority_partner", stakeholders=[{"who": "sócio", "segment_ids": [seg[5]]}])
    pci = analyze_call(call, provider, CLASSIFICATION_KB, kb)
    codes = [r.code for r in pci.risks]
    assert codes == ["NEXT_STEP_WITHOUT_DATE", "OPEN_OBJECTION", "DECISION_STAKEHOLDER_ABSENT"]
    assert pci.next_steps[0].due_date is None
    assert pci.stakeholders[0].who == "sócio"


def test_due_date_must_be_stated_in_the_cited_segments(kb):
    call = _call("authority_partner")
    seg = [s.segment_id for s in call.segments]
    steps = [{"owner": "lead", "action": "falar com o sócio", "due_date": "amanhã", "segment_ids": [seg[9]]}]
    pci = analyze_call(call, _provider(call, "authority_partner", steps=steps), CLASSIFICATION_KB, kb)
    assert pci.next_steps == ()
    assert any("due_date 'amanhã' is not stated" in e for e in pci.errors)
    assert "NO_CLEAR_NEXT_STEP" in [r.code for r in pci.risks]


def test_post_call_ids_outside_the_call_are_rejected(kb):
    call = _call("price_budget")
    steps = [{"owner": "closer", "action": "x", "due_date": None, "segment_ids": ["seg-invented"]}]
    pci = analyze_call(call, _provider(call, "price_budget", steps=steps), CLASSIFICATION_KB, kb)
    assert pci.next_steps == () and any("not in this call" in e for e in pci.errors)


def test_invalid_classifier_run_yields_no_guidance(kb):
    call = _call("price_budget")
    closer_anchor = _episode(call, "PRICE_BUDGET", [0])  # segment 0 is the closer: invalid anchor
    provider = _provider(call, "price_budget", episodes=[closer_anchor])
    pci = analyze_call(call, provider, CLASSIFICATION_KB, kb)
    assert pci.objections == () and pci.commercial_guidance == ()
    assert any(e.startswith("classifier:") and "not spoken by a lead" in e for e in pci.errors)
    assert "GUIDANCE TASK" not in provider.headers


def test_no_objection_call(kb):
    call = _call("price_budget")
    provider = _provider(call, "price_budget", detection="NO_OBJECTION", episodes=[])
    pci = analyze_call(call, provider, CLASSIFICATION_KB, kb)
    assert pci.objections == () and not pci.errors
    assert "Nenhuma objeção registrada (classifier: NO_OBJECTION)" in render_markdown(pci)


def test_parse_transcript_rejects_unknown_roles():
    with pytest.raises(ValueError, match="line 2"):
        parse_transcript("lead: oi\ncliente: tá caro\n", "x")
    with pytest.raises(ValueError, match="no utterances"):
        parse_transcript("# only a comment\n", "x")
    call = parse_transcript("# c\ncloser: oi\n\nlead: oi\n", "x")
    assert [p.role for p in call.participants] == ["closer", "lead"]
    assert "synthetic_timestamps" in call.quality_flags


def test_parse_transcript_maps_speaker_labels_with_roles():
    roles = cli.parse_roles("Renato Silva=lead, Ana=closer")
    call = parse_transcript("Ana: Bom dia.\nRenato Silva: Está caro.\n", "x", roles=roles)
    assert {p.id: p.role for p in call.participants} == {"ana": "closer", "renato silva": "lead"}
    with pytest.raises(ValueError, match="'joao'"):
        parse_transcript("Joao: oi\n", "x", roles=roles)  # unmapped label: error, never a guess
    with pytest.raises(ValueError, match="--roles"):
        cli.parse_roles("Ana=buyer")


# --- next-step grounding ----------------------------------------------------------------------


def _steps_pci(kb, name, step):
    call = _call(name)
    return call, analyze_call(call, _provider(call, name, steps=[step]), CLASSIFICATION_KB, kb)


def test_due_date_absent_from_the_call_stays_null(kb):
    call = _call("authority_partner")
    step = {"owner": "lead", "action": "conversar com o sócio", "due_date": None,
            "segment_ids": [call.segments[9].segment_id]}
    _, pci = _steps_pci(kb, "authority_partner", step)
    assert pci.next_steps[0].due_date is None and not pci.errors


def test_invented_due_date_rejects_the_step(kb):
    call = _call("authority_partner")
    step = {"owner": "lead", "action": "conversar com o sócio", "due_date": "sexta-feira",
            "segment_ids": [call.segments[9].segment_id]}
    _, pci = _steps_pci(kb, "authority_partner", step)
    assert pci.next_steps == () and any("not stated in the cited segments" in e for e in pci.errors)


def test_vague_timing_is_not_a_due_date(kb):
    call = parse_transcript("closer: Fechamos?\nlead: Está caro.\ncloser: Certo.\n"
                            "lead: Depois eu te ligo.\n", "vague")
    seg = [s.segment_id for s in call.segments]
    provider = RoutedProvider(
        classification={"call_detection": "OBJECTIONS_FOUND", "uncertain_spans": [],
                        "episodes": [_episode(call, "PRICE_BUDGET", [1])]},
        guidance={"move_id": "PRICE_BUDGET.M2", "rationale": "Disse que está caro.",
                  "suggested_question": "Caro em relação a quê?", "evidence_segment_ids": [seg[1]]},
        post_call={"lead_end_position": {"value": "DEFERRED", "segment_ids": [seg[3]]}, "stakeholders": [],
                   "next_steps": [{"owner": "lead", "action": "ligar", "due_date": "Depois",
                                   "segment_ids": [seg[3]]}]},
    )
    pci = analyze_call(call, provider, CLASSIFICATION_KB, kb)
    assert pci.next_steps == () and any("is not a date or deadline" in e for e in pci.errors)
    assert pci.lead_end_position.value == "DEFERRED"
    assert "NO_CLEAR_NEXT_STEP" in [r.code for r in pci.risks]


@pytest.mark.parametrize("owner, action, needle", [
    ("closer", "conversar com o sócio", "owner 'closer' spoke none"),       # only the lead spoke it
    ("both", "conversar com o sócio", "owner 'both' needs"),
    ("lead", "assinar o contrato", "shares no word"),                        # not supported by the call
    ("lead", "conversar com o CFO", "ungrounded stakeholder"),
])
def test_next_step_owner_and_action_must_be_grounded(kb, owner, action, needle):
    call = _call("authority_partner")
    step = {"owner": owner, "action": action, "due_date": None, "segment_ids": [call.segments[9].segment_id]}
    _, pci = _steps_pci(kb, "authority_partner", step)
    assert pci.next_steps == () and any(needle in e for e in pci.errors), pci.errors
    assert pci.pipeline_status == "INVALID"


# --- CLI / pilot runner -----------------------------------------------------------------------


class ByCallProvider:
    """Routes each prompt to the matching example call's fake, by the segment ids it contains."""

    name = "fake"

    def __init__(self, model, base_url, num_ctx):
        self.model = model
        self.last_usage = {}
        self.fakes = [(_call(n), _provider(_call(n), n)) for n in CASES]

    def classify(self, prompt):
        for c, fake in self.fakes:
            if any(s.segment_id in prompt for s in c.segments):
                return fake.classify(prompt)
        raise AssertionError("prompt matches no example call")


def _calls_dir(tmp_path):
    calls_dir = tmp_path / "calls"
    calls_dir.mkdir()
    for name in ("price_budget", "timing_priority"):
        (calls_dir / f"{name}.txt").write_text((EXAMPLES / f"{name}.txt").read_text(encoding="utf-8"),
                                               encoding="utf-8")
    (calls_dir / "broken.txt").write_text("cliente: sem papel válido\n", encoding="utf-8")  # sorts first
    return calls_dir


def test_cli_batch_continue_on_error_writes_outputs_review_sheet_and_summary(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "OllamaClassificationProvider", ByCallProvider)
    out = tmp_path / "out"
    code = cli.main([str(_calls_dir(tmp_path)), "--out-dir", str(out), "--continue-on-error"])

    assert code == 1  # one ERROR
    err = capsys.readouterr().err
    assert "ERROR    broken.txt" in err and "summary: SUCCESS=2 INVALID=0 INPUT_TOO_LARGE=0 OLLAMA_TIMEOUT=0 OLLAMA_UNREACHABLE=0 ERROR=1" in err
    for name in ("price_budget", "timing_priority"):
        data = json.loads((out / f"{name}.json").read_text(encoding="utf-8"))
        assert data["commercial_guidance"][0]["status"] == "GUIDED"
        assert CASES[name][0] in (out / f"{name}.md").read_text(encoding="utf-8")
    assert not (out / "broken.json").exists()

    with (out / "review_sheet.csv").open(encoding="utf-8-sig", newline="") as f:
        rows = {r["source_file"]: r for r in csv.DictReader(f)}
    assert tuple(rows["price_budget.txt"]) == cli.REVIEW_COLUMNS
    price = rows["price_budget.txt"]
    assert (price["detected_category"], price["recommended_move"], price["knowledge_grade"],
            price["next_step_detected"], price["pipeline_status"]) == (
        "PRICE_BUDGET", "PRICE_BUDGET.M3", "WEAK", "yes", "SUCCESS")
    assert int(price["risk_count"]) >= 1
    assert rows["broken.txt"]["pipeline_status"] == "ERROR"
    assert all(r[c] == "" for r in rows.values() for c in cli.REVIEW_COLUMNS if c.startswith("human_"))


def test_cli_stops_at_first_error_by_default(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "OllamaClassificationProvider", ByCallProvider)
    out = tmp_path / "out"
    assert cli.main([str(_calls_dir(tmp_path)), "--out-dir", str(out)]) == 1
    assert "ERROR=1 NOT_RUN=2" in capsys.readouterr().err
    assert not (out / "price_budget.json").exists()


def test_cli_refuses_an_out_dir_inside_the_repository(monkeypatch):
    monkeypatch.setattr(cli, "OllamaClassificationProvider", ByCallProvider)
    with pytest.raises(SystemExit):
        cli.main([str(EXAMPLES), "--out-dir", str(EXAMPLES.parent / "pilot_out")])
    assert not (EXAMPLES.parent / "pilot_out").exists()


# --- no silent truncation ---------------------------------------------------------------------


class _Echo:
    name, model = "fake", "fake-1"

    def __init__(self, reported_tokens=None):
        self.calls = 0
        self.last_usage = {} if reported_tokens is None else {"prompt_eval_count": reported_tokens}

    def classify(self, prompt):
        self.calls += 1
        return {"ok": True}


def test_context_guard_refuses_before_sending_a_prompt_that_may_not_fit():
    inner = _Echo()
    guard = cli.ContextGuard(inner, num_ctx=4096)  # budget 2048 tokens ~ 5120 chars at 2.5 chars/token
    assert guard.classify("x" * 5000) == {"ok": True}
    with pytest.raises(cli.InputTooLargeError, match="nothing truncated"):
        guard.classify("x" * 5200)
    assert inner.calls == 1  # the oversized prompt never reached the model


def test_context_guard_discards_output_when_the_model_reports_a_full_context():
    guard = cli.ContextGuard(_Echo(reported_tokens=4000), num_ctx=4096)
    with pytest.raises(cli.InputTooLargeError, match="possible truncation"):
        guard.classify("short prompt")


def test_cli_reports_input_too_large_in_summary_and_review_sheet(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "OllamaClassificationProvider", ByCallProvider)
    calls_dir = tmp_path / "calls"
    calls_dir.mkdir()
    (calls_dir / "price_budget.txt").write_text((EXAMPLES / "price_budget.txt").read_text(encoding="utf-8"),
                                                encoding="utf-8")
    out = tmp_path / "out"
    # The E2 classifier prompt alone is ~24k chars: it cannot fit an 8k context.
    assert cli.main([str(calls_dir), "--out-dir", str(out), "--num-ctx", "8192", "--continue-on-error"]) == 1
    err = capsys.readouterr().err
    assert "INPUT_TOO_LARGE price_budget.txt" in err and "INPUT_TOO_LARGE=1" in err
    assert not (out / "price_budget.json").exists() and not (out / "price_budget.md").exists()
    with (out / "review_sheet.csv").open(encoding="utf-8-sig", newline="") as f:
        [row] = list(csv.DictReader(f))
    assert row["pipeline_status"] == "INPUT_TOO_LARGE"


def test_parse_transcript_preserves_order_attribution_and_text():
    text = "Ana: Bom dia: tudo certo?\nRenato: Tá caro.\nAna:  Entendo.  \nRenato: Não sei...\n"
    call = parse_transcript(text, "x", roles=cli.parse_roles("Ana=closer,Renato=lead"))
    assert [(s.speaker_id, s.text) for s in call.segments] == [
        ("ana", "Bom dia: tudo certo?"), ("renato", "Tá caro."), ("ana", "Entendo."), ("renato", "Não sei..."),
    ]
    assert [s.segment_index for s in call.segments] == [0, 1, 2, 3]
