"""Opportunity Detection v1 + Seller Action Arbitration (deterministic, no LLM).

    Commercial State + signals + compliance  ->  Opportunity (playbook OP-xx)  ->  ONE seller action

An opportunity exists only when a playbook OP trigger is in the call (a lead signal, a Commercial State
fact or the objection engine's own decision) and the closer has not covered it yet. Like compliance, the
state is a pure function recomputed when read: idempotent, deduplicated, rebuilt after a restart.

- Dedup key: (OP id, subject). OP-03's subject is the decider ("socio", "pai"; a pronoun joins the
  current one); the other OPs have one subject per call. A repeated trigger adds evidence to the same
  opportunity. Event-like OPs (`reopen`: OP-12, OP-14) open a new one only for a trigger AFTER the
  previous one was resolved; state-like OPs never reopen.
- Status: ACTIVE (trigger, not covered) | RESOLVED (the closer covered it after the trigger) |
  SUPPRESSED (covered before the trigger, or its business knowledge is not CONFIRMED) | EXPIRED (not
  produced in v1). ACTIVE at finalize = "missed" in the brief, never during the call.
- Business safety: the action text comes from the playbook JSON; a variant that names business
  knowledge is used only when that knowledge is CONFIRMED; an OP whose required knowledge is not
  CONFIRMED is SUPPRESSED (internal only, never shown).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from closer_ai.live import signals as sig
from closer_ai.live.playbook import OpportunityDef, Playbook, decider_keys, meeting_matches
from closer_ai.live.signals import Segment, Signal

OPPORTUNITY_STATUSES = ("ACTIVE", "RESOLVED", "SUPPRESSED", "EXPIRED")
RELATED_RULES = {"OP-03": ("E6-R1", "E6-R2"), "OP-12": ("E11-R2",), "OP-14": ("E11-R1", "E11-R4")}


@dataclass
class Opportunity:
    id: str  # "OP-03:socio#1": OP + subject + occurrence
    playbook_op_id: str
    status: str
    priority: int
    subject: str
    title: str
    customer_quote: str
    action: str
    objective: str
    trigger_segment_ids: list[str]
    supporting_segment_ids: list[str] = field(default_factory=list)
    reason: str = ""
    created_sequence: int = 0  # 1-based position of the first trigger line in the call
    resolved_sequence: int | None = None
    resolution_reason: str | None = None

    def __post_init__(self) -> None:
        if self.status not in OPPORTUNITY_STATUSES:
            raise ValueError(f"{self.id}: unknown status {self.status}")
        if self.status == "ACTIVE" and not self.trigger_segment_ids:
            raise ValueError(f"{self.id}: ACTIVE without evidence")

    def view(self) -> dict[str, Any]:
        return {**self.__dict__, "related_rules": list(RELATED_RULES.get(self.playbook_op_id, ())),
                "related_objections": list(SUPERSEDES.get(self.playbook_op_id, ()))}


@dataclass(frozen=True)
class OpportunityState:
    opportunities: tuple[Opportunity, ...]
    not_implemented: dict[str, str]  # OP id -> DEFERRED_LOW_CONFIDENCE | BLOCKED_BUSINESS_CONFIRMATION

    def by_status(self, status: str) -> list[Opportunity]:
        return [o for o in self.opportunities if o.status == status]

    def active(self, hidden: set[str] | frozenset[str] = frozenset()) -> list[Opportunity]:
        """ACTIVE ones by priority (lower first), the newest trigger first on a tie."""
        return sorted((o for o in self.by_status("ACTIVE") if o.id not in hidden),
                      key=lambda o: (o.priority, -o.created_sequence))

    def counters(self) -> dict[str, Any]:
        by_type: dict[str, int] = {}
        for o in self.opportunities:
            by_type[o.playbook_op_id] = by_type.get(o.playbook_op_id, 0) + 1
        return {"opportunities_created": len(self.opportunities),
                "opportunities_active": len(self.by_status("ACTIVE")),
                "opportunities_resolved": len(self.by_status("RESOLVED")),
                "opportunities_suppressed": len(self.by_status("SUPPRESSED")), "opportunities_by_type": by_type}

    def view(self) -> dict[str, Any]:
        return {"opportunities": [o.view() for o in self.opportunities], **self.counters(),
                "not_implemented": dict(self.not_implemented)}


def _action(playbook: Playbook, od: OpportunityDef) -> str:
    """The playbook's action text; a variant only when all the knowledge it names is CONFIRMED."""
    return next((v["action"] for v in od.variants if playbook.confirmed(v["requires_knowledge"])), od.action)


def evaluate_opportunities(playbook: Playbook, facts: dict[str, list[dict[str, Any]]], segments: list[Segment],
                           signals: list[Signal] | None = None) -> OpportunityState:
    signals = sig.extract(segments) if signals is None else signals
    order = {sid: i for i, (sid, _, _) in enumerate(segments)}
    text = {sid: t for sid, _, t in segments}
    keys = decider_keys(facts, signals, order)
    out: list[Opportunity] = []

    def pos(sid: str) -> int:
        return order.get(sid, -1)

    for od in playbook.opportunities:
        if od.implementation != "IMPLEMENTED":
            continue
        # trigger events: (position, segment ids, subject or None)
        events: list[tuple[int, list[str], str | None]] = []
        for t in od.triggers:
            if t == "OBJECTION_AUTHORITY":
                for f in facts["objections"]:
                    if f["value"] == "AUTHORITY_INTERNAL_BUY_IN":
                        ids = [i for i in f["segment_ids"] if i in order]
                        if ids:
                            events.append((max(map(pos, ids)), ids, sig.decision_dependency(text[ids[-1]])[1]))
            elif t == "BUYING_SIGNAL_FACT":
                for f in facts["buying_signals"]:
                    ids = [i for i in f["segment_ids"] if i in order]
                    if ids:
                        events.append((max(map(pos, ids)), ids, None))
            else:
                events += [(pos(s.segment_id), list(s.segment_ids), s.details.get("party"))
                           for s in signals if s.type == t and s.role == "lead"]
        events.sort(key=lambda e: e[0])

        def resolutions(subject: str, od: OpportunityDef = od) -> list[tuple[int, Signal]]:
            found = []
            for r in od.resolved_by:
                if not playbook.confirmed(r.get("requires_knowledge", ())):
                    continue  # e.g. the 2nd chair resolves OP-03 only while it is CONFIRMED knowledge
                for s in signals:
                    if s.type != r["signal"] or ("pillar" in r and s.details.get("pillar") != r["pillar"]):
                        continue
                    if s.type == "DECISION_MEETING_SCHEDULED":
                        if not meeting_matches(s, keys | {subject}):
                            continue
                    elif s.role != "closer":
                        continue
                    found.append((pos(s.segment_id), s))
            return sorted(found, key=lambda x: x[0])

        mine: list[Opportunity] = []
        for at, ids, party in events:
            if od.id == "OP-03":  # one decider = one opportunity; a pronoun joins the current one
                only = next(iter(keys)) if len(keys) == 1 else None
                subject = party or (mine[-1].subject if mine else None) or only or "decisor"
            else:
                subject = "call"
            same = [o for o in mine if o.subject == subject]
            cur = same[-1] if same else None
            if cur and (cur.status != "RESOLVED" or not od.reopen or at < cur.resolved_sequence - 1):
                cur.supporting_segment_ids += [i for i in ids if i not in cur.trigger_segment_ids
                                               and i not in cur.supporting_segment_ids]
                continue
            res = resolutions(subject)
            n = len(same) + 1
            quote = text[ids[-1]]
            o = Opportunity(f"{od.id}:{subject}#{n}", od.id, "ACTIVE", od.priority, subject, od.title, quote,
                            _action(playbook, od), od.objective, list(ids), created_sequence=at + 1,
                            reason=f"gatilho: “{quote}”")
            before = [s for p, s in res if p < at]
            later = [(p, s) for p, s in res if p > at]
            if not playbook.confirmed(od.requires_knowledge):
                o.status, o.reason = "SUPPRESSED", "BLOCKED_BUSINESS_CONFIRMATION: conhecimento ainda não confirmado"
            elif before and not od.reopen:
                o.status, o.reason = "SUPPRESSED", f"já coberto antes do gatilho ({before[0].type} {before[0].segment_id})"
                o.supporting_segment_ids.append(before[0].segment_id)
            elif later:
                p, s = later[0]
                o.status, o.resolved_sequence = "RESOLVED", p + 1
                o.resolution_reason = f"{s.type} [{s.segment_id}]"
                o.supporting_segment_ids.append(s.segment_id)
            mine.append(o)
        out += mine
    not_impl = {od.id: od.implementation for od in playbook.opportunities if od.implementation != "IMPLEMENTED"}
    return OpportunityState(tuple(out), not_impl)


# --- seller action arbitration ------------------------------------------------------------------

@dataclass(frozen=True)
class SellerAction:
    """The ONE thing the seller sees (a presentation layer over a Recommendation or an Opportunity)."""
    source: str  # OBJECTION | OPPORTUNITY
    source_id: str
    priority: int
    title: str
    customer_quote: str
    action: str
    objective: str | None
    segment_ids: tuple[str, ...]

    def view(self) -> dict[str, Any]:
        return {**self.__dict__, "segment_ids": list(self.segment_ids)}


# An objection whose structural opportunity resolved is behind the call: AUTHORITY -> OP-03 (a meeting
# with the decider booked, or the 2nd chair while CONFIRMED). Probes never count (OP-12 "vou pensar"
# -> a cause probe opens the objection, it does not answer it; same for OP-01 cash/payment terms).
SUPERSEDES = {"OP-03": ("AUTHORITY_INTERNAL_BUY_IN",)}


def superseding(category: str, recommendation_sequence: int | None, state: OpportunityState) -> Opportunity | None:
    """The RESOLVED opportunity proving the call moved past the objection said at `recommendation_sequence`
    (1-based line), or None (keep the recommendation: conservative, a neutral line never retires it):
    - its structural OP, open by that line, resolved after it (SUPERSEDES);
    - a buying signal said after it (OP-14) that the closer then turned into a decision ask: the lead
      advanced past the objection, for any category.
    A new objection afterwards is a new recommendation (later line), never retired by this evidence."""
    if recommendation_sequence is None:
        return None
    for o in state.by_status("RESOLVED"):
        if o.resolved_sequence <= recommendation_sequence:
            continue
        if category in SUPERSEDES.get(o.playbook_op_id, ()) and o.created_sequence <= recommendation_sequence:
            return o
        if o.playbook_op_id == "OP-14" and o.created_sequence > recommendation_sequence:
            return o
    return None


def arbitrate(recommendation: dict[str, Any] | None, recommendation_sequence: int | None,
              state: OpportunityState, hidden: set[str] | frozenset[str] = frozenset()) -> SellerAction | None:
    """One seller-facing action, deterministic:
    1. the active objection recommendation (the lead's newest resistance, already grounded guidance);
       exception: a buying signal (priority 1) said AFTER that objection line wins, since the lead moved on
       and the playbook says to ask for the decision right away (E11-R4);
    2. otherwise the top ACTIVE opportunity: OP-14 close > OP-03 decider > OP-12 "vou pensar" >
       OP-01 cash > the pillar/probe OPs (newest first on a tie);
    3. compliance gaps are never seller-facing in v1 (no reliable "when"; Advanced panel only).
    The caller retires a superseded recommendation first (`superseding`), so a card the call moved past
    never comes back when the newer opportunity resolves."""
    top = next(iter(state.active(hidden)), None)
    if recommendation is not None and not (
            top and top.priority == 1 and recommendation_sequence is not None
            and top.created_sequence > recommendation_sequence):
        r = recommendation
        return SellerAction("OBJECTION", f"rec:{r['id']}", 0, r.get("label") or r["category"], r.get("lead_said", ""),
                            r.get("question", ""), r.get("objective"), ())
    if top is None:
        return None
    return SellerAction("OPPORTUNITY", top.id, top.priority, top.title, top.customer_quote, top.action,
                        top.objective, tuple(top.trigger_segment_ids))
