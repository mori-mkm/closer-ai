"""Machine-readable playbook + Playbook Compliance Engine (deterministic, no LLM).

    Commercial State = facts        Compliance Engine = evaluation of those facts against the playbook

The human source of truth is the playbook Markdown; the runtime reads only its versioned JSON
(`PLAYBOOK`: stages, rules, business_knowledge, opportunities), validated at load. `evaluate()` is a pure
function of the playbook, the Commercial State view and the transcript (segment id, role, text). It is
recomputed when read, so it is idempotent, cumulative (facts and lines only accumulate) and rebuilt for
free after a restart.

Evidence:
- lead facts come only from the Commercial State (never re-extracted here);
- closer/lead phrasings come from `signals.extract` (shared with the Opportunity Engine).
A rule is SATISFIED or VIOLATED only with segment ids (enforced by `ComplianceResult`). Rules without a
detector are listed in `not_evaluated`, never guessed.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from closer_ai.live import signals as sig
from closer_ai.live.commercial_state import fact_key, fold
from closer_ai.live.signals import Segment, Signal, phrase_hits, quantity

_REPO = Path(__file__).resolve().parents[3]
PLAYBOOK = _REPO / "docs" / "playbooks" / "agrotalento" / "playbook_agrotalento_v1.json"

CLASSES = ("REQUIRED", "RECOMMENDED", "OPTIONAL", "PROHIBITED")
STATUSES = ("PENDING", "SATISFIED", "VIOLATED", "NOT_APPLICABLE", "UNKNOWN")
BUSINESS_STATUSES = ("CONFIRMED", "PENDING_CONFIRMATION")
IMPLEMENTATIONS = ("IMPLEMENTED", "DEFERRED_LOW_CONFIDENCE", "BLOCKED_BUSINESS_CONFIRMATION")
ACTION_TYPES = ("ALIGN_PAYMENT_TO_CASH", "INVOLVE_DECISION_MAKER", "CONNECT_PILLAR", "ASK_NUMBER_CONNECT_PILLAR",
                "PROBE_TIME_CONCERN", "PROBE_PRIOR_EXPERIENCE", "PROBE_DECISION_CAUSE", "ASK_FOR_DECISION")
# what an opportunity can be triggered by / resolved by (the engine's capabilities)
TRIGGERS = (*sig.LEAD, "DECISION_DEPENDENCY", "OBJECTION_AUTHORITY", "BUYING_SIGNAL_FACT")
RESOLUTIONS = (*(k for k in sig.CLOSER if k != "DECISION_ASK_SHORT"), "PILLAR_MENTIONED", "NEXT_STEP_SCHEDULED",
               "DECISION_MEETING_SCHEDULED", "PRICE_PRESENTED")
_RULE_ID = re.compile(r"^(E\d{1,2}-R\d{1,2}|N/A-\d)$")
_OP_ID = re.compile(r"^OP-\d{2}$")
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
class OpportunityDef:
    id: str
    title: str
    implementation: str
    priority: int = 99
    triggers: tuple[str, ...] = ()
    resolved_by: tuple[dict[str, Any], ...] = ()
    action_type: str | None = None
    requires_knowledge: tuple[str, ...] = ()
    action: str = ""
    variants: tuple[dict[str, Any], ...] = ()
    objective: str = ""
    reopen: bool = False  # event-like (a new "vou pensar" after a resolved one is a new opportunity)
    reason: str = ""  # why it is not implemented


@dataclass(frozen=True)
class Playbook:
    version: str
    stages: dict[str, str]  # id -> title, in playbook order
    rules: tuple[Rule, ...]
    business_knowledge: tuple[dict[str, str], ...]
    opportunities: tuple[OpportunityDef, ...] = ()

    def authorized_knowledge(self) -> tuple[dict[str, str], ...]:
        """The only business information a consumer may state as fact (guidance, opportunities):
        PENDING_CONFIRMATION items exist in the source but are never authorized."""
        return tuple(i for i in self.business_knowledge if i["business_status"] == "CONFIRMED")

    def confirmed(self, ids: Any) -> bool:
        ok = {i["id"] for i in self.authorized_knowledge()}
        return all(i in ok for i in ids)


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
    knowledge = tuple(data.get("business_knowledge", []))
    for i in knowledge:
        need(i.get("business_status") in BUSINESS_STATUSES, f"{i.get('id')}: bad business_status")
    kids = {i["id"] for i in knowledge}
    need(len(kids) == len(knowledge), "repeated business_knowledge ids")
    ops = []
    for o in data.get("opportunities", []):
        oid = o.get("id")
        need(isinstance(oid, str) and bool(_OP_ID.match(oid)), f"bad opportunity id {oid!r}")
        need(o.get("implementation") in IMPLEMENTATIONS, f"{oid}: bad implementation")
        refs = [*o.get("requires_knowledge", []), *(k for v in o.get("variants", []) for k in v["requires_knowledge"]),
                *(k for r in o.get("resolved_by", []) for k in r.get("requires_knowledge", []))]
        need(all(k in kids for k in refs), f"{oid}: unknown business_knowledge in {refs}")
        if o["implementation"] == "IMPLEMENTED":
            need(o.get("action_type") in ACTION_TYPES, f"{oid}: unknown action_type {o.get('action_type')!r}")
            need(bool(o.get("triggers")) and all(t in TRIGGERS for t in o["triggers"]), f"{oid}: unknown trigger")
            need(bool(o.get("resolved_by")) and all(r.get("signal") in RESOLUTIONS for r in o["resolved_by"]),
                 f"{oid}: unknown resolution signal")
            need(bool(o.get("action")) and isinstance(o.get("priority"), int), f"{oid}: action/priority missing")
        else:
            need(bool(o.get("reason")), f"{oid}: a deferred opportunity needs a reason")
        ops.append(OpportunityDef(oid, o.get("title", ""), o["implementation"], o.get("priority", 99),
                                  tuple(o.get("triggers", ())), tuple(o.get("resolved_by", ())), o.get("action_type"),
                                  tuple(o.get("requires_knowledge", ())), o.get("action", ""),
                                  tuple(o.get("variants", ())), o.get("objective", ""), bool(o.get("reopen")),
                                  o.get("reason", "")))
    need(len({o.id for o in ops}) == len(ops), "repeated opportunity ids")
    return Playbook(data["version"], stages, tuple(rules), knowledge, tuple(ops))


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
    not_evaluated: tuple[str, ...]  # rules with no detector yet
    signals: tuple[Signal, ...]  # the deterministic signals used as evidence
    rules: dict[str, Rule]
    stages: dict[str, str]

    def result(self, rule_id: str) -> ComplianceResult | None:
        return next((r for r in self.rule_results if r.rule_id == rule_id), None)

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
                "not_evaluated": list(self.not_evaluated), "signals": [s.view() for s in self.signals]}


# --- evaluation -----------------------------------------------------------------------------------

def _ids(facts: list[dict[str, Any]]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(i for f in facts for i in f["segment_ids"]))


def _quote(facts: list[dict[str, Any]]) -> str:
    return "; ".join(f"“{f['value']}”" for f in facts)


def deciders(facts: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """Stakeholders with a decision role, or named by the lead in a decision step ("Preciso falar com meu
    sócio" -> stakeholder "sócio" mentioned + decision "falar com meu sócio")."""
    steps = " ".join(fold(f["value"]) for f in facts["decision_process"])
    return [f for f in facts["stakeholders"] if f.get("role") in DECIDER_ROLES
            or (fact_key(f["value"]) and re.search(rf"\b{re.escape(fact_key(f['value']))}\b", steps))]


def _key(value: str) -> str:
    words = fact_key(value).split()
    return (sig.party_key(words[-1]) or "") if words else ""


def decision_map(facts: dict[str, list[dict[str, Any]]], signals: list[Signal],
                 order: dict[str, int]) -> tuple[set[str], list[str]]:
    """Who else decides (party keys) and the evidence, from the Commercial State AND the deterministic
    signals (the 8B extractor sometimes records "sócio" only as mentioned, or nothing at all):
    - stakeholders with a decision role or named in a decision step;
    - a person named right after "quem participa da decisão?" (DECIDER_NAMED);
    - the party of a decision dependency ("preciso falar com meu sócio"); with a pronoun ("com ele"),
      the latest person mentioned before that line."""
    dec = deciders(facts)
    keys = {_key(f["value"]) for f in dec} - {""}
    ids = [i for f in dec for i in f["segment_ids"]]
    people = sorted([(min(order.get(i, 1 << 30) for i in f["segment_ids"]), _key(f["value"]))
                     for f in facts["stakeholders"]]
                    + [(order.get(s.segment_id, -1), s.details["party"]) for s in signals if s.type == "DECIDER_NAMED"])
    for s in signals:
        if s.type == "DECIDER_NAMED":
            keys.add(s.details["party"])
            ids += s.segment_ids
        elif s.type == "DECISION_DEPENDENCY":
            party = s.details.get("party") or next(
                (k for p, k in reversed(people) if k and p < order.get(s.segment_id, -1)), None)
            if party:
                keys.add(party)
                ids += s.segment_ids
    return keys, ids


def decider_keys(facts: dict[str, list[dict[str, Any]]], signals: list[Signal] = (),
                 order: dict[str, int] | None = None) -> set[str]:
    return decision_map(facts, list(signals), order or {})[0]


def meeting_matches(s: Signal, keys: set[str]) -> bool:
    """A meeting signal with this decider: named ("com seu sócio") or a pronoun ("com ele")."""
    return s.type == "DECISION_MEETING_SCHEDULED" and (s.details.get("party") is None or s.details["party"] in keys)


def evaluate(playbook: Playbook, facts: dict[str, list[dict[str, Any]]], segments: list[Segment],
             signals: list[Signal] | None = None) -> PlaybookComplianceState:
    order = {sid: i for i, (sid, _, _) in enumerate(segments)}
    signals = sig.extract(segments) if signals is None else signals
    text = {sid: t for sid, _, t in segments}
    closer = [(sid, t) for sid, role, t in segments if role == "closer"]
    by_type: dict[str, list[Signal]] = {}
    for s in signals:
        by_type.setdefault(s.type, []).append(s)

    def pos(s: Signal | str) -> int:
        return order.get(s if isinstance(s, str) else s.segment_id, -1)

    def after(kind: str, start: int, role: str | None = None) -> list[Signal]:
        return [s for s in by_type.get(kind, []) if pos(s) > start and (role is None or s.role == role)]

    def closer_turns_after(start: int, n: int) -> set[str]:
        """Segment ids of the first `n` closer turns after position `start`."""
        out, turns, prev = set(), 0, None
        for sid, role, _ in segments[start + 1:]:
            if role == "closer":
                if prev != "closer":
                    turns += 1
                if turns > n:
                    break
                out.add(sid)
            prev = role
        return out

    prices = [s for s in by_type.get("PRICE_PRESENTED", []) if s.role == "closer"]
    first_price = pos(prices[0]) if prices else None
    keys, decision_ids = decision_map(facts, signals, order)
    meetings = [s for s in by_type.get("DECISION_MEETING_SCHEDULED", []) if meeting_matches(s, keys)]
    seats = [s for s in by_type.get("SECOND_SEAT_OFFERED", []) if s.role == "closer"]
    thinks = by_type.get("THINK_IT_OVER", [])
    results: list[ComplianceResult] = []

    def add(rule: Rule, status: str, ids: Any = (), reason: str = "", **details: Any) -> None:
        ids = tuple(sorted(dict.fromkeys(i.segment_id if isinstance(i, Signal) else i for i in ids),
                           key=lambda i: order.get(i, 1 << 30)))
        results.append(ComplianceResult(rule.id, status, ids, reason, details))

    def pain(rule: Rule) -> None:
        f = facts["pain_points"]
        add(rule, "SATISFIED", _ids(f), f"dor registrada: {_quote(f)}") if f else add(
            rule, "PENDING", reason="nenhuma dor registrada")

    def impact(rule: Rule) -> None:
        f = facts["impacts"]
        add(rule, "SATISFIED", _ids(f), f"consequência registrada: {_quote(f)}") if f else add(
            rule, "PENDING", reason="nenhuma consequência registrada")

    def impact_quantified(rule: Rule) -> None:
        # the number must be in the lead's own impact words (the Commercial State value), not just nearby
        hits = [(f, q) for f in facts["impacts"] if (q := quantity(f["value"]))]
        if hits:
            add(rule, "SATISFIED", _ids([f for f, _ in hits]),
                f"impacto com número do lead: {_quote([f for f, _ in hits])}", quantity=hits[0][1])
        elif facts["impacts"]:
            add(rule, "PENDING", reason="impacto ainda não quantificado (sem número do lead)")
        else:
            add(rule, "PENDING", reason="nenhum impacto registrado")

    def timing_before_price(rule: Rule) -> None:
        probes = [s for s in by_type.get("TIMING_PROBE", []) if first_price is None or pos(s) < first_price]
        if probes:
            add(rule, "SATISFIED", [probes[0], *prices[:1]],
                "prioridade/momento checado antes do preço" if prices else "prioridade/momento checado (sem preço ainda)")
        elif prices:  # the probe detector has limited recall: never claimed as a violation
            add(rule, "PENDING", prices[:1], "preço apresentado sem checagem de prioridade/momento detectada antes")
        else:
            add(rule, "PENDING", reason="prioridade/momento ainda não checados")

    def decision_authority(rule: Rule) -> None:
        if keys or facts["decision_process"]:
            who = ", ".join(sorted(keys))
            how = _quote(facts["decision_process"])
            add(rule, "SATISFIED", [*decision_ids, *_ids(facts["decision_process"])],
                "decisão mapeada: " + " · ".join(x for x in (who, how) if x))
        elif facts["stakeholders"]:
            add(rule, "PENDING", reason="pessoa citada sem papel na decisão")
        else:
            add(rule, "PENDING", reason="quem decide ainda não identificado")

    def decider_plan(rule: Rule) -> None:
        if not keys:
            if facts["decision_process"]:
                add(rule, "NOT_APPLICABLE", reason="nenhum outro decisor identificado")
            else:
                add(rule, "PENDING", reason="decisor ainda não identificado (E6-R1)")
        elif meetings:
            add(rule, "SATISFIED", [*decision_ids, *meetings], "reunião com o decisor marcada com data e hora",
                date=meetings[0].details["date"], time=meetings[0].details["time"])
        elif seats:
            add(rule, "SATISFIED", [*decision_ids, *seats], "2ª cadeira oferecida ao decisor")
        else:
            add(rule, "PENDING", decision_ids, "decisor identificado, sem reunião marcada nem 2ª cadeira")

    def program_blocks(rule: Rule) -> None:
        seen: dict[str, Signal] = {}
        for s in by_type.get("PROGRAM_BLOCK_MENTIONED", []):
            for b in s.details["blocks"]:
                seen.setdefault(b, s)
        missing = [b for b in sig.PROGRAM_BLOCKS if b not in seen]
        if not missing:
            add(rule, "SATISFIED", list(seen.values()), "pilares, 6 semanas/placar e ritmo do ano apresentados")
        else:
            add(rule, "PENDING", list(seen.values()), "falta apresentar: " + ", ".join(missing))

    def price_presented(rule: Rule) -> None:
        if prices:
            add(rule, "SATISFIED", prices[:1], "investimento apresentado pelo closer")
        elif meetings:
            add(rule, "NOT_APPLICABLE", meetings, "decisor ausente com reunião marcada")
        else:
            add(rule, "PENDING", reason="investimento ainda não apresentado")

    def payment_options(rule: Rule) -> None:
        if not prices:
            add(rule, "PENDING", reason="investimento ainda não apresentado")
            return
        near = [t for t in by_type.get("PAYMENT_TERMS_MENTIONED", []) if t.role == "closer"
                and any(pos(p) - 2 <= pos(t) <= pos(p) + 6 for p in prices)]
        if near:
            add(rule, "SATISFIED", [prices[0], near[0]], "formas de pagamento junto com o valor")
        else:
            add(rule, "PENDING", prices[:1], "valor sem formas de pagamento na mesma janela")

    def second_seat(rule: Rule) -> None:
        add(rule, "SATISFIED", seats[:1], "2ª cadeira mencionada") if seats else add(
            rule, "PENDING", reason="2ª cadeira ainda não mencionada")

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
        # resistance on price/timing ("vou pensar" too): the closer's FIRST reply must be a cause probe.
        events = [(max(pos(i) for i in f["segment_ids"]), f["segment_ids"]) for f in facts["objections"]
                  if f["value"] in ("PRICE_BUDGET", "TIMING_PRIORITY")] + [(pos(s), list(s.segment_ids)) for s in thinks]
        if not events:
            add(rule, "NOT_APPLICABLE", reason="nenhuma resistência de preço/momento/vou pensar")
            return
        probes = {s.segment_id for s in by_type.get("CAUSE_PROBE", []) if s.role == "closer"}
        state, ids = [], []
        for at, seg in events:
            first = sorted(closer_turns_after(at, 1), key=pos)
            # the probe must come before any argument: short acknowledgements ("Entendo.") may precede it
            hit = None
            for sid in first:
                if sid in probes:
                    hit = sid
                    break
                if len(text[sid].split()) > 4:
                    break
            state.append("ok" if hit else ("unknown" if first else "pending"))
            ids += [*seg, *([hit] if hit else [])]
        if "unknown" in state:  # a reply without a known probe phrasing: not judged (v1)
            add(rule, "UNKNOWN", ids, "resposta do closer sem pergunta de causa reconhecida")
        elif "pending" in state:
            add(rule, "PENDING", ids, "resistência ainda sem resposta do closer")
        else:
            add(rule, "SATISFIED", ids, "o closer investigou a causa antes de responder")

    def decision_requested(rule: Rule) -> None:
        if not prices:
            add(rule, "NOT_APPLICABLE", reason="preço ainda não apresentado")
            return
        asks = after("DECISION_ASK", first_price, "closer")
        add(rule, "SATISFIED", [prices[0], asks[0]], "decisão pedida depois do preço") if asks else add(
            rule, "PENDING", prices[:1], "preço apresentado sem pedido explícito de decisão")

    def think_opened(rule: Rule) -> None:
        if not thinks:
            add(rule, "NOT_APPLICABLE", reason="nenhum “vou pensar”")
            return
        probes = [after("CAUSE_PROBE", pos(t), "closer") for t in thinks]
        if all(probes):
            add(rule, "SATISFIED", [*thinks, *(p[0] for p in probes)], "“vou pensar” aberto com pergunta de causa")
        else:
            add(rule, "PENDING", [t for t, p in zip(thinks, probes, strict=True) if not p],
                "“vou pensar” sem pergunta do que precisa pensar")

    def buying_followed(rule: Rule) -> None:
        events = [s.segment_id for s in by_type.get("BUYING_QUESTION", [])] + [
            f["segment_ids"][-1] for f in facts["buying_signals"]]
        if not events:
            add(rule, "NOT_APPLICABLE", reason="nenhum sinal de compra")
            return
        pending, ids = [], []
        for e in sorted(set(events), key=pos):
            window = closer_turns_after(pos(e), 2)
            asks = [s for s in after("DECISION_ASK", pos(e), "closer") if s.segment_id in window]
            ids += [e, *(s.segment_id for s in asks[:1])]
            if not asks:
                pending.append(e)
        add(rule, "PENDING", pending, "sinal de compra sem pedido de decisão em até 2 turnos") if pending else add(
            rule, "SATISFIED", ids, "sinal de compra seguido de pedido de decisão")

    def next_step(rule: Rule) -> None:
        lead = [f for f in facts["next_steps"] if sig.schedule(f["value"]) or any(
            sig.DATE.search(sig.plain(text.get(i, ""))) and sig.TIME.search(sig.plain(text.get(i, "")))
            for i in f["segment_ids"])]
        said = by_type.get("NEXT_STEP_SCHEDULED", [])
        if lead or said:
            first = said[0].details if said else {}
            details = {k: first[k] for k in ("date", "time", "owner") if k in first}
            add(rule, "SATISFIED", [*_ids(lead), *said],
                "próximo passo com data e hora" + (f": {_quote(lead)}" if lead else ""), **details)
        elif facts["next_steps"]:
            add(rule, "PENDING", _ids(facts["next_steps"]), f"próximo passo sem data e hora: {_quote(facts['next_steps'])}")
        else:
            add(rule, "PENDING", reason="próximo passo com data e hora não registrado")

    def closer_owns(rule: Rule) -> None:
        own = [s for s in by_type.get("NEXT_STEP_SCHEDULED", []) if s.details.get("owner") == "closer"]
        add(rule, "SATISFIED", own[:1], "o closer marcou o retorno") if own else add(
            rule, "PENDING", reason="retorno com data/hora marcado pelo closer não registrado")

    def prohibited(rule: Rule) -> None:
        hits = [(sid, p) for sid, t in closer for p in phrase_hits(t, rule.phrases)]
        if hits:
            add(rule, "VIOLATED", [sid for sid, _ in hits],
                "closer disse: " + ", ".join(dict.fromkeys(f"“{p}”" for _, p in hits)))
        else:
            add(rule, "PENDING", reason="nenhuma ocorrência até agora")

    evaluators = {"pain_identified": pain, "impact_explored": impact, "impact_quantified": impact_quantified,
                  "timing_checked_before_price": timing_before_price,
                  "decision_authority_identified": decision_authority, "decider_engagement_plan": decider_plan,
                  "program_blocks_presented": program_blocks, "price_presented": price_presented,
                  "payment_options_presented": payment_options, "second_chair_mentioned": second_seat,
                  "objection_answered": objection_answered, "objection_cause_investigated": objection_cause,
                  "decision_requested": decision_requested, "think_it_over_opened": think_opened,
                  "buying_signal_followed": buying_followed, "next_step_scheduled": next_step,
                  "closer_owns_follow_up": closer_owns, "prohibited_phrase": prohibited}
    skipped = []
    for rule in playbook.rules:
        if rule.evidence_type in evaluators:
            evaluators[rule.evidence_type](rule)
        else:
            skipped.append(rule.id)
    return PlaybookComplianceState(playbook.version, tuple(results), tuple(skipped), tuple(signals),
                                   {r.id: r for r in playbook.rules}, playbook.stages)
