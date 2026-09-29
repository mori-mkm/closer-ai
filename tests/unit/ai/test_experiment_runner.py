"""Experiment runner v0.1 tests. Scripted provider and synthetic Calls only; Git tests use a
throwaway repository under tmp_path (the real repository is never touched)."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest
from classifier_support import (
    PRICE_CALL_TEXTS,
    ScriptedClassificationProvider,
    episode,
    response,
    synthetic_call,
)

from closer_ai.ai import experiment_runner as er
from closer_ai.ai.experiment_runner import (
    ARTIFACT_VERSION,
    ExperimentSpec,
    KnowledgeGitError,
    knowledge_git_sha,
    result_to_dict,
    run_experiment,
    write_artifact,
)
from closer_ai.ai.knowledge_context import KnowledgeBaseError, build_knowledge_context
from closer_ai.ai.objection_classifier import MalformedResponseError, build_prompt, classify_call
from closer_ai.ai.ollama_provider import OllamaError

KB = Path(__file__).resolve().parents[3] / "docs" / "knowledge" / "sales" / "objections"
SHA = "a" * 40


class UsageProvider(ScriptedClassificationProvider):
    """Scripted provider that also reports per-call usage and a config, like the Ollama adapter."""

    def __init__(self, *responses, usages=()):
        super().__init__(*responses)
        self.config = {"temperature": 0, "num_ctx": 1024}
        self._usages = list(usages)
        self.last_usage = {}

    def classify(self, prompt):
        self.last_usage = self._usages.pop(0) if self._usages else {}
        return super().classify(prompt)


def valid(call):
    s = [seg.segment_id for seg in call.segments]
    return response(episode(objection_segment_ids=[s[1]], context_segment_ids=[s[2], s[3]]))


def invalid():
    return response(episode(objection_segment_ids=["not-a-segment"]))


def spec(**kw):
    return ExperimentSpec(**{"name": "exp-1", "knowledge_root": KB, "knowledge_git_sha": SHA, **kw})


# --- orchestration ----------------------------------------------------------------------------


def test_one_call_three_arms_in_canonical_order_same_provider():
    call = synthetic_call()
    provider = ScriptedClassificationProvider(valid(call), valid(call), valid(call))
    result = run_experiment(spec(arms=("E2", "E0", "E1")), [call], provider)
    assert [r.arm for r in result.runs] == ["E0", "E1", "E2"]
    assert result.spec.arms == ("E0", "E1", "E2")
    assert [r.status for r in result.runs] == ["SUCCESS_VALID"] * 3
    assert {(r.provider, r.model) for r in result.runs} == {("scripted", "test-model")}
    assert provider.prompts == [build_prompt(call, a, KB) for a in ("E0", "E1", "E2")]


def test_multiple_calls_run_in_call_order():
    a, b = synthetic_call(source_id="a"), synthetic_call(source_id="b")
    provider = ScriptedClassificationProvider(*[valid(a)] * 2, *[valid(b)] * 2)
    result = run_experiment(spec(arms=("E0", "E1")), [a, b], provider)
    assert [(r.call_id, r.arm) for r in result.runs] == [
        (a.call_id, "E0"), (a.call_id, "E1"), (b.call_id, "E0"), (b.call_id, "E1")]
    assert result.call_ids == (a.call_id, b.call_id)


def test_failures_are_recorded_and_the_experiment_continues():
    call = synthetic_call()
    provider = ScriptedClassificationProvider(
        OllamaError("Ollama HTTP 500: boom"), MalformedResponseError("model output is not JSON"), invalid())
    result = run_experiment(spec(), [call], provider)
    r0, r1, r2 = result.runs
    assert (r0.status, r0.failure_type, r0.failure_message) == ("PROVIDER_ERROR", "OllamaError", "Ollama HTTP 500: boom")
    assert (r1.status, r1.failure_type) == ("MALFORMED_RESPONSE", "MalformedResponseError")
    assert r2.status == "SUCCESS_INVALID_PREDICTION" and r2.validation_errors and r2.failure_type is None
    assert r2.prediction_count == 1  # recorded, never dropped
    for r in (r0, r1):  # the prompt was sent, so its digest is still known
        assert r.prompt_sha256 and r.call_detection is None and r.prediction_count == 0


def test_wrong_shape_from_classifier_parser_is_malformed():
    result = run_experiment(spec(arms=("E0",)), [synthetic_call()], ScriptedClassificationProvider({"x": 1}))
    assert result.runs[0].status == "MALFORMED_RESPONSE"


def test_summary_is_operational_counts_only():
    call = synthetic_call()
    provider = UsageProvider(valid(call), invalid(), OllamaError("down"),
                             usages=[{"prompt_eval_count": 10, "eval_count": 3}, {"prompt_eval_count": 20, "eval_count": 4}])
    summary = run_experiment(spec(), [call], provider).summary
    assert summary["planned_runs"] == summary["completed_runs"] == summary["runs"] == 3
    assert (summary["SUCCESS_VALID"], summary["SUCCESS_INVALID_PREDICTION"], summary["MALFORMED_RESPONSE"],
            summary["PROVIDER_ERROR"]) == (1, 1, 0, 1)
    assert summary["by_arm"]["E0"]["SUCCESS_VALID"] == 1
    assert summary["by_arm"]["E2"]["PROVIDER_ERROR"] == 1
    assert (summary["prompt_eval_count_total"], summary["eval_count_total"]) == (30, 7)
    assert not {"accuracy", "precision", "recall", "f1", "winner", "best_arm"} & {k.lower() for k in summary}


# --- global aborts ------------------------------------------------------------------------------


def test_invalid_knowledge_base_aborts_before_any_call(tmp_path):
    provider = ScriptedClassificationProvider()
    with pytest.raises(KnowledgeBaseError):
        run_experiment(spec(knowledge_root=tmp_path), [synthetic_call()], provider)
    assert provider.prompts == []


@pytest.mark.parametrize("fails", [False, True])
def test_knowledge_base_changed_mid_experiment_aborts(tmp_path, fails):
    kb = tmp_path / "kb"
    shutil.copytree(KB, kb)
    calls = [synthetic_call(source_id="a"), synthetic_call(source_id="b")]

    class Editing(ScriptedClassificationProvider):
        def classify(self, prompt):  # edits a rendered unit section after the prompt was built
            unit = kb / "PRICE_BUDGET.md"
            text = unit.read_text(encoding="utf-8")
            unit.write_text(text.replace("## Definition\n", "## Definition\n\nEdited.\n", 1), encoding="utf-8")
            if fails:  # detected even when no run succeeds
                raise OllamaError("down")
            return super().classify(prompt)

    with pytest.raises(RuntimeError, match="changed during the experiment"):
        run_experiment(spec(arms=("E2",), knowledge_root=kb), calls, Editing(*[valid(c) for c in calls]))


def test_unexpected_exception_is_not_hidden():
    class Buggy(ScriptedClassificationProvider):
        name = "buggy"

    call = synthetic_call()
    with pytest.raises(TypeError):
        run_experiment(spec(arms=("E0",)), [call.model_dump()], Buggy())  # not a Call


@pytest.mark.parametrize(
    "kw",
    [{"name": ""}, {"name": "../x"}, {"name": "a/b"}, {"arms": ()}, {"arms": ("E0", "E0")},
     {"arms": ("E3",)}, {"arms": ("e0",)}, {"knowledge_root": None}],
)
def test_bad_spec_rejected(kw):
    with pytest.raises(ValueError):
        run_experiment(spec(**kw), [synthetic_call()], ScriptedClassificationProvider())


def test_duplicate_or_empty_calls_rejected():
    call = synthetic_call()
    with pytest.raises(ValueError):
        run_experiment(spec(), [call, call], ScriptedClassificationProvider())
    with pytest.raises(TypeError):
        run_experiment(spec(), [], ScriptedClassificationProvider())


def test_e2_optional_when_not_in_arms():
    call = synthetic_call()
    result = run_experiment(spec(arms=("E0",), knowledge_root=None), [call], ScriptedClassificationProvider(valid(call)))
    assert result.knowledge_sha256 is None and result.runs[0].status == "SUCCESS_VALID"


# --- provenance -------------------------------------------------------------------------------


def test_provenance_per_arm():
    call = synthetic_call()
    usages = [{"prompt_eval_count": i, "eval_count": i + 1, "total_duration": 5} for i in (1, 2, 3)]
    provider = UsageProvider(valid(call), valid(call), valid(call), usages=usages)
    result = run_experiment(spec(), [call], provider)
    knowledge = build_knowledge_context(KB)
    assert result.provider_config == {"temperature": 0, "num_ctx": 1024}
    assert result.knowledge_sha256 == knowledge.sha256
    for r, arm, usage in zip(result.runs, ("E0", "E1", "E2"), usages, strict=True):
        prompt = build_prompt(call, arm, KB)
        assert r.prompt_sha256 == hashlib.sha256(prompt.encode()).hexdigest()
        assert (r.prompt_chars, r.prompt_utf8_bytes) == (len(prompt), len(prompt.encode()))
        assert r.usage == usage  # attributed to the run that produced it
        assert r.segment_sequence_hash == result.runs[0].segment_sequence_hash
        if arm == "E2":
            assert r.knowledge_sha256 == knowledge.sha256 and r.knowledge_git_sha == SHA
            assert r.knowledge_concept_versions == knowledge.concept_versions
        else:
            assert r.knowledge_sha256 is None and r.knowledge_git_sha is None and not r.knowledge_concept_versions


def test_usage_not_carried_over_from_a_previous_run():
    call = synthetic_call()
    provider = UsageProvider(valid(call), OllamaError("down"), usages=[{"eval_count": 9}])
    r0, r1 = run_experiment(spec(arms=("E0", "E1")), [call], provider).runs
    assert r0.usage == {"eval_count": 9} and r1.usage == {}


def test_timestamps_are_observational_only():
    call = synthetic_call()
    a = result_to_dict(run_experiment(spec(arms=("E0",)), [call], ScriptedClassificationProvider(valid(call))))
    b = result_to_dict(run_experiment(spec(arms=("E0",)), [call], ScriptedClassificationProvider(valid(call))))
    for d in (a, b):
        for key in ("started_at", "finished_at"):
            d.pop(key)
        d["summary"].pop("elapsed_seconds")
        for r in d["runs"]:
            r.pop("elapsed_seconds")
    assert a == b


# --- artifact ---------------------------------------------------------------------------------


def _result():
    call = synthetic_call()
    provider = ScriptedClassificationProvider(valid(call), invalid(), OllamaError("down"))
    return run_experiment(spec(), [call], provider)


def test_artifact_is_json_without_text_prompt_or_raw_response(tmp_path):
    result = _result()
    path = write_artifact(result, tmp_path / "experiments")
    assert path.name == "exp-1.json"
    raw = path.read_text(encoding="utf-8")
    data = json.loads(raw)
    assert data["artifact_version"] == ARTIFACT_VERSION == "v0.1"
    assert data["summary"]["SUCCESS_VALID"] == 1 and len(data["runs"]) == 3
    assert data["knowledge"]["git_sha"] == SHA and data["runs"][2]["knowledge_git_sha"] == SHA
    for _, text in PRICE_CALL_TEXTS:
        assert text not in raw
    assert "TASK RULES" not in raw and "FACTS FROM CALL" not in raw
    assert "raw_response" not in raw
    assert "summary" not in data["runs"][0]["predictions"][0]
    assert episode()["summary"] not in raw
    assert str(KB) not in raw and "knowledge_root" not in raw


def test_artifact_never_overwrites(tmp_path):
    result = _result()
    path = write_artifact(result, tmp_path)
    before = path.read_bytes()
    with pytest.raises(FileExistsError):
        write_artifact(result, tmp_path)
    assert path.read_bytes() == before


def test_artifact_write_failure_leaves_no_file(tmp_path, monkeypatch):
    def fail(*args):
        raise OSError("disk full")

    monkeypatch.setattr(er.os, "replace", fail)
    with pytest.raises(OSError):
        write_artifact(_result(), tmp_path)
    assert list(tmp_path.iterdir()) == []


# --- git --------------------------------------------------------------------------------------


@pytest.fixture
def repo(tmp_path, monkeypatch):
    if shutil.which("git") is None:
        pytest.skip("git not installed")
    empty = tmp_path / "gitconfig"
    empty.write_text("")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(empty))  # isolate from the user's git config
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    root = tmp_path / "repo"
    kb = root / "docs" / "knowledge" / "sales" / "objections"
    shutil.copytree(KB, kb)
    (root / "README.md").write_text("x\n")

    def git(*args):
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
                       cwd=root, check=True, capture_output=True)

    git("init", "-q")
    git("add", ".")
    git("commit", "-q", "-m", "init")
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=True).stdout.strip()
    return root, kb, head


def test_clean_knowledge_tree_returns_head_sha(repo):
    _, kb, head = repo
    assert knowledge_git_sha(kb) == head and len(head) == 40


def test_unrelated_changes_do_not_block(repo):
    root, kb, head = repo
    (root / "README.md").write_text("changed\n")
    runs = root / "docs" / "evals" / "calibration" / "runs"
    runs.mkdir(parents=True)
    (runs / "notes.md").write_text("human dry run\n")
    assert knowledge_git_sha(kb) == head


@pytest.mark.parametrize("change", ["modify", "untracked", "delete"])
def test_dirty_knowledge_tree_rejected(repo, change):
    _, kb, _ = repo
    unit = kb / "PRICE_BUDGET.md"
    if change == "modify":
        unit.write_text(unit.read_text(encoding="utf-8") + "\nedit\n", encoding="utf-8")
    elif change == "untracked":
        (kb / "NEW.md").write_text("x\n")
    else:
        unit.unlink()
    with pytest.raises(KnowledgeGitError, match="uncommitted"):
        knowledge_git_sha(kb)


def test_ignored_file_in_knowledge_tree_rejected(repo):
    root, kb, _ = repo
    (root / ".gitignore").write_text("*.md.bak\n")
    (kb / "PRICE_BUDGET.md.bak").write_text("x\n")
    with pytest.raises(KnowledgeGitError, match="uncommitted"):
        knowledge_git_sha(kb)


def test_not_a_repository_or_untracked_directory(tmp_path, repo):
    with pytest.raises(KnowledgeGitError):
        knowledge_git_sha(tmp_path / "missing")
    outside = tmp_path / "outside"
    outside.mkdir()
    with pytest.raises(KnowledgeGitError):
        knowledge_git_sha(outside)  # tmp_path itself is not a repository
    untracked = repo[0] / "docs" / "empty"
    untracked.mkdir()
    with pytest.raises(KnowledgeGitError, match="no tracked files"):
        knowledge_git_sha(untracked)


def test_git_unavailable_is_explicit(repo, monkeypatch):
    def missing(*args, **kwargs):
        raise FileNotFoundError("git")

    monkeypatch.setattr(er.subprocess, "run", missing)
    with pytest.raises(KnowledgeGitError, match="not available"):
        knowledge_git_sha(repo[1])


def test_git_runs_without_shell(repo, monkeypatch):
    calls = []
    real = subprocess.run

    def spy(args, **kwargs):
        calls.append((args, kwargs))
        return real(args, **kwargs)

    monkeypatch.setattr(er.subprocess, "run", spy)
    knowledge_git_sha(repo[1])
    assert calls and all(isinstance(a, list) and not k.get("shell") and k.get("timeout") for a, k in calls)


# --- redaction of model-produced values ---------------------------------------------------------

LEAK = "não temos verba para isso neste ano"  # transcript text a model might echo into any field


def test_model_echoed_text_never_reaches_the_record_or_artifact(tmp_path):
    call = synthetic_call()
    s = [seg.segment_id for seg in call.segments]
    bad = response(
        episode(prediction_id=LEAK, objection_segment_ids=[s[1], LEAK], category=LEAK + "!",
                reaction=LEAK + "?", resolution_status=LEAK + "."),
        episode(prediction_id="p2", objection_segment_ids=[s[3]], category_status=LEAK, category=None),
        call_detection=LEAK + ":",
        uncertain_spans=[{"segment_ids": [LEAK], "status": LEAK}],
    )
    provider = ScriptedClassificationProvider(bad, {LEAK: 1}, OllamaError("down"))
    result = run_experiment(spec(), [call], provider)
    raw = json.dumps(result_to_dict(result), ensure_ascii=False)
    assert "verba" not in raw and "verba" not in repr(result.runs)
    r0, r1, _ = result.runs
    assert r0.status == "SUCCESS_INVALID_PREDICTION" and r1.status == "MALFORMED_RESPONSE"
    assert "<unlisted" in r1.failure_message
    # same verdicts as the unredacted validation, different values stay different
    original = classify_call(call, "E0", ScriptedClassificationProvider(bad))
    assert len(r0.validation_errors) == len(original.validation_errors)
    assert r0.predictions[0]["objection_segment_ids"] == (s[1], r0.predictions[0]["prediction_id"])  # same value
    assert r0.predictions[0]["category"] != r0.predictions[0]["reaction"]


def test_known_values_are_kept_verbatim():
    call = synthetic_call()
    run = run_experiment(spec(arms=("E0",)), [call], ScriptedClassificationProvider(valid(call))).runs[0]
    p = run.predictions[0]
    assert (p["prediction_id"], p["category"], p["reaction"], p["resolution_status"]) == (
        "p1", "PRICE_BUDGET", "REJECT", "unresolved")
    assert run.call_detection == "OBJECTIONS_FOUND" and run.validation_errors == ()
