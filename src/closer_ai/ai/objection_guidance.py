"""Objection Guidance Engine v0: classified objection + objection knowledge -> CommercialGuidance.

See docs/ai/OBJECTION_GUIDANCE_ENGINE_V0.md. Product layer of the Value Sprint v0 vertical slice,
built on top of the E0/E1/E2 classifier (it consumes `EpisodePrediction`s; it does not change them).

Design decisions worth knowing:

- Knowledge lives in `docs/knowledge/sales/guidance/<CATEGORY>.json`, one unit per CIT-O1 category,
  transcribed from Gabriel's objection research (docs/research/). It is a sibling of the
  classification KB, not part of it: the E2 corpus and its digest are untouched.
- Retrieval v0 is an exact category lookup (`ObjectionKnowledge.retrieve`). No ranking, embeddings or
  search; a future retriever only needs the same `retrieve(category) -> unit | None` method.
- CALL EVIDENCE and SALES KNOWLEDGE are separate blocks in the prompt and separate fields in the
  output. Quotes come from the Call by segment_id, never from model text.
- The model only picks a move id from the retrieved unit and phrases a rationale and a question.
  Grade, sources and the "avoid" list are copied from the knowledge unit, never from the model, so a
  WEAK move cannot come back as anything stronger and negative knowledge is always shown.
- Generated text is checked by `grounding.ungrounded` against the CALL EVIDENCE it was given: an
  invented date, number, amount, stakeholder, name or commercial condition, or a leftover template
  placeholder, rejects the whole answer (fail closed).
- No repair, no retry: a malformed, invalid or ungrounded model answer yields status INVALID_RESPONSE
  with the errors listed; a category without knowledge yields NO_KNOWLEDGE. Provider exceptions propagate.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from closer_ai.ai.grounding import ungrounded
from closer_ai.ai.knowledge_context import CONCEPT_ORDER
from closer_ai.ai.objection_classifier import ClassificationProvider, EpisodePrediction
from closer_ai.normalization.models import Call

ENGINE_VERSION = "0.1"

EVIDENCE_GRADES: tuple[str, ...] = ("STRONG", "MODERATE", "WEAK", "NOT_SUPPORTED_BY_CURRENT_SOURCES")
# Seller response codes of the research (taxonomy v0.1, section 3/4). A move may have none (pause).
RESPONSE_CODES: tuple[str, ...] = (
    "ACKNOWLEDGE_VALIDATE", "CLARIFY", "PROBE_EXPLORE", "ADDRESS_EXPLAIN", "PROVIDE_EVIDENCE",
    "REFRAME", "NEGOTIATE_OFFER_ALTERNATIVE", "DEFER_FOLLOW_UP", "CONFIRM_UNDERSTANDING",
    "IGNORE_CHANGE_TOPIC",
)
GUIDANCE_STATUSES: tuple[str, ...] = ("GUIDED", "NO_KNOWLEDGE", "INVALID_RESPONSE")

_UNIT_KEYS = {"id", "category", "version", "source_section", "typical_phrases", "recommended_moves",
              "do_not", "evidence_source_ids", "notes"}
_MOVE_KEYS = {"id", "code", "guidance", "evidence_grade", "grade_note", "source_ids"}
_DO_NOT_KEYS = _MOVE_KEYS - {"code"}
_RESPONSE_KEYS = {"move_id", "rationale", "suggested_question", "evidence_segment_ids"}
_SOURCE_ID = re.compile(r"^N\d+$")
_MAX_TEXT_CHARS = 400


class ObjectionKnowledgeError(ValueError):
    """The guidance knowledge is malformed or incomplete; nothing is loaded."""


@dataclass(frozen=True)
class KnowledgeItem:
    """A recommended move or a do-not item. `code` is None for do-not items and code-less moves."""

    id: str
    code: str | None
    guidance: str
    evidence_grade: str
    grade_note: str  # the research's own grade text, verbatim intent
    source_ids: tuple[str, ...]


@dataclass(frozen=True)
class ObjectionKnowledgeUnit:
    id: str
    category: str
    version: str
    source_section: str
    typical_phrases: tuple[str, ...]
    recommended_moves: tuple[KnowledgeItem, ...]
    do_not: tuple[KnowledgeItem, ...]
    evidence_source_ids: tuple[str, ...]
    notes: str

    def move(self, move_id: str) -> KnowledgeItem | None:
        return next((m for m in self.recommended_moves if m.id == move_id), None)


@dataclass(frozen=True)
class ObjectionKnowledge:
    units: Mapping[str, ObjectionKnowledgeUnit]
    sources: Mapping[str, Mapping[str, str]]
    sha256: str  # digest of the unit + source files as read; run provenance

    def retrieve(self, category: str | None) -> ObjectionKnowledgeUnit | None:
        """Retrieval v0: exact category lookup. None for OTHER, None or an unknown label."""
        return self.units.get(category or "")


def _fail(where: str, msg: str) -> ObjectionKnowledgeError:
    return ObjectionKnowledgeError(f"{where}: {msg}")


def _exact_keys(obj: Any, expected: set[str], where: str) -> Mapping[str, Any]:
    if not isinstance(obj, dict) or set(obj) != expected:
        got = sorted(obj) if isinstance(obj, dict) else type(obj).__name__
        raise _fail(where, f"expected keys {sorted(expected)}, got {got}")
    return obj


def _text(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _fail(where, "expected a non-empty string")
    return value


def _ids(value: Any, sources: Mapping[str, Any], where: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(v, str) and _SOURCE_ID.match(v) for v in value):
        raise _fail(where, "expected a list of source ids like 'N13'")
    unknown = sorted(set(value) - set(sources))
    if unknown:
        raise _fail(where, f"source ids not in SOURCES.json: {unknown}")
    return tuple(value)


def _item(raw: Any, keys: set[str], prefix: str, sources: Mapping[str, Any], where: str) -> KnowledgeItem:
    obj = _exact_keys(raw, keys, where)
    item_id = _text(obj["id"], f"{where}.id")
    if not item_id.startswith(prefix):
        raise _fail(where, f"id {item_id!r} must start with {prefix!r}")
    code = obj.get("code")
    if code is not None and code not in RESPONSE_CODES:
        raise _fail(where, f"code {code!r} not in {RESPONSE_CODES}")
    if obj["evidence_grade"] not in EVIDENCE_GRADES:
        raise _fail(where, f"evidence_grade {obj['evidence_grade']!r} not in {EVIDENCE_GRADES}")
    return KnowledgeItem(
        id=item_id,
        code=code,
        guidance=_text(obj["guidance"], f"{where}.guidance"),
        evidence_grade=obj["evidence_grade"],
        grade_note=_text(obj["grade_note"], f"{where}.grade_note"),
        source_ids=_ids(obj["source_ids"], sources, f"{where}.source_ids"),
    )


def _unit(path: Path, sources: Mapping[str, Any]) -> ObjectionKnowledgeUnit:
    name = path.stem
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise _fail(path.name, f"not valid JSON: {exc}") from exc
    obj = _exact_keys(raw, _UNIT_KEYS, path.name)
    if obj["category"] != name or obj["id"] != f"guidance.{name}":
        raise _fail(path.name, f"category/id must match the file name {name!r}")
    phrases = obj["typical_phrases"]
    if not isinstance(phrases, list) or not phrases or not all(isinstance(p, str) for p in phrases):
        raise _fail(path.name, "typical_phrases must be a non-empty list of strings")
    moves, do_not = obj["recommended_moves"], obj["do_not"]
    if not isinstance(moves, list) or not moves:
        raise _fail(path.name, "recommended_moves must be a non-empty list")
    if not isinstance(do_not, list) or not do_not:
        raise _fail(path.name, "do_not must be a non-empty list (negative knowledge is required)")
    unit = ObjectionKnowledgeUnit(
        id=obj["id"],
        category=name,
        version=_text(obj["version"], f"{path.name}.version"),
        source_section=_text(obj["source_section"], f"{path.name}.source_section"),
        typical_phrases=tuple(phrases),
        recommended_moves=tuple(_item(m, _MOVE_KEYS, f"{name}.M", sources, f"{path.name}.recommended_moves[{i}]")
                                for i, m in enumerate(moves)),
        do_not=tuple(_item(d, _DO_NOT_KEYS, f"{name}.D", sources, f"{path.name}.do_not[{i}]")
                     for i, d in enumerate(do_not)),
        evidence_source_ids=_ids(obj["evidence_source_ids"], sources, f"{path.name}.evidence_source_ids"),
        notes=_text(obj["notes"], f"{path.name}.notes"),
    )
    all_ids = [i.id for i in (*unit.recommended_moves, *unit.do_not)]
    if len(set(all_ids)) != len(all_ids):
        raise _fail(path.name, "duplicate move/do_not id")
    return unit


def load_objection_knowledge(root: Path) -> ObjectionKnowledge:
    """Load and validate `SOURCES.json` + one `<CATEGORY>.json` per CIT-O1 category under `root`.

    A missing category, an unknown file, an unknown key, grade, code or source id is an error.
    """
    root = Path(root)
    sources_path = root / "SOURCES.json"
    if not sources_path.is_file():
        raise _fail(str(root), "missing SOURCES.json")
    try:
        sources_raw = json.loads(sources_path.read_text(encoding="utf-8"))
        sources = sources_raw["sources"]
    except (ValueError, KeyError, TypeError) as exc:
        raise _fail("SOURCES.json", f"malformed: {exc}") from exc
    if not isinstance(sources, dict) or not all(_SOURCE_ID.match(k) for k in sources):
        raise _fail("SOURCES.json", "'sources' must map ids like 'N13' to entries")

    files = {p.stem: p for p in root.glob("*.json") if p.name != "SOURCES.json"}
    missing = [c for c in CONCEPT_ORDER if c not in files]
    unexpected = sorted(set(files) - set(CONCEPT_ORDER))
    if missing or unexpected:
        raise _fail(str(root), f"corpus mismatch: missing={missing} unexpected={unexpected}")

    digest = hashlib.sha256()
    for path in [sources_path, *(files[c] for c in CONCEPT_ORDER)]:
        digest.update(path.name.encode("utf-8") + b"\0" + path.read_text(encoding="utf-8").encode("utf-8"))
    return ObjectionKnowledge(
        units={c: _unit(files[c], sources) for c in CONCEPT_ORDER},
        sources=sources,
        sha256=digest.hexdigest(),
    )


# --- guidance ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class Quote:
    """Call evidence: a transcript segment, copied from the Call by id."""

    segment_id: str
    speaker_role: str
    text: str


@dataclass(frozen=True)
class GeneratedGuidance:
    """MODEL-GENERATED text. Passed the grounding validator; never a source of facts."""

    rationale: str
    rationale_evidence: tuple[Quote, ...]  # the call segments the model cited for it
    suggested_question: str
    generated_by: str  # "<provider>/<model>"


@dataclass(frozen=True)
class CommercialGuidance:
    """Three separate, auditable parts: CALL EVIDENCE, SALES KNOWLEDGE, MODEL-GENERATED GUIDANCE."""

    prediction_id: str  # the classifier episode this guidance is for
    status: str  # GUIDANCE_STATUSES
    category: str | None
    # CALL EVIDENCE: copied from the Call by segment_id
    objection_evidence: tuple[Quote, ...]
    # SALES KNOWLEDGE: copied from the retrieved unit, never from the model
    knowledge_unit_id: str | None  # "guidance.PRICE_BUDGET"
    knowledge_unit_version: str | None
    knowledge_move_id: str | None
    recommended_move: KnowledgeItem | None
    avoid: tuple[KnowledgeItem, ...]  # always the unit's full do_not list
    knowledge_grade: str | None  # grade of the recommended move
    knowledge_sources: tuple[str, ...]  # source ids of the move and the avoid items
    category_evidence_sources: tuple[str, ...]  # research findings about the category itself
    # MODEL-GENERATED GUIDANCE: None unless GUIDED
    generated_guidance: GeneratedGuidance | None
    errors: tuple[str, ...]


def quotes(call: Call, segment_ids: tuple[str, ...] | list[str]) -> tuple[Quote, ...]:
    roles = {p.id: p.role for p in call.participants}
    by_id = {s.segment_id: s for s in call.segments}
    return tuple(Quote(i, roles[by_id[i].speaker_id], by_id[i].text) for i in segment_ids if i in by_id)


def _render_quotes(qs: tuple[Quote, ...]) -> str:
    return "\n".join(f"[{q.segment_id} | {q.speaker_role}]\n{q.text}" for q in qs)


GUIDANCE_TASK = """GUIDANCE TASK

You help a sales closer choose the next commercial move for ONE objection raised in a sales call.
- CALL EVIDENCE is what was actually said in this call. It is the only evidence about this call.
- SALES KNOWLEDGE is external guidance, NOT FROM THIS CALL. It never proves that anything happened.
- Choose exactly one move from SALES KNOWLEDGE, by its id. Never invent a move.
- Do not invent cases, numbers, results, guarantees, discounts, offers or business rules that are
  not in CALL EVIDENCE or SALES KNOWLEDGE.
- "rationale": one or two sentences in Portuguese on why this move fits what the lead said. Refer
  only to CALL EVIDENCE; do not infer motives that were not said.
- "suggested_question": one question in Portuguese that the closer can ask next, adapting the chosen
  move to this call. No promises or claims about results.
- "evidence_segment_ids": the CALL EVIDENCE segment_ids that support the rationale.
- Grounding (checked automatically; any violation rejects the whole answer): "rationale" and
  "suggested_question" must not contain any date, weekday, month, deadline, number, amount, person,
  role (partner, spouse, CFO, board...), name, product or commercial condition (discount,
  installments, guarantee...) that does not appear in CALL EVIDENCE. Facts from the call may be reused.
- Never write placeholders (brackets, braces, TODO) and never choose a date or value the call did not
  give: say it generically ("uma data objetiva", "esse ponto") or reuse what the call says."""


_TEMPLATE_SLOT = re.compile(r"\[([^\]]*)\]")


def _generic(guidance: str) -> str:
    """Prompt-only rendering of knowledge templates ("[data]" -> "uma data objetiva"), so the model is
    not shown slots to fill. The knowledge itself and the output validation are unchanged."""
    return _TEMPLATE_SLOT.sub(
        lambda m: "uma data objetiva" if m.group(1).strip().lower() in ("data", "dia") else "esse ponto",
        guidance)


def _call_evidence(call: Call, episode: EpisodePrediction) -> tuple[Quote, ...]:
    return quotes(call, [*episode.objection_segment_ids, *episode.context_segment_ids])


_BRIEF = ("one or two sentences in Portuguese", "one short sentence in Portuguese")
# The response shape, enforced by the provider when it supports it (live copilot). Validation below is
# unchanged and still runs: the schema only stops malformed shapes such as integer segment ids.
_STR, _STRS = {"type": "string"}, {"type": "array", "items": {"type": "string"}}
GUIDANCE_SCHEMA = {"type": "object", "additionalProperties": False, "required": sorted(_RESPONSE_KEYS),
                   "properties": {"move_id": _STR, "rationale": _STR, "suggested_question": _STR,
                                  "evidence_segment_ids": _STRS}}


def build_guidance_prompt(call: Call, episode: EpisodePrediction, unit: ObjectionKnowledgeUnit,
                          brief: bool = False) -> str:
    """`brief` (live copilot): ask for a one-sentence rationale. Measured on qwen3:8b: ~118 -> ~93 output
    tokens, about 1.2 s less on the live hardware. Everything else is unchanged."""
    evidence = _call_evidence(call, episode)
    moves = "\n".join(f"- {m.id} [{m.code or 'NO_CODE'}] {_generic(m.guidance)}" for m in unit.recommended_moves)
    do_not = "\n".join(f"- {d.guidance}" for d in unit.do_not)
    blocks = [
        GUIDANCE_TASK.replace(*_BRIEF) if brief else GUIDANCE_TASK,
        f"CALL EVIDENCE\n\nObjection category (classifier): {unit.category}\n\n{_render_quotes(evidence)}",
        (
            "SALES KNOWLEDGE — NOT FROM THIS CALL\n\n"
            f"Category: {unit.category}\n\nMoves:\n{moves}\n\nDo not:\n{do_not}\n\nNotes: {unit.notes}"
        ),
        (
            "OUTPUT\n\nReturn one JSON object with exactly these keys: \"move_id\" (one id from Moves), "
            "\"rationale\", \"suggested_question\", \"evidence_segment_ids\" (list)."
        ),
    ]
    return "\n\n".join(blocks) + "\n"


def _validate_response(response: Any, call: Call, episode: EpisodePrediction,
                       unit: ObjectionKnowledgeUnit) -> list[str]:
    if not isinstance(response, Mapping) or set(response) != _RESPONSE_KEYS:
        got = sorted(response) if isinstance(response, Mapping) else type(response).__name__
        return [f"response: expected keys {sorted(_RESPONSE_KEYS)}, got {got}"]
    errors = []
    if not isinstance(response["move_id"], str) or unit.move(response["move_id"]) is None:
        errors.append(f"move_id {response['move_id']!r} is not a move of {unit.id}")
    # What the model was shown as CALL EVIDENCE (segments + category line) is the only fact base.
    fact_base = "\n".join([unit.category, *(q.text for q in _call_evidence(call, episode))])
    for key in ("rationale", "suggested_question"):
        value = response[key]
        if not isinstance(value, str) or not value.strip() or len(value) > _MAX_TEXT_CHARS:
            errors.append(f"{key}: expected a non-empty string of at most {_MAX_TEXT_CHARS} chars")
        else:
            errors += [f"{key}: ungrounded {problem}" for problem in ungrounded(value, fact_base)]
    if isinstance(response["suggested_question"], str) and "?" not in response["suggested_question"]:
        errors.append("suggested_question: not a question")
    ids = response["evidence_segment_ids"]
    allowed = {*episode.objection_segment_ids, *episode.context_segment_ids}
    if not isinstance(ids, list) or not ids or not all(isinstance(i, str) for i in ids):
        errors.append("evidence_segment_ids: expected a non-empty list of strings")
    elif not set(ids) <= allowed:
        errors.append(f"evidence_segment_ids not in CALL EVIDENCE: {sorted(set(ids) - allowed)}")
    return errors


def guide_episode(call: Call, episode: EpisodePrediction, knowledge: ObjectionKnowledge,
                  provider: ClassificationProvider, live: bool = False) -> CommercialGuidance:
    """Guidance for one classified episode. One provider call, only when knowledge exists.

    `live` (copilot during the call): one-sentence rationale and the provider enforces GUIDANCE_SCHEMA.
    Measured on 8 live objection lines (qwen3:8b): GUIDED 4/8 -> 7/8 (integer segment ids were the main
    rejection) and ~1.2 s less. Validation and grounding are the same either way."""
    category = episode.category if episode.category_status == "PRESENT" else None
    evidence = quotes(call, episode.objection_segment_ids)
    unit = knowledge.retrieve(category)
    no_answer: dict[str, Any] = {"knowledge_move_id": None, "recommended_move": None,
                                 "knowledge_grade": None, "knowledge_sources": (), "generated_guidance": None}
    if unit is None:
        reason = (f"no guidance knowledge for category {category!r}" if category
                  else f"category not PRESENT ({episode.category_status}); no guidance")
        return CommercialGuidance(episode.prediction_id, "NO_KNOWLEDGE", category, evidence,
                                  knowledge_unit_id=None, knowledge_unit_version=None, avoid=(),
                                  category_evidence_sources=(), errors=(reason,), **no_answer)

    prompt = build_guidance_prompt(call, episode, unit, brief=live)
    response = provider.classify(prompt, schema=GUIDANCE_SCHEMA) if live else provider.classify(prompt)
    errors = _validate_response(response, call, episode, unit)
    knowledge_part: dict[str, Any] = {
        "knowledge_unit_id": unit.id, "knowledge_unit_version": unit.version, "avoid": unit.do_not,
        "category_evidence_sources": unit.evidence_source_ids,
    }
    if errors:  # fail closed: nothing the model wrote is kept, nothing is repaired
        return CommercialGuidance(episode.prediction_id, "INVALID_RESPONSE", category, evidence,
                                  errors=tuple(errors), **knowledge_part, **no_answer)
    move = unit.move(response["move_id"])
    return CommercialGuidance(
        prediction_id=episode.prediction_id,
        status="GUIDED",
        category=category,
        objection_evidence=evidence,
        knowledge_move_id=move.id,
        recommended_move=move,
        knowledge_grade=move.evidence_grade,
        knowledge_sources=tuple(dict.fromkeys(s for item in (move, *unit.do_not) for s in item.source_ids)),
        generated_guidance=GeneratedGuidance(
            rationale=response["rationale"].strip(),
            rationale_evidence=quotes(call, response["evidence_segment_ids"]),
            suggested_question=response["suggested_question"].strip(),
            generated_by=f"{provider.name}/{provider.model}",
        ),
        errors=(),
        **knowledge_part,
    )
