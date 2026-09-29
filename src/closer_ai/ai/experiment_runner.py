"""Experiment runner / run orchestration v0.1: Calls × arms × one provider -> run records.

See docs/ai/EXPERIMENT_RUNNER_V0_1.md. Orchestration only: every classification goes through
`objection_classifier.classify_call`; this module never builds prompts, picks labels or judges
predictions. It records operational outcomes (compliance), not quality — there is no gold here.

- Sequential and single-threaded. Provider usage is read right after each call through a per-run
  wrapper, so it is attributed to the run that produced it.
- A failure in one Call × arm is recorded and the experiment continues. Global problems (bad spec,
  invalid Knowledge Base, Knowledge Base changing mid-experiment) raise and abort.
- Artifacts are privacy-first: ids, digests, structured labels and operational metadata only — no
  transcript text, prompt, raw model response or free-text summary.
- Git is used only here (`knowledge_git_sha`), never by the classifier or the context builder.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
import time
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, fields, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from closer_ai.ai.knowledge_context import build_knowledge_context
from closer_ai.ai.objection_classifier import (
    ARMS,
    CALL_DETECTIONS,
    CATEGORY_LABELS,
    CATEGORY_STATUSES,
    REACTION_LABELS,
    REACTION_STATUSES,
    RESOLUTION_STATUSES,
    SPAN_STATUSES,
    ClassificationProvider,
    ClassificationRun,
    EpisodePrediction,
    MalformedResponseError,
    UncertainSpan,
    classify_call,
    segment_sequence_hash,
    validate_predictions,
)
from closer_ai.normalization.models import Call

ARTIFACT_VERSION = "v0.1"
STATUSES: tuple[str, ...] = (
    "SUCCESS_VALID",               # parseable and valid against the Call
    "SUCCESS_INVALID_PREDICTION",  # parseable, but breaks validation rules (validation_errors)
    "MALFORMED_RESPONSE",          # model output not JSON / wrong shape (MalformedResponseError)
    "PROVIDER_ERROR",              # the provider raised anything else (transport, API, timeout)
)
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


class KnowledgeGitError(RuntimeError):
    """Git unavailable, not a repository, Knowledge Base untracked, or Knowledge Base dirty."""


@dataclass(frozen=True)
class ExperimentSpec:
    name: str
    arms: tuple[str, ...] = ARMS
    knowledge_root: Path | None = None  # required when E2 is in arms
    knowledge_git_sha: str | None = None  # from knowledge_git_sha(); recorded, never computed here


@dataclass(frozen=True)
class ExperimentRunRecord:
    call_id: str
    segment_sequence_hash: str
    arm: str
    status: str
    failure_type: str | None
    failure_message: str | None
    provider: str
    model: str
    prompt_sha256: str | None  # None only if the provider was never called
    prompt_chars: int | None
    prompt_utf8_bytes: int | None
    knowledge_sha256: str | None  # E2 only
    knowledge_concept_versions: tuple[tuple[str, str], ...]  # E2 only
    knowledge_git_sha: str | None  # E2 only
    usage: Mapping[str, Any]  # provider-reported, observational (e.g. prompt_eval_count, eval_count)
    elapsed_seconds: float  # observational
    call_detection: str | None
    predictions: tuple[dict[str, Any], ...]  # structured labels + segment ids; no free text
    uncertain_spans: tuple[dict[str, Any], ...]
    validation_errors: tuple[str, ...]

    @property
    def prediction_count(self) -> int:
        return len(self.predictions)


@dataclass(frozen=True)
class ExperimentResult:
    spec: ExperimentSpec
    call_ids: tuple[str, ...]
    provider: str
    model: str
    provider_config: Mapping[str, Any]
    knowledge_sha256: str | None
    knowledge_concept_versions: tuple[tuple[str, str], ...]
    started_at: str  # UTC ISO, observational
    finished_at: str
    runs: tuple[ExperimentRunRecord, ...]

    @property
    def summary(self) -> dict[str, Any]:
        """Operational counts only (no accuracy: there is no gold in this layer)."""

        def counts(runs: Sequence[ExperimentRunRecord]) -> dict[str, int]:
            by_status = Counter(r.status for r in runs)
            return {"runs": len(runs), **{s: by_status[s] for s in STATUSES}}

        def usage_total(key: str) -> int | None:
            values = [r.usage[key] for r in self.runs if isinstance(r.usage.get(key), int)]
            return sum(values) if values else None

        return {
            "planned_runs": len(self.call_ids) * len(self.spec.arms),
            "completed_runs": len(self.runs),
            **counts(self.runs),
            "by_arm": {a: counts([r for r in self.runs if r.arm == a]) for a in self.spec.arms},
            "elapsed_seconds": round(sum(r.elapsed_seconds for r in self.runs), 3),
            "prompt_eval_count_total": usage_total("prompt_eval_count"),
            "eval_count_total": usage_total("eval_count"),
        }


class _RunProvider:
    """Per-run wrapper: records the prompt the provider received and its usage, and tags any
    provider exception (except MalformedResponseError) so the runner can tell it apart."""

    def __init__(self, inner: ClassificationProvider) -> None:
        self.inner, self.name, self.model = inner, inner.name, inner.model
        self.prompt: str | None = None
        self.usage: dict[str, Any] = {}

    def classify(self, prompt: str) -> Mapping[str, Any]:
        self.prompt = prompt
        try:
            return self.inner.classify(prompt)
        except MalformedResponseError:
            raise
        except Exception as exc:
            raise _ProviderFailure(exc) from exc
        finally:
            self.usage = dict(getattr(self.inner, "last_usage", None) or {})


class _ProviderFailure(Exception):
    def __init__(self, cause: Exception) -> None:
        super().__init__(str(cause))
        self.cause = cause


# Every value a well-behaved model can emit in a label/status field, plus the output contract's keys.
_KNOWN_TOKENS = frozenset({
    *CATEGORY_LABELS, *CALL_DETECTIONS, *CATEGORY_STATUSES, *REACTION_STATUSES, *REACTION_LABELS,
    *SPAN_STATUSES, *RESOLUTION_STATUSES, *(f.name for f in fields(EpisodePrediction)),
    "call_detection", "episodes", "uncertain_spans",
})
_PREDICTION_ID = re.compile(r"[A-Za-z_-]{0,4}[0-9]{1,6}")
_QUOTED = re.compile(r"'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"")
_MAX_MESSAGE_CHARS = 300


class _Redactor:
    """Maps any model-produced value outside the allowlist (known tokens, this call's segment ids,
    short prediction ids) to `<unlisted:N>`. Distinct values stay distinct and equal values equal, so
    validating the redacted predictions gives the same verdicts without persisting the values."""

    def __init__(self, segment_ids: set[str]) -> None:
        self.segment_ids = segment_ids
        self.seen: dict[str, str] = {}

    def __call__(self, value: str | None, *, prediction_id: bool = False) -> str | None:
        if value is None or value in _KNOWN_TOKENS or value in self.segment_ids \
                or (prediction_id and _PREDICTION_ID.fullmatch(value)):
            return value
        return self.seen.setdefault(value, f"<unlisted:{len(self.seen) + 1}>")

    def ids(self, values: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(self(v) for v in values)


def _redacted(call: Call, run: ClassificationRun) -> tuple[str, tuple[EpisodePrediction, ...],
                                                          tuple[UncertainSpan, ...], tuple[str, ...]]:
    r = _Redactor({s.segment_id for s in call.segments})
    episodes = tuple(
        replace(
            e,
            prediction_id=r(e.prediction_id, prediction_id=True),
            objection_segment_ids=r.ids(e.objection_segment_ids),
            context_segment_ids=r.ids(e.context_segment_ids),
            category_status=r(e.category_status), category=r(e.category),
            category_candidates=r.ids(e.category_candidates),
            reaction_status=r(e.reaction_status), reaction=r(e.reaction),
            reaction_candidates=r.ids(e.reaction_candidates),
            resolution_status=r(e.resolution_status),
            summary="x" * min(len(e.summary), 301) if e.summary.strip() else "",  # length check only
        )
        for e in run.episodes
    )
    spans = tuple(UncertainSpan(r.ids(s.segment_ids), r(s.status)) for s in run.uncertain_spans)
    call_detection = r(run.call_detection)
    return call_detection, episodes, spans, validate_predictions(call, call_detection, episodes, spans)


def _redact_message(message: str) -> str:
    """Quoted substrings that are not known tokens are removed (e.g. model-emitted JSON keys)."""
    text = _QUOTED.sub(lambda m: m[0] if m[0][1:-1] in _KNOWN_TOKENS else "'<unlisted>'", message)
    return text[:_MAX_MESSAGE_CHARS]


def _prediction(e: EpisodePrediction) -> dict[str, Any]:
    d = asdict(e)
    del d["summary"]  # free text derived from the transcript: not persisted
    return d


def run_experiment(spec: ExperimentSpec, calls: Sequence[Call], provider: ClassificationProvider
                   ) -> ExperimentResult:
    """Run every Call × arm once, sequentially, in call order then canonical arm order (E0, E1, E2)."""
    if not _NAME.fullmatch(spec.name):
        raise ValueError(f"experiment name must match {_NAME.pattern}; got {spec.name!r}")
    if not spec.arms or len(set(spec.arms)) != len(spec.arms) or not set(spec.arms) <= set(ARMS):
        raise ValueError(f"arms must be distinct values from {ARMS}; got {spec.arms!r}")
    arms = tuple(a for a in ARMS if a in spec.arms)
    if not calls or not all(isinstance(c, Call) for c in calls):
        raise TypeError("calls must be a non-empty sequence of canonical Calls")
    call_ids = tuple(c.call_id for c in calls)
    if len(set(call_ids)) != len(call_ids):
        raise ValueError("duplicate call_id in calls")

    knowledge = None
    if "E2" in arms:
        if spec.knowledge_root is None:
            raise ValueError("arm E2 needs spec.knowledge_root")
        knowledge = build_knowledge_context(spec.knowledge_root)  # invalid KB aborts here
    provider_config = dict(getattr(provider, "config", None) or {})

    started_at = datetime.now(UTC).isoformat()
    runs = []
    for call in calls:
        seq_hash = segment_sequence_hash(call)
        for arm in arms:
            wrapper = _RunProvider(provider)
            status, failure, run = None, None, None
            t0 = time.perf_counter()
            try:
                run = classify_call(call, arm, wrapper, spec.knowledge_root, spec.knowledge_git_sha)
            except MalformedResponseError as exc:
                status, failure = "MALFORMED_RESPONSE", exc
            except _ProviderFailure as exc:
                status, failure = "PROVIDER_ERROR", exc.cause
            elapsed = round(time.perf_counter() - t0, 3)
            e2 = arm == "E2" and knowledge is not None
            if e2 and wrapper.prompt is not None and knowledge.text.rstrip("\n") not in wrapper.prompt:
                raise RuntimeError("Knowledge Base changed during the experiment; aborting")
            call_detection, episodes, spans, errors = _redacted(call, run) if run else (None, (), (), ())
            if run is not None:
                status = "SUCCESS_VALID" if run.valid else "SUCCESS_INVALID_PREDICTION"
            encoded = wrapper.prompt.encode("utf-8") if wrapper.prompt is not None else None
            runs.append(ExperimentRunRecord(
                call_id=call.call_id,
                segment_sequence_hash=seq_hash,
                arm=arm,
                status=status,
                failure_type=type(failure).__name__ if failure else None,
                failure_message=_redact_message(str(failure)) if failure else None,
                provider=provider.name,
                model=provider.model,
                prompt_sha256=hashlib.sha256(encoded).hexdigest() if encoded is not None else None,
                prompt_chars=len(wrapper.prompt) if wrapper.prompt is not None else None,
                prompt_utf8_bytes=len(encoded) if encoded is not None else None,
                knowledge_sha256=knowledge.sha256 if e2 else None,
                knowledge_concept_versions=knowledge.concept_versions if e2 else (),
                knowledge_git_sha=spec.knowledge_git_sha if e2 else None,
                usage=wrapper.usage,
                elapsed_seconds=elapsed,
                call_detection=call_detection,
                predictions=tuple(_prediction(e) for e in episodes),
                uncertain_spans=tuple(asdict(s) for s in spans),
                validation_errors=errors,
            ))
    if knowledge and build_knowledge_context(spec.knowledge_root).sha256 != knowledge.sha256:
        raise RuntimeError("Knowledge Base changed during the experiment; aborting")
    return ExperimentResult(
        spec=ExperimentSpec(spec.name, arms, spec.knowledge_root, spec.knowledge_git_sha),
        call_ids=call_ids,
        provider=provider.name,
        model=provider.model,
        provider_config=provider_config,
        knowledge_sha256=knowledge.sha256 if knowledge else None,
        knowledge_concept_versions=knowledge.concept_versions if knowledge else (),
        started_at=started_at,
        finished_at=datetime.now(UTC).isoformat(),
        runs=tuple(runs),
    )


# --- Git provenance (orchestration only) ------------------------------------------------------


def _git(cwd: Path, *args: str) -> str:
    try:
        done = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=10,
                              check=True)
    except FileNotFoundError as exc:
        raise KnowledgeGitError("git is not available") from exc
    except NotADirectoryError as exc:
        raise KnowledgeGitError(f"not a directory: {cwd}") from exc
    except subprocess.TimeoutExpired as exc:
        raise KnowledgeGitError(f"git {args[0]} timed out") from exc
    except subprocess.CalledProcessError as exc:
        raise KnowledgeGitError(f"git {args[0]} failed: {exc.stderr.strip()}") from exc
    return done.stdout


def knowledge_git_sha(knowledge_root: Path) -> str:
    """HEAD commit SHA of the repository holding `knowledge_root`, if that directory is tracked and
    has no uncommitted change (modified, staged, untracked or ignored files); else KnowledgeGitError.
    Only `knowledge_root` is checked: changes elsewhere in the repository do not block."""
    root = Path(knowledge_root)
    if not root.is_dir():
        raise KnowledgeGitError(f"knowledge_root is not a directory: {root}")
    if not _git(root, "ls-files", "--", ".").strip():
        raise KnowledgeGitError(f"knowledge_root has no tracked files: {root}")
    dirty = _git(root, "status", "--porcelain", "--untracked-files=all", "--ignored", "--", ".")
    if dirty.strip():
        raise KnowledgeGitError(f"knowledge_root has uncommitted changes:\n{dirty.rstrip()}")
    return _git(root, "rev-parse", "HEAD").strip()


# --- artifact ---------------------------------------------------------------------------------


def result_to_dict(result: ExperimentResult) -> dict[str, Any]:
    """Privacy-first artifact content: no transcript text, prompt, raw response or summaries."""
    spec = result.spec
    return {
        "artifact_version": ARTIFACT_VERSION,
        "experiment": {"name": spec.name, "arms": list(spec.arms), "call_ids": list(result.call_ids)},
        "provider": {"name": result.provider, "model": result.model, "config": dict(result.provider_config)},
        "knowledge": {
            "sha256": result.knowledge_sha256,
            "concept_versions": dict(result.knowledge_concept_versions),
            "git_sha": spec.knowledge_git_sha,
        },
        "started_at": result.started_at,
        "finished_at": result.finished_at,
        "summary": result.summary,
        "runs": [
            {**asdict(r), "knowledge_concept_versions": dict(r.knowledge_concept_versions),
             "prediction_count": r.prediction_count}
            for r in result.runs
        ],
    }


def write_artifact(result: ExperimentResult, out_dir: Path) -> Path:
    """Write `<out_dir>/<name>.json` atomically (temp file + os.replace). Never overwrites."""
    path = Path(out_dir) / f"{result.spec.name}.json"
    if path.exists():
        raise FileExistsError(f"experiment artifact already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(result_to_dict(result), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        if path.exists():  # ponytail: check-then-replace race; single-user v0.1
            raise FileExistsError(f"experiment artifact already exists: {path}")
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return path
