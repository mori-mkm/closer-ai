"""Post-call Intelligence v0: Call -> objections + commercial guidance + next steps + risks.

See docs/ai/OBJECTION_GUIDANCE_ENGINE_V0.md. Composition only:

    classify_call (E2 by default)  -> objection episodes (existing classifier, unchanged)
    guide_episode per episode      -> CommercialGuidance (objection_guidance)
    one extraction prompt          -> lead end position, stakeholders, next steps
    deterministic rules            -> risks

Design decisions worth knowing:

- Every quote in the output is copied from the Call by segment_id; the model only returns ids.
- Next steps are grounded in the segments the model cites, fail closed (a violating step is
  rejected and the reason listed in `errors`; nothing is repaired):
  owner `lead`/`closer`/`both` must match who spoke the cited segments; `action` must share a word
  with them and introduce no ungrounded fact (`grounding.ungrounded`); `due_date` must appear
  verbatim in them and be an actual date/deadline ("depois", "mais pra frente" are not).
- Risks are rules over the extracted structure, not model opinions, so each one points at evidence.
- An invalid classifier run (validation_errors) yields no objections and no guidance; the errors are
  surfaced, nothing is repaired. Provider exceptions propagate to the caller.
"""
from __future__ import annotations

import dataclasses
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from closer_ai.ai.grounding import has_date, normalize, ungrounded
from closer_ai.ai.objection_classifier import Arm, ClassificationProvider, classify_call
from closer_ai.ai.objection_guidance import (
    ENGINE_VERSION,
    CommercialGuidance,
    ObjectionKnowledge,
    Quote,
    guide_episode,
    quotes,
)
from closer_ai.normalization.models import Call

LEAD_END_POSITIONS: tuple[str, ...] = (
    "ACCEPTED", "DECLINED", "CONSIDERING", "CONDITIONAL", "DEFERRED", "NO_PROPOSAL", "UNKNOWN",
)
STEP_OWNERS: tuple[str, ...] = ("lead", "closer", "both", "unknown")


@dataclass(frozen=True)
class ObjectionFinding:
    prediction_id: str
    category_status: str
    category: str | None
    category_candidates: tuple[str, ...]
    evidence: tuple[Quote, ...]
    resolution_status: str
    summary: str  # model-written, one sentence


@dataclass(frozen=True)
class LeadEndPosition:
    value: str  # LEAD_END_POSITIONS
    evidence: tuple[Quote, ...]


@dataclass(frozen=True)
class Stakeholder:
    who: str  # as said in the call, e.g. "sócio"
    evidence: tuple[Quote, ...]


@dataclass(frozen=True)
class NextStep:
    owner: str  # STEP_OWNERS
    action: str
    due_date: str | None  # verbatim from the evidence, or None; never inferred
    evidence: tuple[Quote, ...]


@dataclass(frozen=True)
class Risk:
    code: str
    description: str
    evidence: tuple[Quote, ...]


@dataclass(frozen=True)
class PostCallIntelligence:
    call_id: str
    objections: tuple[ObjectionFinding, ...]
    commercial_guidance: tuple[CommercialGuidance, ...]
    lead_end_position: LeadEndPosition
    stakeholders: tuple[Stakeholder, ...]
    next_steps: tuple[NextStep, ...]
    risks: tuple[Risk, ...]
    provenance: Mapping[str, Any]
    errors: tuple[str, ...]

    @property
    def pipeline_status(self) -> str:
        """SUCCESS = no model output rejected anywhere; INVALID = something was rejected (see errors)."""
        return "INVALID" if self.errors else "SUCCESS"

    def to_json(self) -> str:
        return json.dumps(dataclasses.asdict(self), ensure_ascii=False, indent=2)


# --- extraction -------------------------------------------------------------------------------

POST_CALL_TASK = f"""POST-CALL TASK

Extract, from this sales call only, what was explicitly said about how it ended.
- Use only FACTS FROM CALL. Do not infer intent, dates or commitments that were not said.
- "lead_end_position": {{"value": ..., "segment_ids": [...]}}: the lead's position at the end of
  the call, cited by the lead's own last relevant segments. One of:
  ACCEPTED = said yes to buying / closing;
  DECLINED = said no;
  CONSIDERING = will think, look at material or a proposal, without a stated condition;
  CONDITIONAL = will only decide after a stated condition (someone's approval, a number, a check);
  DEFERRED = postponed the decision or conversation to a later moment;
  NO_PROPOSAL = no offer or price was presented, so there was nothing to accept or decline;
  UNKNOWN = the call does not show the lead's position. Use UNKNOWN only when none of the above is
  supported; do not force a value.
- "stakeholders": list of {{"who": "...", "segment_ids": [...]}} — people who are NOT in this call but
  were said to take part in the decision (e.g. a partner, spouse, board). Empty if none.
- "next_steps": list of {{"owner": {" | ".join(STEP_OWNERS)}, "action": "...", "due_date": ... ,
  "segment_ids": [...]}}: commitments said in the call. "owner" is who committed, per the cited
  segments' speakers ("unknown" if unclear). "action" in Portuguese, short, using the call's words.
  "due_date" is a date or deadline copied exactly as said (e.g. "sexta-feira"), or null. Vague timing
  such as "depois", "mais pra frente", "qualquer dia" is not a date: use null.
- segment_ids must come from FACTS FROM CALL and must contain what they support.

Return one JSON object with exactly the keys "lead_end_position", "stakeholders", "next_steps"."""


def build_post_call_prompt(call: Call) -> str:
    roles = {p.id: p.role for p in call.participants}
    facts = "\n".join(f"\n[{s.segment_id} | {roles[s.speaker_id]}]\n{s.text}"
                      for s in sorted(call.segments, key=lambda s: s.segment_index))
    return f"{POST_CALL_TASK}\n\nFACTS FROM CALL\n{facts}\n"


def _seg_ids(value: Any, call: Call, where: str, errors: list[str]) -> list[str] | None:
    known = {s.segment_id for s in call.segments}
    if not isinstance(value, list) or not value or not all(isinstance(v, str) for v in value):
        errors.append(f"{where}: segment_ids must be a non-empty list of strings")
        return None
    if not set(value) <= known:
        errors.append(f"{where}: segment_ids not in this call: {sorted(set(value) - known)}")
        return None
    return value


def _step_problems(owner: str, action: str, due: Any, evidence: tuple[Quote, ...]) -> list[str]:
    text = "\n".join(q.text for q in evidence)
    speakers = {q.speaker_role for q in evidence}
    problems = []
    if owner in ("lead", "closer") and owner not in speakers:
        problems.append(f"owner {owner!r} spoke none of the cited segments")
    if owner == "both" and not {"lead", "closer"} <= speakers:
        problems.append("owner 'both' needs cited segments from lead and closer")
    stems = {w[:5] for w in normalize(text).split() if len(w) >= 4}
    if not any(w[:5] in stems for w in normalize(action).split() if len(w) >= 4):
        problems.append(f"action {action!r} shares no word with the cited segments")
    problems += [f"action ungrounded {p}" for p in ungrounded(action, text)]
    if due is not None:
        if not isinstance(due, str) or not due.strip() or normalize(due.strip()) not in normalize(text):
            problems.append(f"due_date {due!r} is not stated in the cited segments")
        elif not has_date(due):
            problems.append(f"due_date {due!r} is not a date or deadline")
    return problems


def _extract(call: Call, response: Any) -> tuple[LeadEndPosition, tuple[Stakeholder, ...],
                                                 tuple[NextStep, ...], list[str]]:
    unknown = LeadEndPosition("UNKNOWN", ())
    keys = {"lead_end_position", "stakeholders", "next_steps"}
    if not isinstance(response, Mapping) or set(response) != keys:
        got = sorted(response) if isinstance(response, Mapping) else type(response).__name__
        return unknown, (), (), [f"post-call response: expected keys {sorted(keys)}, got {got}"]
    errors: list[str] = []

    position = unknown
    raw = response["lead_end_position"]
    if not isinstance(raw, Mapping) or raw.get("value") not in LEAD_END_POSITIONS:
        errors.append(f"lead_end_position: value must be one of {LEAD_END_POSITIONS}")
    elif raw["value"] == "UNKNOWN":
        position = unknown
    elif (ids := _seg_ids(raw.get("segment_ids"), call, "lead_end_position", errors)) is not None:
        position = LeadEndPosition(raw["value"], quotes(call, ids))

    stakeholders = []
    raw_list = response["stakeholders"] if isinstance(response["stakeholders"], list) else []
    if not isinstance(response["stakeholders"], list):
        errors.append("stakeholders: expected a list")
    for i, s in enumerate(raw_list):
        who = s.get("who") if isinstance(s, Mapping) else None
        if not isinstance(who, str) or not who.strip():
            errors.append(f"stakeholders[{i}]: 'who' must be a non-empty string")
        elif (ids := _seg_ids(s.get("segment_ids"), call, f"stakeholders[{i}]", errors)) is not None:
            stakeholders.append(Stakeholder(who.strip(), quotes(call, ids)))

    steps = []
    raw_list = response["next_steps"] if isinstance(response["next_steps"], list) else []
    if not isinstance(response["next_steps"], list):
        errors.append("next_steps: expected a list")
    for i, s in enumerate(raw_list):
        w = f"next_steps[{i}]"
        if not isinstance(s, Mapping) or s.get("owner") not in STEP_OWNERS \
                or not isinstance(s.get("action"), str) or not s["action"].strip():
            errors.append(f"{w}: needs owner in {STEP_OWNERS} and a non-empty action")
            continue
        ids = _seg_ids(s.get("segment_ids"), call, w, errors)
        if ids is None:
            continue
        evidence = quotes(call, ids)
        problems = _step_problems(s["owner"], s["action"], s.get("due_date"), evidence)
        if problems:
            errors += [f"{w}: {problem}; step rejected" for problem in problems]
            continue
        due = s.get("due_date")
        steps.append(NextStep(s["owner"], s["action"].strip(), due.strip() if due else None, evidence))
    return position, tuple(stakeholders), tuple(steps), errors


# --- risks ------------------------------------------------------------------------------------


def derive_risks(objections: tuple[ObjectionFinding, ...], position: LeadEndPosition,
                 stakeholders: tuple[Stakeholder, ...], steps: tuple[NextStep, ...]) -> tuple[Risk, ...]:
    risks = []
    if position.value == "DECLINED":
        risks.append(Risk("LEAD_DECLINED", "O lead recusou no fim da call.", position.evidence))
    if not steps:
        risks.append(Risk("NO_CLEAR_NEXT_STEP", "Nenhum próximo passo claro combinado na call.", ()))
    for s in steps:
        if s.due_date is None:
            risks.append(Risk("NEXT_STEP_WITHOUT_DATE", f"Próximo passo sem data definida: {s.action}.",
                              s.evidence))
    for o in objections:
        if o.resolution_status != "resolved":
            label = o.category or "objeção sem categoria"
            risks.append(Risk("OPEN_OBJECTION",
                              f"{label} não foi resolvida na call ({o.resolution_status}).", o.evidence))
    for s in stakeholders:
        risks.append(Risk("DECISION_STAKEHOLDER_ABSENT",
                          f"Participante da decisão fora da call: {s.who}.", s.evidence))
    return tuple(risks)


# --- pipeline ---------------------------------------------------------------------------------


def analyze_call(
    call: Call,
    provider: ClassificationProvider,
    classification_knowledge_root: Path,
    guidance_knowledge: ObjectionKnowledge,
    arm: Arm = "E2",
) -> PostCallIntelligence:
    """Call -> PostCallIntelligence. 1 classifier call + 1 per guided episode + 1 extraction call."""
    run = classify_call(call, arm, provider, knowledge_root=classification_knowledge_root)
    errors = [f"classifier: {e}" for e in run.validation_errors]
    episodes = () if run.validation_errors else run.episodes
    objections = tuple(
        ObjectionFinding(e.prediction_id, e.category_status, e.category, e.category_candidates,
                         quotes(call, e.objection_segment_ids), e.resolution_status, e.summary)
        for e in episodes
    )
    guidance = tuple(guide_episode(call, e, guidance_knowledge, provider) for e in episodes)
    errors += [f"guidance {g.prediction_id}: {e}" for g in guidance if g.status == "INVALID_RESPONSE"
               for e in g.errors]

    position, stakeholders, steps, extract_errors = _extract(call, provider.classify(build_post_call_prompt(call)))
    errors += extract_errors
    return PostCallIntelligence(
        call_id=call.call_id,
        objections=objections,
        commercial_guidance=guidance,
        lead_end_position=position,
        stakeholders=stakeholders,
        next_steps=steps,
        risks=derive_risks(objections, position, stakeholders, steps),
        provenance={
            "engine_version": ENGINE_VERSION,
            "provider": provider.name,
            "model": provider.model,
            "classifier_arm": run.arm,
            "classifier_call_detection": run.call_detection,
            "classifier_prompt_sha256": run.prompt_sha256,
            "classification_knowledge_sha256": run.knowledge_sha256,
            "guidance_knowledge_sha256": guidance_knowledge.sha256,
            "segment_sequence_hash": run.segment_sequence_hash,
        },
        errors=tuple(errors),
    )


# --- markdown ---------------------------------------------------------------------------------

_GRADE_LABEL = {
    "STRONG": "STRONG",
    "MODERATE": "MODERATE",
    "WEAK": "WEAK — hipótese de prática, sem efeito medido",
    "NOT_SUPPORTED_BY_CURRENT_SOURCES": "NOT SUPPORTED BY CURRENT SOURCES — nenhuma fonte encontrada",
}


def _md_quotes(qs: tuple[Quote, ...]) -> list[str]:
    return [f"> **{q.speaker_role}:** {q.text}" for q in qs]


def render_markdown(pci: PostCallIntelligence) -> str:
    out = [f"# Call Intelligence: `{pci.call_id[:12]}`", "", f"Status do pipeline: **{pci.pipeline_status}**", ""]
    if not pci.objections:
        detection = pci.provenance.get("classifier_call_detection")
        out += ["## Objeções", "", f"Nenhuma objeção registrada (classifier: {detection}).", ""]
    guidance = {g.prediction_id: g for g in pci.commercial_guidance}
    for o in pci.objections:
        title = o.category or f"{o.category_status} ({', '.join(o.category_candidates) or 'sem categoria'})"
        out += [f"## Objeção: {title}", "", "Evidência na call:", *_md_quotes(o.evidence), "",
                f"Resolução na call: {o.resolution_status}", ""]
        g = guidance.get(o.prediction_id)
        if g is None or g.status != "GUIDED":
            reason = "; ".join(g.errors) if g else "sem guidance"
            out += [f"**Sem recomendação** ({g.status if g else 'NONE'}): {reason}", ""]
            continue
        m, gen = g.recommended_move, g.generated_guidance
        out += [
            f"### Ação recomendada: {m.code or 'sem código'} (`{m.id}`)", "",
            f"**Conhecimento (pesquisa, não é da call):** {m.guidance}", "",
            f"**Gerado pelo modelo ({gen.generated_by}), validado contra a call:**", "",
            f"Por quê: {gen.rationale}", "",
            "Pergunta sugerida:", f"> {gen.suggested_question}", "",
            "### Evitar", *[f"- {d.guidance} ({d.evidence_grade})" for d in g.avoid], "",
            "### Grau da evidência", "",
            f"{_GRADE_LABEL[g.knowledge_grade]} (nota da pesquisa: {m.grade_note})", "",
            (
                f"Fontes do movimento/evitar: {', '.join(g.knowledge_sources) or 'nenhuma'} · "
                f"fontes sobre a categoria: {', '.join(g.category_evidence_sources) or 'nenhuma'} · "
                f"unidade: `{g.knowledge_unit_id}@{g.knowledge_unit_version}`"
            ),
            "",
        ]
    out += ["## Posição do lead no fim", "", pci.lead_end_position.value,
            *_md_quotes(pci.lead_end_position.evidence), ""]
    if pci.stakeholders:
        out += ["## Participantes da decisão fora da call", ""]
        for s in pci.stakeholders:
            out += [f"- {s.who}", "", *_md_quotes(s.evidence), ""]
        out.append("")
    out += ["## Próximos passos", ""]
    for s in pci.next_steps:
        out += [f"- **{s.owner}:** {s.action} ({s.due_date or 'data não definida'})", "",
                *_md_quotes(s.evidence), ""]
    if not pci.next_steps:
        out.append("Nenhum próximo passo combinado.")
    out += ["", "## Riscos", ""]
    out += [f"- **{r.code}:** {r.description}" for r in pci.risks] or ["Nenhum risco detectado pelas regras."]
    if pci.errors:
        out += ["", "## Avisos (saída do modelo rejeitada)", "", *[f"- {e}" for e in pci.errors]]
    p = pci.provenance
    out += ["", "---", (
        f"_{p['provider']}/{p['model']} · classifier {p['classifier_arm']} · engine {p['engine_version']} · "
        "evidência = falas da call; conhecimento = pesquisa externa, não prova nada sobre a call._"
    ), ""]
    return "\n".join(out)
