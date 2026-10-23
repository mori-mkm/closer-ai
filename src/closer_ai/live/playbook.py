"""Machine-readable playbook + Playbook Compliance Engine v1 (deterministic, no LLM).

    Commercial State = facts        Compliance Engine = evaluation of those facts against the playbook

The human source of truth is the playbook Markdown; the runtime reads only its versioned JSON
(`PLAYBOOK`), validated at load. `evaluate()` is a pure function of the playbook, the Commercial State
view and the transcript (segment id, role, text). It is recomputed when read, so it is idempotent,
cumulative (facts and lines only accumulate) and rebuilt for free after a restart.

Evidence:
- lead facts come only from the Commercial State (never re-extracted here);
- closer facts come from a few high-precision regex signals over the closer's own lines
  (second chair offered, meeting with the decider, scheduled next step, prohibited phrase).
A rule is SATISFIED or VIOLATED only with segment ids (enforced by `ComplianceResult`). Rules without a
v1 detector are listed in `not_evaluated`, never guessed.
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from closer_ai.live.commercial_state import fact_key, fold

_REPO = Path(__file__).resolve().parents[3]
PLAYBOOK = _REPO / "docs" / "playbooks" / "agrotalento" / "playbook_agrotalento_v1.json"

CLASSES = ("REQUIRED", "RECOMMENDED", "OPTIONAL", "PROHIBITED")
STATUSES = ("PENDING", "SATISFIED", "VIOLATED", "NOT_APPLICABLE", "UNKNOWN")
BUSINESS_STATUSES = ("CONFIRMED", "PENDING_CONFIRMATION")
_RULE_ID = re.compile(r"^(E\d{1,2}-R\d{1,2}|N/A-\d)$")
DECIDER_ROLES = ("decision_participant", "final_decision_maker")


# --- playbook -------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Rule:
    id: str
    stage: str
    rule_class: str
    title: str
    evidence_type: str
    applies_when: str | None = None
    phrases: tuple[str, ...] = ()


@dataclass(frozen=True)
class Playbook:
    version: str
    stages: dict[str, str]  # id -> title, in playbook order
    rules: tuple[Rule, ...]
    commercial_info: tuple[dict[str, str], ...]

    def authorized_commercial_info(self) -> tuple[dict[str, str], ...]:
        """The only commercial information a consumer may state as fact (guidance, knowledge units):
        PENDING_CONFIRMATION items exist in the source but are never authorized."""
        return tuple(i for i in self.commercial_info if i["business_status"] == "CONFIRMED")


def parse_playbook(data: dict[str, Any]) -> Playbook:
    """Validate the JSON shape; raise ValueError naming the first problem."""
    def need(ok: bool, msg: str) -> None:
        if not ok:
            raise ValueError(f"playbook: {msg}")

    need(isinstance(data.get("version"), str) and data["version"], "version missing")
    stages = {s["id"]: s["title"] for s in data.get("stages", [])}
    need(len(stages) == len(data.get("stages", [])) and stages, "stage ids missing or repeated")
    rules = []
    for r in data.get("rules", []):
        rid = r.get("id")
        need(isinstance(rid, str) and bool(_RULE_ID.match(rid)), f"bad rule id {rid!r}")
        need(r.get("stage") in stages, f"{rid}: unknown stage {r.get('stage')!r}")
        need(r.get("class") in CLASSES, f"{rid}: unknown class {r.get('class')!r}")
        need(isinstance(r.get("title"), str) and r["title"] and isinstance(r.get("evidence_type"), str),
             f"{rid}: title/evidence_type missing")
        need(r["evidence_type"] != "prohibited_phrase" or (r["class"] == "PROHIBITED" and r.get("phrases")),
             f"{rid}: a phrase rule must be PROHIBITED with phrases")
        rules.append(Rule(rid, r["stage"], r["class"], r["title"], r["evidence_type"], r.get("applies_when"),
                          tuple(fold(p) for p in r.get("phrases", ()))))
    need(bool(rules) and len({r.id for r in rules}) == len(rules), "rules missing or repeated ids")
    info = tuple(data.get("commercial_info", []))
    for i in info:
        need(i.get("business_status") in BUSINESS_STATUSES, f"{i.get('id')}: bad business_status")
    return Playbook(data["version"], stages, tuple(rules), info)


@lru_cache(maxsize=4)
def load_playbook(path: Path = PLAYBOOK) -> Playbook:
    return parse_playbook(json.loads(path.read_text(encoding="utf-8")))


# --- results --------------------------------------------------------------------------------------

@dataclass(frozen=True)
class ComplianceResult:
    rule_id: str
    status: str
    segment_ids: tuple[str, ...]
    reason: str
    details: dict[str, Any] = field(default_factory=dict)  # e.g. quantity, date/time/owner

    def __post_init__(self) -> None:
        if self.status not in STATUSES:
            raise ValueError(f"{self.rule_id}: unknown status {self.status}")
        if self.status in ("SATISFIED", "VIOLATED") and not self.segment_ids:
            raise ValueError(f"{self.rule_id}: {self.status} without evidence")


@dataclass(frozen=True)
class PlaybookComplianceState:
    playbook_version: str
    rule_results: tuple[ComplianceResult, ...]  # evaluated rules, playbook order
    not_evaluated: tuple[str, ...]  # rules with no v1 detector
    signals: tuple[dict[str, Any], ...]  # deterministic closer/lead signals used as evidence
    rules: dict[str, Rule]
    stages: dict[str, str]

    def _ids(self, status: str, rule_class: str | None = None) -> list[str]:
        return [r.rule_id for r in self.rule_results if r.status == status
                and (rule_class is None or self.rules[r.rule_id].rule_class == rule_class)]

    @property
    def completed_required(self) -> list[str]:
        return self._ids("SATISFIED", "REQUIRED")

    @property
    def pending_required(self) -> list[str]:
        return self._ids("PENDING", "REQUIRED")

    @property
    def violations(self) -> list[ComplianceResult]:
        return [r for r in self.rule_results if r.status == "VIOLATED"]

    def stage_summary(self) -> list[dict[str, Any]]:
        """Evidence per stage; no single current stage (calls go back and forth)."""
        out = []
        for sid, title in self.stages.items():
            results = [r for r in self.rule_results if self.rules[r.rule_id].stage == sid]
            counts = {s.lower(): sum(r.status == s for r in results) for s in STATUSES}
            out.append({"stage": sid, "title": title, "evaluated": len(results), **counts,
                        "has_evidence": any(r.status in ("SATISFIED", "VIOLATED") for r in results),
                        "not_evaluated": sum(self.rules[r].stage == sid for r in self.not_evaluated)})
        return out

    def view(self) -> dict[str, Any]:
        def result(r: ComplianceResult) -> dict[str, Any]:
            rule = self.rules[r.rule_id]
            return {"rule_id": r.rule_id, "stage": rule.stage, "class": rule.rule_class, "title": rule.title,
                    "status": r.status, "segment_ids": list(r.segment_ids), "reason": r.reason, **r.details}
        return {"playbook_version": self.playbook_version,
                "rule_results": [result(r) for r in self.rule_results],
                "completed_required": self.completed_required, "pending_required": self.pending_required,
                "violations": [result(r) for r in self.violations], "stage_summary": self.stage_summary(),
                "not_evaluated": list(self.not_evaluated), "signals": list(self.signals)}


# --- deterministic signals ------------------------------------------------------------------------

def _plain(text: str) -> str:
    """Lowercase, no accents, punctuation kept ("14:00", "R$", "10%")."""
    return unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode()


# ponytail: word lists / patterns, high precision by design; widen only when real calls show misses.
_NOT_A_DAY = r"(?![ -]?(?:cadeira|vez|opcao|parcela|pessoa|etapa|reuniao|call|geracao|parte|fase|turma|pergunta))"
_DATE = re.compile(rf"\b(?:(?:segunda|terca|quarta|quinta|sexta){_NOT_A_DAY}(?:[ -]feira)?|sabado|domingo|amanha"
                   r"|hoje|dia \d{1,2}|\d{1,2}/\d{1,2})\b")
_TIME = re.compile(r"\b\d{1,2} ?h(?:\d{2})?\b|\b\d{1,2}:\d{2}\b|\b(?:as|a partir das|ate as) \d{1,2}\b|\bmeio[ -]dia\b"
                   r"|\b(?:as|a) (?:uma|duas|tres|quatro|cinco|seis|sete|oito|nove|dez|onze|doze)"
                   r" (?:horas?|da tarde|da manha|da noite)\b")
_STEP_CUE = re.compile(r"\b(?:lig\w*|marc\w*|agend\w*|reuni\w*|convers\w*|fal\w*|retorn\w*|call|encontro|cham\w*"
                       r"|mand\w*|envi\w*|fechado|combinado|pode ser|confirm\w*|nos vemos|contato|procuro)\b")
_MEETING_CUE = re.compile(r"\b(?:marc\w*|agend\w*|reuni\w*|convers\w*|call|encontro|chamar|trazer|participar)\b")
_OWNER = re.compile(r"\b(?:eu (?:te |lhe )?|te )(?:ligo|chamo|mando|envio|retorno|marco|agendo|procuro|confirmo)\b")
_SECOND_CHAIR = re.compile(r"\bsegunda cadeira\b|\b(?:traga|trazer|traz) (?:o |a )?(?:seu |sua )?"
                           r"(?:socio|socia|esposa|marido|filho|filha|pai|mae|conjuge|sucessor|genro|braco direito)\b")
_NEGATION = re.compile(r"\b(?:nao|nunca|nem|sem)\b")
_NUMBER = (r"(?:\d+(?:[.,]\d+)?|meia|uma?|dois|duas|tres|quatro|cinco|seis|sete|oito|nove|dez|quinze|vinte|trinta"
           r"|quarenta|cinquenta|cem|duzentos|trezentos|quinhentos|mil)")
_UNIT = (r"(?:mil|milhao|milhoes|reais|real|%|por cento|horas?|dias?|semanas?|meses|mes|anos?|cabecas?|bezerros?"
         r"|animais|matrizes|arrobas?|hectares?|ha|litros?|sacas?|funcionarios?|pessoas?|clientes?|vendas?|pedidos?)")
_QUANTITY = re.compile(rf"r\$ ?\d[\d.,]*(?: mil)?|\b{_NUMBER} (?:de )?{_UNIT}(?!\w)|\b\d+(?:[.,]\d+)? ?%")


def schedule(text: str) -> dict[str, str] | None:
    """Date AND time AND a next-step cue in one line, else None ("semana que vem" is not a date)."""
    t = _plain(text)
    d, h = _DATE.search(t), _TIME.search(t)
    if not (d and h and _STEP_CUE.search(t)):
        return None
    return {"date": d.group(0), "time": h.group(0)}


def quantity(text: str) -> str | None:
    """A number with a unit ("8 horas", "R$ 10 mil", "15%", "uma hora"), or None ("muito tempo")."""
    m = _QUANTITY.search(_plain(text))
    return m.group(0) if m else None


def phrase_hits(text: str, phrases: tuple[str, ...]) -> list[str]:
    """Prohibited phrases said affirmatively (no negation in the 3 words before: "não garanto")."""
    words = fold(text)
    hits = []
    for p in phrases:
        for m in re.finditer(rf"\b{re.escape(p)}\b", words):
            before = words[:m.start()].split()[-3:]
            if not _NEGATION.search(" ".join(before)):
                hits.append(p)
                break
    return hits


# --- evaluation -----------------------------------------------------------------------------------

Segment = tuple[str, str, str]  # (segment_id, role, text), call order


def _ids(facts: list[dict[str, Any]]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(i for f in facts for i in f["segment_ids"]))


def _ordered(ids: Any, order: dict[str, int]) -> tuple[str, ...]:
    return tuple(sorted(dict.fromkeys(ids), key=lambda i: order.get(i, 1 << 30)))


def _quote(facts: list[dict[str, Any]]) -> str:
    return "; ".join(f"“{f['value']}”" for f in facts)


def evaluate(playbook: Playbook, facts: dict[str, list[dict[str, Any]]],
             segments: list[Segment]) -> PlaybookComplianceState:
    order = {sid: i for i, (sid, _, _) in enumerate(segments)}
    text = {sid: t for sid, _, t in segments}
    closer = [(sid, t) for sid, role, t in segments if role == "closer"]
    signals: list[dict[str, Any]] = []
    for sid, role, t in segments:
        if role not in ("closer", "lead"):
            continue
        if (s := schedule(t)) is not None:
            owner = role if _OWNER.search(_plain(t)) else None
            signals.append({"kind": "NEXT_STEP_SCHEDULED", "segment_id": sid, "speaker_role": role, **s,
                            **({"owner": owner} if owner else {})})
        if role == "closer" and _SECOND_CHAIR.search(fold(t)):
            signals.append({"kind": "SECOND_CHAIR_OFFERED", "segment_id": sid, "speaker_role": role})
    # a decider: a stakeholder with a decision role, or one the lead named in a decision step
    # ("Preciso falar com meu sócio" -> stakeholder "sócio" mentioned + decision "falar com meu sócio")
    steps = " ".join(fold(f["value"]) for f in facts["decision_process"])
    deciders = [f for f in facts["stakeholders"] if f.get("role") in DECIDER_ROLES
                or (fact_key(f["value"]) and re.search(rf"\b{re.escape(fact_key(f['value']))}\b", steps))]
    results: list[ComplianceResult] = []

    def add(rule: Rule, status: str, ids: Any = (), reason: str = "", **details: Any) -> None:
        results.append(ComplianceResult(rule.id, status, _ordered(ids, order), reason, details))

    def pain(rule: Rule) -> None:
        f = facts["pain_points"]
        if f:
            add(rule, "SATISFIED", _ids(f), f"dor registrada: {_quote(f)}")
        else:
            add(rule, "PENDING", reason="nenhuma dor registrada")

    def impact(rule: Rule) -> None:
        f = facts["impacts"]
        if f:
            add(rule, "SATISFIED", _ids(f), f"consequência registrada: {_quote(f)}")
        else:
            add(rule, "PENDING", reason="nenhuma consequência registrada")

    def impact_quantified(rule: Rule) -> None:
        # the number must be in the lead's own impact words (the Commercial State value), not just nearby
        hits = [(f, q) for f in facts["impacts"] if (q := quantity(f["value"]))]
        if hits:
            add(rule, "SATISFIED", _ids([f for f, _ in hits]), f"impacto com número do lead: {_quote([f for f, _ in hits])}",
                quantity=hits[0][1])
        elif facts["impacts"]:
            add(rule, "PENDING", reason="impacto ainda não quantificado (sem número do lead)")
        else:
            add(rule, "PENDING", reason="nenhum impacto registrado")

    def decision_authority(rule: Rule) -> None:
        if deciders or facts["decision_process"]:
            who = "; ".join(f"{f['value']} ({f['role'] if f.get('role') in DECIDER_ROLES else 'no processo de decisão'})"
                            for f in deciders)
            how = _quote(facts["decision_process"])
            add(rule, "SATISFIED", _ids(deciders + facts["decision_process"]),
                "decisão mapeada: " + " · ".join(x for x in (who, how) if x))
        elif facts["stakeholders"]:
            add(rule, "PENDING", reason="pessoa citada sem papel na decisão")
        else:
            add(rule, "PENDING", reason="quem decide ainda não identificado")

    def decider_plan(rule: Rule) -> None:
        if not deciders:
            if facts["decision_process"]:
                add(rule, "NOT_APPLICABLE", reason="nenhum outro decisor identificado")
            else:
                add(rule, "PENDING", reason="decisor ainda não identificado (E6-R1)")
            return
        keys = {fact_key(f["value"]) for f in deciders} - {""}
        chair = [s["segment_id"] for s in signals if s["kind"] == "SECOND_CHAIR_OFFERED"]
        meeting = [s for s in signals if s["kind"] == "NEXT_STEP_SCHEDULED"
                   and _MEETING_CUE.search(_plain(text[s["segment_id"]]))
                   and any(re.search(rf"\b{re.escape(k)}\b", fold(text[s["segment_id"]])) for k in keys)]
        if meeting:
            add(rule, "SATISFIED", [*_ids(deciders), *(s["segment_id"] for s in meeting)],
                "reunião com o decisor marcada com data e hora",
                date=meeting[0]["date"], time=meeting[0]["time"])
        elif chair:
            add(rule, "SATISFIED", [*_ids(deciders), *chair], "2ª cadeira oferecida ao decisor")
        else:
            add(rule, "PENDING", _ids(deciders), "decisor identificado, sem reunião marcada nem 2ª cadeira")

    def objection_answered(rule: Rule) -> None:
        objs = facts["objections"]
        if not objs:
            add(rule, "NOT_APPLICABLE", reason="nenhuma objeção detectada")
            return
        answered, open_ = [], []
        for f in objs:
            last = max(order.get(i, -1) for i in f["segment_ids"])
            reply = next((sid for sid, _ in closer if order[sid] > last), None)
            (answered if reply else open_).append((f, reply))
        if open_:
            add(rule, "PENDING", _ids([f for f, _ in open_]),
                "objeção sem fala do closer depois: " + ", ".join(f["value"] for f, _ in open_))
        else:
            add(rule, "SATISFIED", [*_ids(objs), *(r for _, r in answered)],
                "o closer falou depois de cada objeção: " + ", ".join(f["value"] for f in objs))

    def objection_cause(rule: Rule) -> None:
        if not facts["objections"]:
            add(rule, "NOT_APPLICABLE", reason="nenhuma objeção detectada")
        else:  # a question after the objection is not reliably "investigating the cause" (v1)
            add(rule, "UNKNOWN", _ids(facts["objections"]), "sem detector determinístico confiável no v1")

    def next_step(rule: Rule) -> None:
        lead = [f for f in facts["next_steps"]
                if schedule(f["value"]) or any(_DATE.search(_plain(text.get(i, ""))) and _TIME.search(
                    _plain(text.get(i, ""))) for i in f["segment_ids"])]
        said = [s for s in signals if s["kind"] == "NEXT_STEP_SCHEDULED"]
        if lead or said:
            first = said[0] if said else None
            details = {k: first[k] for k in ("date", "time", "owner") if first and k in first}
            add(rule, "SATISFIED", [*_ids(lead), *(s["segment_id"] for s in said)],
                "próximo passo com data e hora" + (f": {_quote(lead)}" if lead else ""), **details)
        elif facts["next_steps"]:
            add(rule, "PENDING", _ids(facts["next_steps"]),
                f"próximo passo sem data e hora: {_quote(facts['next_steps'])}")
        else:
            add(rule, "PENDING", reason="próximo passo com data e hora não registrado")

    def prohibited(rule: Rule) -> None:
        hits = [(sid, p) for sid, t in closer for p in phrase_hits(t, rule.phrases)]
        if hits:
            add(rule, "VIOLATED", [sid for sid, _ in hits],
                "closer disse: " + ", ".join(dict.fromkeys(f"“{p}”" for _, p in hits)))
        else:
            add(rule, "PENDING", reason="nenhuma ocorrência até agora")

    evaluators = {"pain_identified": pain, "impact_explored": impact, "impact_quantified": impact_quantified,
                  "decision_authority_identified": decision_authority, "decider_engagement_plan": decider_plan,
                  "objection_answered": objection_answered, "objection_cause_investigated": objection_cause,
                  "next_step_scheduled": next_step, "prohibited_phrase": prohibited}
    skipped = []
    for rule in playbook.rules:
        if rule.evidence_type in evaluators:
            evaluators[rule.evidence_type](rule)
        else:
            skipped.append(rule.id)
    return PlaybookComplianceState(playbook.version, tuple(results), tuple(skipped), tuple(signals),
                                   {r.id: r for r in playbook.rules}, playbook.stages)
