"""Long-call chunking (pilot orchestration), Ollama status mapping and BOM input. No real Ollama."""
from __future__ import annotations

import csv
import itertools
import re
import socket
import threading

import pytest

from closer_ai.ai.objection_classifier import (
    MalformedResponseError,
    build_prompt,
    render_call_facts,
)
from closer_ai.ai.objection_guidance import load_objection_knowledge
from closer_ai.ai.ollama_provider import OllamaClassificationProvider, OllamaError
from closer_ai.demo import analyze_call as cli
from closer_ai.demo.analyze_call import CLASSIFICATION_KB, GUIDANCE_KB, parse_transcript
from closer_ai.demo.long_call import _sub_call, analyze_call_auto, plan_chunks

_SEG = re.compile(r"\[(seg_\w+) \| (\w+)\]\n(.*)")
OBJECTION = "Olha, está caro pra mim e não tenho orçamento agora."
FINAL = "Vou pensar com calma e te retorno."


@pytest.fixture(scope="module")
def kb():
    return load_objection_knowledge(GUIDANCE_KB)


def _transcript(n: int, objection_at: int | None = None) -> str:
    lines = []
    for i in range(n):
        if i == objection_at:
            lines.append(f"lead: {OBJECTION}")
        elif i == n - 1:
            lines.append(f"lead: {FINAL}")
        elif i % 2 == 0:
            lines.append(f"closer: Pergunta {i} sobre como funciona o processo comercial da empresa hoje?")
        else:
            lines.append(f"lead: Resposta {i}: cada vendedor faz de um jeito e perdemos oportunidades.")
    return "\n".join(lines) + "\n"


def _call(n: int, objection_at: int | None = None):
    return parse_transcript(_transcript(n, objection_at), f"long_{n}_{objection_at}")


def _budget(call, segments_per_chunk: int) -> int:
    """A max_prompt_chars that fits roughly `segments_per_chunk` utterances of this synthetic call."""
    fixed = len(build_prompt(call, "E2", CLASSIFICATION_KB)) - len(render_call_facts(call)) + len("FACTS FROM CALL")
    biggest = max(len(f"\n[{s.segment_id} | lead]\n{s.text}") + 1 for s in call.segments)
    return fixed + segments_per_chunk * biggest


class ChunkFake:
    """Answers every stage from the segments it finds in the prompt itself (works for any chunk)."""

    name, model = "fake", "fake-1"

    def __init__(self, *, invalid_chunk_with: str | None = None, raise_chunk_with: str | None = None):
        self.invalid_chunk_with, self.raise_chunk_with = invalid_chunk_with, raise_chunk_with
        self.headers: list[str] = []

    def classify(self, prompt: str):
        header = prompt.split("\n", 1)[0]
        self.headers.append(header)
        segs = _SEG.findall(prompt)
        if header == "TASK RULES":
            texts = " ".join(t for _, _, t in segs)
            if self.raise_chunk_with and self.raise_chunk_with in texts:
                raise MalformedResponseError("model output is not JSON")
            episodes = []
            for i, (sid, role, text) in enumerate(segs):
                if role == "lead" and text == OBJECTION and i + 1 < len(segs):  # needs context after it
                    episodes.append(self._episode(f"p{len(episodes) + 1}", sid, segs[i + 1][0]))
            if self.invalid_chunk_with and self.invalid_chunk_with in texts:
                closer = next(sid for sid, role, _ in segs if role == "closer")
                episodes.append(self._episode("bad", closer, segs[-1][0]))  # closer anchor: invalid
            return {"call_detection": "OBJECTIONS_FOUND" if episodes else "NO_OBJECTION",
                    "episodes": episodes, "uncertain_spans": []}
        if header == "GUIDANCE TASK":
            category = re.search(r"Objection category \(classifier\): (\w+)", prompt).group(1)
            return {"move_id": f"{category}.M2", "rationale": "A lead levantou essa barreira na call.",
                    "suggested_question": "O que precisaria acontecer para avançar?",
                    "evidence_segment_ids": [segs[0][0]]}
        lead = [(sid, text) for sid, role, text in segs if role == "lead"]
        is_last = any(text == FINAL for _, text in lead)
        steps = [{"owner": "lead", "action": "pensar com calma e retornar", "due_date": None,
                  "segment_ids": [sid]} for sid, text in lead if text == FINAL]
        return {"lead_end_position": {"value": "DEFERRED" if is_last else "CONSIDERING",
                                      "segment_ids": [lead[-1][0]]},
                "stakeholders": [], "next_steps": steps}

    @staticmethod
    def _episode(pid, anchor, context):
        return {"prediction_id": pid, "objection_segment_ids": [anchor], "context_segment_ids": [context],
                "category_status": "PRESENT", "category": "PRICE_BUDGET", "category_candidates": [],
                "reaction_status": "ABSENT", "reaction": None, "reaction_candidates": [],
                "resolution_status": "unknown", "summary": "Preço."}


# 1-5: planning


def test_short_call_uses_single_context(kb):
    call = _call(10, objection_at=3)
    fake = ChunkFake()
    pci = analyze_call_auto(call, fake, CLASSIFICATION_KB, kb, max_prompt_chars=10**6)
    assert pci.provenance["processing_mode"] == "single_context" and pci.provenance["chunk_count"] == 1
    assert pci.provenance["segments_processed"] == pci.provenance["segment_count"] == 10
    assert fake.headers.count("TASK RULES") == 1 and pci.pipeline_status == "SUCCESS"


def test_long_call_is_split_and_every_chunk_fits(kb):
    call = _call(60, objection_at=21)
    budget = _budget(call, 12)
    plan = plan_chunks(call, "E2", CLASSIFICATION_KB, budget)
    assert len(plan) > 1
    for start, end in plan:
        assert len(build_prompt(_sub_call(call, start, end), "E2", CLASSIFICATION_KB)) <= budget
    pci = analyze_call_auto(call, ChunkFake(), CLASSIFICATION_KB, kb, max_prompt_chars=budget)
    assert pci.provenance["processing_mode"] == "chunked"
    assert pci.provenance["chunk_count"] == len(plan) and pci.pipeline_status == "SUCCESS"


def test_no_utterance_is_split_and_identity_is_preserved():
    call = _call(60)
    by_id = {s.segment_id: s for s in call.segments}
    for start, end in plan_chunks(call, "E2", CLASSIFICATION_KB, _budget(call, 12)):
        chunk = _sub_call(call, start, end)
        assert chunk.call_id == call.call_id and chunk.participants == call.participants
        for s in chunk.segments:
            original = by_id[s.segment_id]
            assert (s.text, s.speaker_id) == (original.text, original.speaker_id)


def test_segment_order_is_preserved_within_and_across_chunks():
    call = _call(60)
    plan = plan_chunks(call, "E2", CLASSIFICATION_KB, _budget(call, 12))
    assert [p[0] for p in plan] == sorted(p[0] for p in plan) and plan[0][0] == 0
    index = {s.segment_id: s.segment_index for s in call.segments}
    for start, end in plan:
        chunk = _sub_call(call, start, end)
        assert [index[s.segment_id] for s in chunk.segments] == list(range(start, end))
        assert [s.segment_index for s in chunk.segments] == list(range(end - start))


def test_every_segment_is_in_at_least_one_chunk_with_small_overlap():
    call = _call(61)
    plan = plan_chunks(call, "E2", CLASSIFICATION_KB, _budget(call, 12))
    assert set().union(*(range(s, e) for s, e in plan)) == set(range(61))
    assert plan[-1][1] == 61
    for (_, prev_end), (next_start, _) in itertools.pairwise(plan):
        assert prev_end - next_start == 2  # overlap of 2 utterances


def test_single_utterance_too_large_is_input_too_large():
    call = _call(4)
    with pytest.raises(cli.ChunkTooLargeError, match="never split"):
        plan_chunks(call, "E2", CLASSIFICATION_KB, _budget(call, 0))
    assert cli.failure_status(cli.ChunkTooLargeError("x")) == "INPUT_TOO_LARGE"


# 6-9: merge and fail closed


def test_objection_on_a_chunk_boundary_is_detected(kb):
    call = _call(60)
    plan = plan_chunks(call, "E2", CLASSIFICATION_KB, _budget(call, 12))
    boundary = plan[0][1] - 1  # last utterance of the first chunk: no context after it in that chunk
    if boundary % 2 == 0:
        boundary -= 1  # keep it a lead line
    call = _call(60, objection_at=boundary)
    plan = plan_chunks(call, "E2", CLASSIFICATION_KB, _budget(call, 12))
    assert plan[0][1] - 1 in (boundary, boundary + 1)
    pci = analyze_call_auto(call, ChunkFake(), CLASSIFICATION_KB, kb, max_prompt_chars=_budget(call, 12))
    assert [o.category for o in pci.objections] == ["PRICE_BUDGET"]
    assert pci.objections[0].evidence[0].text == OBJECTION


def test_overlap_duplicate_is_merged_into_one_episode(kb):
    budget = _budget(_call(60), 12)

    def seen_with_context(at):  # chunks in which the objection has an utterance after it
        plan = plan_chunks(_call(60, objection_at=at), "E2", CLASSIFICATION_KB, budget)
        return sum(s <= at < e - 1 for s, e in plan)

    at = next(i for i in range(1, 59) if seen_with_context(i) == 2)  # inside an overlap
    call = _call(60, objection_at=at)
    pci = analyze_call_auto(call, ChunkFake(), CLASSIFICATION_KB, kb, max_prompt_chars=budget)
    assert len(pci.objections) == 1 and len(pci.commercial_guidance) == 1
    [chunks] = pci.provenance["episode_chunks"].values()
    assert len(chunks) == 2
    assert len(pci.next_steps) == 1  # the final step, also not duplicated


def test_invalid_chunk_prevents_success(kb):
    call = _call(60, objection_at=21)
    pci = analyze_call_auto(call, ChunkFake(invalid_chunk_with="Pergunta 30 "), CLASSIFICATION_KB, kb,
                            max_prompt_chars=_budget(call, 12))
    assert pci.pipeline_status == "INVALID"
    assert any(e.startswith("chunk ") and "classifier" in e for e in pci.errors)


def test_failing_chunk_yields_no_output(kb):
    call = _call(60, objection_at=21)
    with pytest.raises(MalformedResponseError):
        analyze_call_auto(call, ChunkFake(raise_chunk_with="Pergunta 40 "), CLASSIFICATION_KB, kb,
                          max_prompt_chars=_budget(call, 12))


def test_lead_end_position_comes_from_the_last_chunk(kb):
    call = _call(60, objection_at=21)
    pci = analyze_call_auto(call, ChunkFake(), CLASSIFICATION_KB, kb, max_prompt_chars=_budget(call, 12))
    assert pci.provenance["chunk_count"] > 2
    assert pci.lead_end_position.value == "DEFERRED"  # earlier chunks said CONSIDERING
    assert pci.lead_end_position.evidence[0].text == FINAL
    assert pci.provenance["lead_end_position_chunk"] == pci.provenance["chunk_count"] - 1


# 10: BOM; 11-12: Ollama statuses


class FakeOllama(ChunkFake):
    def __init__(self, model, base_url, num_ctx):
        super().__init__()
        self.last_usage = {}


def test_utf8_bom_file_is_read_and_sheet_has_processing_columns(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "OllamaClassificationProvider", FakeOllama)
    calls = tmp_path / "calls"
    calls.mkdir()
    (calls / "bom.txt").write_bytes(b"\xef\xbb\xbf" + _transcript(8, objection_at=3).encode("utf-8"))
    out = tmp_path / "out"
    assert cli.main([str(calls), "--out-dir", str(out)]) == 0
    assert "SUCCESS  bom.txt [single_context, 1 chunk(s)" in capsys.readouterr().err
    with (out / "review_sheet.csv").open(encoding="utf-8-sig", newline="") as f:
        [row] = list(csv.DictReader(f))
    assert (row["pipeline_status"], row["processing_mode"], row["chunk_count"]) == ("SUCCESS", "single_context", "1")


def test_timeout_is_ollama_timeout_not_unreachable():
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    accepted = []
    threading.Thread(target=lambda: accepted.append(server.accept()), daemon=True).start()
    provider = OllamaClassificationProvider("m", base_url=f"http://127.0.0.1:{server.getsockname()[1]}",
                                            timeout=0.3)
    with pytest.raises(OllamaError) as info:
        provider.classify("x")  # connection accepted, never answered
    server.close()
    assert cli.failure_status(info.value) == "OLLAMA_TIMEOUT"


def test_closed_port_is_ollama_unreachable():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()  # nothing listens here now
    with pytest.raises(OllamaError) as info:
        OllamaClassificationProvider("m", base_url=f"http://127.0.0.1:{port}", timeout=10).classify("x")
    assert cli.failure_status(info.value) == "OLLAMA_UNREACHABLE"
    assert cli.failure_status(ValueError("parse")) == "ERROR"
