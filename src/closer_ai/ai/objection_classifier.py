"""Objection classifier core + E0/E1/E2 experiment arms (runner v0.1). Eval layer, not domain.

See docs/ai/OBJECTION_CLASSIFIER_RUNNER_V0_1.md, docs/ai/SALES_KNOWLEDGE_RETRIEVAL_RAG_V0_1_PROPOSAL.md
(E0/E1/E2 ablation) and docs/evals/OBJECTION_ANNOTATION_GUIDELINE_V0_1.md (label semantics).

`classify_call(call, arm, provider)` builds one prompt, calls the provider once, parses its
structured response and validates it deterministically against the Call. No real LLM provider,
retry, fallback or network lives here: `ClassificationProvider` is the seam.

Design decisions worth knowing:

- One classifier, three arms. The arms differ only in one optional block between FACTS FROM CALL
  and OUTPUT REQUIREMENTS: E0 none, E1 `CLASSIFICATION_GUIDE` (short taxonomy + rules, a
  constant), E2 the `build_knowledge_context()` block. TASK RULES, the transcript rendering and
  the output contract are byte-identical across arms, so an arm comparison changes one variable.
- Input is only the canonical `Call` (segments + participant roles). There is no parameter for
  Deal, Outcome, stage or CRM data, and the prompt uses no Call field besides segment ids, speaker
  roles and text — call classification stays blind to outcomes (guideline "Blindness").
- Predictions are `EpisodePrediction`s, not `ObjectionEpisode`s, and categories are the CIT-O1
  annotation labels (`CATEGORY_LABELS`, reusing `knowledge_context.CONCEPT_ORDER`), not the domain
  enum. Nothing here is persisted or promoted to gold.
- Malformed provider output (wrong shape/types) raises `MalformedResponseError`. Well-formed but
  invalid predictions are kept and listed in `ClassificationRun.validation_errors` (never repaired,
  never dropped), so a future eval can count them as invalid output (ObjectionEpisode §12.1.1).
- `resolution_status` must agree with the decisive reaction (contract §9.2 + GL-3); AMBIGUOUS is a
  reaction/category status, never a resolution value.
- The run record has no timestamp and no run id: identity is the digests. The core never calls Git;
  a caller may pass `knowledge_git_sha` through.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol, runtime_checkable

from closer_ai.ai.knowledge_context import CONCEPT_ORDER, KnowledgeContext, build_knowledge_context
from closer_ai.normalization.models import Call

RUNNER_VERSION = "0.1"

Arm = Literal["E0", "E1", "E2"]
ARMS: tuple[str, ...] = ("E0", "E1", "E2")

CATEGORY_LABELS: tuple[str, ...] = (*CONCEPT_ORDER, "OTHER")  # CIT-O1 annotation labels
CALL_DETECTIONS: tuple[str, ...] = ("OBJECTIONS_FOUND", "NO_OBJECTION", "UNKNOWN")
CATEGORY_STATUSES: tuple[str, ...] = ("PRESENT", "AMBIGUOUS", "UNKNOWN")
REACTION_STATUSES: tuple[str, ...] = ("PRESENT", "ABSENT", "AMBIGUOUS")
SPAN_STATUSES: tuple[str, ...] = ("AMBIGUOUS", "UNKNOWN")
RESOLUTION_STATUSES: tuple[str, ...] = ("resolved", "partially_resolved", "unresolved", "unknown")

# Decisive reaction (contract §9.1 labels + GL-3 CLARIFICATION) -> the only resolution it allows.
_RESOLUTION_FOR_REACTION: dict[str, str] = {
    "ACCEPT": "resolved",
    "REJECT": "unresolved",
    "MIXED": "partially_resolved",
    "UNKNOWN": "unknown",
    "CLARIFICATION": "unknown",
}
REACTION_LABELS: tuple[str, ...] = tuple(_RESOLUTION_FOR_REACTION)
_MAX_SUMMARY_CHARS = 300

TASK_RULES = """TASK RULES

You annotate objections in one sales call, for evaluation only.
- Classify only what the transcript supports, not what probably happened.
- An objection is resistance stated by a lead-role participant in this call, with an identifiable
  barrier that affects moving forward.
- A topic being mentioned is not an objection. A closer statement alone is never a lead objection.
- Do not infer intent, emotion or motives that were not said.
- Only segment_ids from FACTS FROM CALL can support that something occurred. Any guide or
  knowledge in this prompt only defines concepts; it is never call evidence.
- Abstention is allowed: no objection, UNKNOWN and AMBIGUOUS are valid answers.
- No deal outcome, CRM, stage or later-call information is available; do not assume any."""

CLASSIFICATION_GUIDE = """CLASSIFICATION GUIDE — NOT FROM THIS CALL

Provisional annotation labels (not domain values). This guide defines labels; it is not evidence.

PRICE_BUDGET: the amount, available budget or ability to pay is stated as a barrier to moving forward.
TIMING_PRIORITY: timing or current priority, with a stated reason, prevents or postpones moving forward.
NEED_VALUE_FIT: the lead says they do not need it, the benefit does not pay off, or it does not fit their case.
AUTHORITY_INTERNAL_BUY_IN: the lead cannot approve alone, or someone's approval is stated as blocking progress.
TRUST_RISK: fear of a bad result or doubt that the solution/vendor will deliver, tied to not moving forward.
COMPETITION_EXISTING_SOLUTION: an existing alternative (current vendor, competitor) is the stated reason not to move.
IMPLEMENTATION_INTEGRATION: the effort, feasibility or operational impact of putting it in place blocks progress.
TERMS_PROCESS: a contract term or formal purchasing rule is stated as a blocker or condition.
OTHER: a clear objection that none of the labels above represents.

- Categorize by what is being resisted, as said; never by keyword or topic.
- Mentioning a stakeholder, competitor, price, integration or a normal process step is not an objection.
- Hesitation or a brush-off without a stated barrier gets no category.
- One category per episode; two blockers of different categories in one utterance are two episodes
  with the same anchor.
- Same lead and category while the thread is still open is the same episode."""

OUTPUT_REQUIREMENTS = f"""OUTPUT REQUIREMENTS

Return one JSON object with exactly these keys:
- "call_detection": "OBJECTIONS_FOUND" | "NO_OBJECTION" | "UNKNOWN" (transcript too incomplete to tell).
- "episodes": list, empty unless OBJECTIONS_FOUND. Each episode has exactly:
  - "prediction_id": short unique id, e.g. "p1".
  - "objection_segment_ids": the lead's segments expressing the objection, in call order; the first is
    the anchor.
  - "context_segment_ids": later segments needed to understand the episode (closer handling, lead
    responses), in call order; may be empty.
  - "category_status": "PRESENT" | "AMBIGUOUS" | "UNKNOWN".
  - "category": one label if PRESENT, else null.
  - "category_candidates": two or more labels if AMBIGUOUS, else [].
  - "reaction_status": "PRESENT" | "ABSENT" (no substantive lead response) | "AMBIGUOUS".
  - "reaction": if PRESENT, the decisive lead response: {" | ".join(REACTION_LABELS)}; else null.
  - "reaction_candidates": two or more reactions if AMBIGUOUS, else [].
  - "resolution_status": {" | ".join(RESOLUTION_STATUSES)}.
  - "summary": one short sentence on what was said; no step-by-step reasoning.
- "uncertain_spans": list of {{"segment_ids": [...], "status": "AMBIGUOUS" | "UNKNOWN"}} for stretches
  where you cannot tell whether an objection occurred (they create no episode).

Labels: {", ".join(CATEGORY_LABELS)}.

- Use only segment_ids shown in FACTS FROM CALL; never quote text as evidence.
- Do not force a category; return NO_OBJECTION when there is none.
- The decisive reaction is the last lead response that takes a position on the barrier; interjections
  and topic changes never count. A clarification request does not override an earlier position; use
  CLARIFICATION only when no response took a position.
- resolution_status follows the reaction: ACCEPT -> resolved; REJECT -> unresolved; MIXED ->
  partially_resolved (two aspects of the same category in the same response); anything else, no
  reaction or an ambiguous reaction -> unknown. AMBIGUOUS is never a resolution_status.
- Examples in any guide or knowledge are synthetic and did not happen in this call. Being described in
  the context is not a vote for a label."""


class MalformedResponseError(ValueError):
    """The provider response does not have the required structure; nothing is validated."""


@runtime_checkable
class ClassificationProvider(Protocol):
    """Seam for a future LLM-backed provider. Receives the exact prompt, returns parsed JSON."""

    name: str
    model: str

    def classify(self, prompt: str) -> Mapping[str, Any]:
        ...


@dataclass(frozen=True)
class EpisodePrediction:
    """A model prediction for one episode. Not an ObjectionEpisode and not gold."""

    prediction_id: str
    objection_segment_ids: tuple[str, ...]  # [0] is the anchor
    context_segment_ids: tuple[str, ...]
    category_status: str
    category: str | None
    category_candidates: tuple[str, ...]
    reaction_status: str
    reaction: str | None
    reaction_candidates: tuple[str, ...]
    resolution_status: str
    summary: str

    @property
    def anchor_segment_id(self) -> str:
        return self.objection_segment_ids[0]


@dataclass(frozen=True)
class UncertainSpan:
    segment_ids: tuple[str, ...]
    status: str


@dataclass(frozen=True)
class ClassificationRun:
    arm: str
    runner_version: str
    call_id: str
    segment_sequence_hash: str
    provider: str
    model: str
    prompt_sha256: str
    prompt_chars: int
    prompt_utf8_bytes: int
    knowledge_sha256: str | None  # E2 only
    knowledge_concept_versions: tuple[tuple[str, str], ...]  # E2 only
    knowledge_git_sha: str | None  # passed through by the caller, E2 only
    raw_response: Mapping[str, Any]
    call_detection: str
    episodes: tuple[EpisodePrediction, ...]
    uncertain_spans: tuple[UncertainSpan, ...]
    validation_errors: tuple[str, ...]

    @property
    def valid(self) -> bool:
        return not self.validation_errors


# --- prompt assembly --------------------------------------------------------------------------


def _roles(call: Call) -> dict[str, str]:
    return {p.id: p.role for p in call.participants}


def segment_sequence_hash(call: Call) -> str:
    """Fingerprint of the Call's segmentation (ObjectionEpisode proposal §11 serialization)."""
    roles = _roles(call)
    rows = [
        [
            s.segment_id,
            s.segment_index,
            s.speaker_id,
            roles[s.speaker_id],
            hashlib.sha256(s.text.encode("utf-8")).hexdigest(),
        ]
        for s in sorted(call.segments, key=lambda s: s.segment_index)
    ]
    canonical = json.dumps(rows, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def render_call_facts(call: Call) -> str:
    """FACTS FROM CALL: every segment in call order as `[segment_id | role]` + its text."""
    roles = _roles(call)
    lines = ["FACTS FROM CALL"]
    for s in sorted(call.segments, key=lambda s: s.segment_index):
        lines.append(f"\n[{s.segment_id} | {roles[s.speaker_id]}]\n{s.text}")
    return "\n".join(lines)


def _assemble(
    call: Call, arm: str, knowledge_root: Path | None
) -> tuple[str, KnowledgeContext | None]:
    if arm not in ARMS:
        raise ValueError(f"unknown arm {arm!r}; expected one of {ARMS}")
    knowledge = None
    blocks = [TASK_RULES, render_call_facts(call)]
    if arm == "E1":
        blocks.append(CLASSIFICATION_GUIDE)
    elif arm == "E2":
        if knowledge_root is None:
            raise ValueError("arm E2 needs knowledge_root")
        knowledge = build_knowledge_context(knowledge_root)
        blocks.append(knowledge.text.rstrip("\n"))
    blocks.append(OUTPUT_REQUIREMENTS)
    return "\n\n".join(blocks) + "\n", knowledge


def build_prompt(call: Call, arm: Arm, knowledge_root: Path | None = None) -> str:
    """The exact text a provider receives for this call and arm."""
    return _assemble(call, arm, knowledge_root)[0]


# --- response parsing (shape only) ------------------------------------------------------------

_RESPONSE_KEYS = {"call_detection", "episodes", "uncertain_spans"}
_EPISODE_KEYS = {
    "prediction_id", "objection_segment_ids", "context_segment_ids", "category_status", "category",
    "category_candidates", "reaction_status", "reaction", "reaction_candidates",
    "resolution_status", "summary",
}
_SPAN_KEYS = {"segment_ids", "status"}


def _keys(obj: Any, expected: set[str], where: str) -> Mapping[str, Any]:
    if not isinstance(obj, Mapping) or set(obj) != expected:
        got = sorted(obj) if isinstance(obj, Mapping) else type(obj).__name__
        raise MalformedResponseError(f"{where}: expected keys {sorted(expected)}, got {got}")
    return obj


def _str(value: Any, where: str, *, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    if not isinstance(value, str):
        raise MalformedResponseError(f"{where}: expected a string, got {type(value).__name__}")
    return value


def _strs(value: Any, where: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise MalformedResponseError(f"{where}: expected a list of strings")
    return tuple(value)


def _list(value: Any, where: str) -> list[Any]:
    if not isinstance(value, list):
        raise MalformedResponseError(f"{where}: expected a list")
    return value


def _parse(response: Any) -> tuple[str, tuple[EpisodePrediction, ...], tuple[UncertainSpan, ...]]:
    top = _keys(response, _RESPONSE_KEYS, "response")
    episodes = []
    for i, raw in enumerate(_list(top["episodes"], "episodes")):
        e = _keys(raw, _EPISODE_KEYS, f"episodes[{i}]")
        episodes.append(
            EpisodePrediction(
                prediction_id=_str(e["prediction_id"], f"episodes[{i}].prediction_id"),
                objection_segment_ids=_strs(e["objection_segment_ids"], f"episodes[{i}].objection_segment_ids"),
                context_segment_ids=_strs(e["context_segment_ids"], f"episodes[{i}].context_segment_ids"),
                category_status=_str(e["category_status"], f"episodes[{i}].category_status"),
                category=_str(e["category"], f"episodes[{i}].category", optional=True),
                category_candidates=_strs(e["category_candidates"], f"episodes[{i}].category_candidates"),
                reaction_status=_str(e["reaction_status"], f"episodes[{i}].reaction_status"),
                reaction=_str(e["reaction"], f"episodes[{i}].reaction", optional=True),
                reaction_candidates=_strs(e["reaction_candidates"], f"episodes[{i}].reaction_candidates"),
                resolution_status=_str(e["resolution_status"], f"episodes[{i}].resolution_status"),
                summary=_str(e["summary"], f"episodes[{i}].summary"),
            )
        )
    spans = []
    for i, raw in enumerate(_list(top["uncertain_spans"], "uncertain_spans")):
        s = _keys(raw, _SPAN_KEYS, f"uncertain_spans[{i}]")
        spans.append(
            UncertainSpan(
                segment_ids=_strs(s["segment_ids"], f"uncertain_spans[{i}].segment_ids"),
                status=_str(s["status"], f"uncertain_spans[{i}].status"),
            )
        )
    return _str(top["call_detection"], "call_detection"), tuple(episodes), tuple(spans)


# --- validation (semantics against the Call) --------------------------------------------------


def _check_ids(ids: tuple[str, ...], index: Mapping[str, int], where: str, errors: list[str]) -> bool:
    unknown = [i for i in ids if i not in index]
    if unknown:
        errors.append(f"{where}: segment_ids not in this call: {unknown}")
        return False
    if len(set(ids)) != len(ids):
        errors.append(f"{where}: duplicate segment_ids")
        return False
    if [index[i] for i in ids] != sorted(index[i] for i in ids):
        errors.append(f"{where}: segment_ids not in call order")
        return False
    return True


def _check_status(status: str, value: str | None, candidates: tuple[str, ...], allowed: tuple[str, ...],
                  present: str, where: str, errors: list[str]) -> None:
    """status PRESENT -> one allowed value, no candidates; AMBIGUOUS -> >=2 distinct allowed
    candidates, no value; any other status -> neither."""
    if status == present:
        if value not in allowed or candidates:
            errors.append(f"{where}: {present} needs one value in {allowed} and no candidates")
    elif status == "AMBIGUOUS":
        if value is not None or len(set(candidates)) < 2 or len(set(candidates)) != len(candidates) \
                or not set(candidates) <= set(allowed):
            errors.append(f"{where}: AMBIGUOUS needs >=2 distinct candidates in {allowed} and no value")
    elif value is not None or candidates:
        errors.append(f"{where}: {status} takes no value and no candidates")


def validate_predictions(
    call: Call,
    call_detection: str,
    episodes: tuple[EpisodePrediction, ...],
    uncertain_spans: tuple[UncertainSpan, ...] = (),
) -> tuple[str, ...]:
    """Every rule broken by the predictions, as messages. Empty tuple = valid. Never repairs."""
    errors: list[str] = []
    index = {s.segment_id: s.segment_index for s in call.segments}
    speaker = {s.segment_id: s.speaker_id for s in call.segments}
    roles = _roles(call)

    if call_detection not in CALL_DETECTIONS:
        errors.append(f"call_detection {call_detection!r} not in {CALL_DETECTIONS}")
    elif (call_detection == "OBJECTIONS_FOUND") != bool(episodes):
        errors.append(f"call_detection {call_detection} contradicts {len(episodes)} episode(s)")

    seen_ids: set[str] = set()
    seen_keys: set[tuple[Any, ...]] = set()
    for e in episodes:
        w = f"episode {e.prediction_id!r}"
        if not e.prediction_id or e.prediction_id in seen_ids:
            errors.append(f"{w}: empty or duplicate prediction_id")
        seen_ids.add(e.prediction_id)

        if not e.objection_segment_ids:
            errors.append(f"{w}: no objection_segment_ids")
        elif _check_ids(e.objection_segment_ids, index, f"{w} objection", errors) and _check_ids(
            e.context_segment_ids, index, f"{w} context", errors
        ):
            anchor = e.anchor_segment_id
            if roles[speaker[anchor]] != "lead":
                errors.append(f"{w}: anchor {anchor} is not spoken by a lead")
            if any(speaker[i] != speaker[anchor] for i in e.objection_segment_ids):
                errors.append(f"{w}: objection segments from more than one speaker")
            if set(e.objection_segment_ids) & set(e.context_segment_ids):
                errors.append(f"{w}: segment in both objection and context")
            if any(index[i] <= index[anchor] for i in e.context_segment_ids):
                errors.append(f"{w}: context segment at or before the anchor")

        if e.category_status not in CATEGORY_STATUSES:
            errors.append(f"{w}: category_status {e.category_status!r} not in {CATEGORY_STATUSES}")
        else:
            _check_status(e.category_status, e.category, e.category_candidates, CATEGORY_LABELS,
                          "PRESENT", f"{w} category", errors)

        if e.reaction_status not in REACTION_STATUSES:
            errors.append(f"{w}: reaction_status {e.reaction_status!r} not in {REACTION_STATUSES}")
        else:
            _check_status(e.reaction_status, e.reaction, e.reaction_candidates, REACTION_LABELS,
                          "PRESENT", f"{w} reaction", errors)

        if e.resolution_status not in RESOLUTION_STATUSES:
            errors.append(f"{w}: resolution_status {e.resolution_status!r} not in {RESOLUTION_STATUSES}")
        else:
            expected = (
                _RESOLUTION_FOR_REACTION.get(e.reaction or "", "unknown")
                if e.reaction_status == "PRESENT"
                else "unknown"
            )
            if e.resolution_status != expected:
                errors.append(
                    f"{w}: resolution_status {e.resolution_status!r} contradicts reaction "
                    f"{e.reaction_status}/{e.reaction} (expected {expected!r})"
                )

        if not e.summary.strip() or len(e.summary) > _MAX_SUMMARY_CHARS:
            errors.append(f"{w}: summary must be non-empty and at most {_MAX_SUMMARY_CHARS} chars")

        key = (e.objection_segment_ids[:1], e.category_status, e.category, tuple(sorted(e.category_candidates)))
        if key in seen_keys:
            errors.append(f"{w}: duplicates another prediction (same anchor and category)")
        seen_keys.add(key)

    for i, span in enumerate(uncertain_spans):
        w = f"uncertain_spans[{i}]"
        if span.status not in SPAN_STATUSES:
            errors.append(f"{w}: status {span.status!r} not in {SPAN_STATUSES}")
        if not span.segment_ids:
            errors.append(f"{w}: no segment_ids")
        else:
            _check_ids(span.segment_ids, index, w, errors)
    return tuple(errors)


# --- runner -----------------------------------------------------------------------------------


def classify_call(
    call: Call,
    arm: Arm,
    provider: ClassificationProvider,
    knowledge_root: Path | None = None,
    knowledge_git_sha: str | None = None,
) -> ClassificationRun:
    """Build the arm's prompt, call the provider once, parse, validate, return the run record.

    Provider exceptions propagate unchanged; a malformed response raises MalformedResponseError;
    invalid predictions are returned in `validation_errors`, not raised.
    """
    if not isinstance(call, Call):
        raise TypeError(f"call must be a canonical Call, got {type(call).__name__}")
    prompt, knowledge = _assemble(call, arm, knowledge_root)
    response = provider.classify(prompt)
    call_detection, episodes, spans = _parse(response)
    encoded = prompt.encode("utf-8")
    return ClassificationRun(
        arm=arm,
        runner_version=RUNNER_VERSION,
        call_id=call.call_id,
        segment_sequence_hash=segment_sequence_hash(call),
        provider=provider.name,
        model=provider.model,
        prompt_sha256=hashlib.sha256(encoded).hexdigest(),
        prompt_chars=len(prompt),
        prompt_utf8_bytes=len(encoded),
        knowledge_sha256=knowledge.sha256 if knowledge else None,
        knowledge_concept_versions=knowledge.concept_versions if knowledge else (),
        knowledge_git_sha=knowledge_git_sha if knowledge else None,
        raw_response=response,
        call_detection=call_detection,
        episodes=episodes,
        uncertain_spans=spans,
        validation_errors=validate_predictions(call, call_detection, episodes, spans),
    )
