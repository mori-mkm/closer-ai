"""Commercial Events -> Commercial State v0: evidence-backed facts of the ongoing sales call.

Transcript -> CommercialEvent (typed, cites segment ids) -> CommercialState (deduplicated, incremental).

Two sources, no duplicated intelligence:
- OBJECTION_IDENTIFIED comes only from the live objection engine's own decision (`objection_event`);
  it is never re-classified here.
- Every other type comes from one small structured extraction call over the newest lead lines
  (`build_facts_prompt` + `parse_facts`), run off the recommendation's critical path.

Fail-closed grounding (`parse_facts`), deterministic: a fact is kept only if
1. its type is a known non-objection type;
2. it cites segments of this call, including a target (new lead) segment;
3. its value is the lead's own words: an exact (accent/case/punctuation-folded) span of the cited
   segments, so nothing can be paraphrased into existence ("sócio" never becomes "CFO");
4. that span is in a target (new) lead line or in the other speaker's turn right before it (the
   question it answers): an old fact, even from the lead's same turn, cannot be re-extracted as new.
   The one exception is an update of a fact already in the state (a stakeholder's role, "Ele é quem
   dá a palavra final.").
A COMMERCIAL_TERM must name an amount, plan, payment, contract or discount; a DECISION_PROCESS must
name how the decision is made (decide, approve, validate, consult or talk to someone, a step). A stakeholder role beyond
"mentioned" also needs a decision cue in that same scope; otherwise it is
downgraded to "mentioned", never invented.

Nothing here produces advice or touches the recommendation. Not to be confused with
`closer_ai.domain.commercial_state` (post-call: Call -> current match -> Deal -> Outcome).
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from closer_ai.normalization.models import Call

# event type -> CommercialState field
FIELDS = {
    "PAIN_IDENTIFIED": "pain_points",
    "IMPACT_IDENTIFIED": "impacts",
    "STAKEHOLDER_IDENTIFIED": "stakeholders",
    "DECISION_PROCESS_IDENTIFIED": "decision_process",
    "BUYING_SIGNAL_DETECTED": "buying_signals",
    "OBJECTION_IDENTIFIED": "objections",
    "COMMERCIAL_TERM_MENTIONED": "commercial_terms",
    "NEXT_STEP_IDENTIFIED": "next_steps",
}
EXTRACTED_TYPES = tuple(t for t in FIELDS if t != "OBJECTION_IDENTIFIED")  # the objection engine owns the rest
ROLES = ("mentioned", "decision_participant", "final_decision_maker")  # weakest -> strongest
MAX_VALUE_WORDS = 10

# Role cues (accent-folded). A role is kept only when the call itself says it.
_FINAL_CUE = re.compile(r"\b(palavra final|bate o martelo|quem (decide|assina|manda)|decide|decisao final|assina)\b")
_PARTICIPANT_CUE = re.compile(r"\b(decis\w*|decid\w*|aprov\w*|valid\w*|particip\w*|assin\w*|consult\w*|"
                              r"palavra final|martelo)\b")
# A COMMERCIAL_TERM must name something concrete: an amount, a plan, a payment, a contract, a discount.
# Without it, "achei caro" (an objection, owned by the objection engine) is not a term.
# ponytail: word list, high precision by design; widen when real calls show missed terms.
_TERM_CUE = re.compile(r"(\d|\b(mil|reais|real|rs|plano|planos|contrato|pagamento|pagar|pago|pagamos|pagam|parcel\w*|"
                       r"desconto|mensal|anual|mensalidade|licen\w*|boleto|cartao|pix|fidelidade|multa|"
                       r"por mes|por ano|por usuario|assinatura)\b)")
# A DECISION_PROCESS must say how the decision is made: deciding, approving, validating, consulting or
# talking to someone, a decision body or a step. "Agora não é o momento" (a timing objection) is not one.
# ponytail: word list, high precision by design; widen when real calls show missed decision steps.
_DECISION_CUE = re.compile(r"\b(decid\w*|decis\w*|aprov\w*|valid\w*|consult\w*|assin\w*|palavra final|martelo|"
                           r"(falar|conversar|alinhar|ver|checar|levar isso|passar isso) com|diretoria|conselho|"
                           r"comite|juridico|compras|licitac\w*|cotac\w*|proposta formal)\b")
# Leading words that do not change which fact it is: "meu sócio" == "sócio" == "o sócio".
_DETERMINERS = {"o", "a", "os", "as", "um", "uma", "meu", "minha", "meus", "minhas", "nosso", "nossa",
                "nossos", "nossas", "seu", "sua", "tambem", "sim", "e"}


def fold(text: str) -> str:
    """Lowercase, no accents, punctuation -> spaces, single spaces."""
    t = unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", t).split())


def fact_key(value: str) -> str:
    """Dedup key: folded words without determiners/fillers. v0 = exact key (paraphrases stay separate)."""
    return " ".join(w for w in fold(value).split() if w not in _DETERMINERS)


def _display(value: str) -> str:
    """The value as shown: the lead's words, minus leading determiners ("meu sócio" -> "sócio")."""
    words = value.strip(" .,!?;:\"'“”").split()
    while len(words) > 1 and fold(words[0]) in _DETERMINERS:
        words.pop(0)
    while len(words) > 1 and fold(words[-1]) in _DETERMINERS:
        words.pop()
    return " ".join(words)


@dataclass(frozen=True)
class CommercialEvent:
    event_type: str
    value: str
    segment_ids: tuple[str, ...]  # canonical evidence
    source_role: str  # who said it: lead (v0 extracts lead lines only)
    status: str  # OBSERVED (grounded extraction) | CONFIRMED (the objection engine's decision)
    stakeholder_role: str | None = None  # STAKEHOLDER_IDENTIFIED only: one of ROLES

    @property
    def key(self) -> str:
        return self.value if self.event_type == "OBJECTION_IDENTIFIED" else fact_key(self.value)


@dataclass
class Fact:
    value: str
    segment_ids: list[str]  # every evidence ever seen for it, in call order; never removed
    status: str
    role: str | None = None  # stakeholders only

    def view(self) -> dict[str, Any]:
        out = {"value": self.value, "segment_ids": list(self.segment_ids), "status": self.status}
        if self.role is not None:
            out["role"] = self.role
        return out


@dataclass
class CommercialState:
    """Facts by field; each field maps the dedup key -> one Fact (insertion order = first seen)."""

    facts: dict[str, dict[str, Fact]] = field(default_factory=lambda: {f: {} for f in FIELDS.values()})
    events: list[dict[str, Any]] = field(default_factory=list)  # accepted events + what they did (audit)

    def get(self, event: CommercialEvent) -> Fact | None:
        return self.facts[FIELDS[event.event_type]].get(event.key)

    def apply(self, event: CommercialEvent, order: dict[str, int] | None = None) -> str:
        """ADDED | UPDATED (new evidence or a stronger role) | UNCHANGED. Evidence is only ever added."""
        bucket = self.facts[FIELDS[event.event_type]]
        fact = bucket.get(event.key)
        if fact is None:
            bucket[event.key] = Fact(_display(event.value) if event.event_type != "OBJECTION_IDENTIFIED"
                                     else event.value, list(event.segment_ids), event.status,
                                     event.stakeholder_role)
            result = "ADDED"
        else:
            new_ids = [i for i in event.segment_ids if i not in fact.segment_ids]
            stronger = (event.stakeholder_role is not None and fact.role is not None
                        and ROLES.index(event.stakeholder_role) > ROLES.index(fact.role))
            if stronger:
                fact.role = event.stakeholder_role
            if new_ids:
                fact.segment_ids += new_ids
                if order:
                    fact.segment_ids.sort(key=lambda i: order.get(i, 1 << 30))
            result = "UPDATED" if stronger or new_ids else "UNCHANGED"
        self.events.append({"event_type": event.event_type, "value": event.value,
                            "segment_ids": list(event.segment_ids), "source_role": event.source_role,
                            "status": event.status, "result": result,
                            **({"stakeholder_role": event.stakeholder_role} if event.stakeholder_role else {})})
        return result

    def view(self) -> dict[str, list[dict[str, Any]]]:
        return {name: [f.view() for f in bucket.values()] for name, bucket in self.facts.items()}

    def __len__(self) -> int:
        return sum(len(b) for b in self.facts.values())


def objection_event(category: str, segment_ids: tuple[str, ...] | list[str]) -> CommercialEvent:
    """The objection engine's own decision as a commercial event (no re-classification)."""
    return CommercialEvent("OBJECTION_IDENTIFIED", category, tuple(segment_ids), "lead", "CONFIRMED")


# --- extraction -------------------------------------------------------------------------------------

FACTS_SCHEMA = {  # Ollama structured output; types/roles are enums (closed v0 vocabulary)
    "type": "object",
    "properties": {"events": {"type": "array", "items": {
        "type": "object",
        "properties": {"event_type": {"type": "string", "enum": list(EXTRACTED_TYPES)},
                       "value": {"type": "string"},
                       "segment_ids": {"type": "array", "items": {"type": "string"}},
                       "stakeholder_role": {"type": "string", "enum": ["none", *ROLES]}},
        "required": ["event_type", "value", "segment_ids", "stakeholder_role"]}}},
    "required": ["events"],
}


def build_facts_prompt(call: Call, target_segment_ids: tuple[str, ...]) -> str:
    roles = {p.id: p.role for p in call.participants}
    lines = "\n".join(f"[{s.segment_id} | {roles.get(s.speaker_id, 'unknown')}]\n{s.text}" for s in call.segments)
    targets = "\n".join(f"[{s.segment_id}] {s.text}" for s in call.segments if s.segment_id in target_segment_ids)
    return f"""COMMERCIAL FACTS TASK

You record commercial facts that the LEAD states in a live sales call (Brazilian Portuguese). You never
give advice and never judge the call.

CALL (oldest first; [segment_id | role]):
{lines}

TARGET (what the lead just said):
{targets}

Record ONLY facts the lead states in the TARGET segment(s); segment_ids always include the target id.
Earlier segments are context: use them to understand short answers (for example "Sim, meu sócio." answering
who takes part in the decision) and references ("ele", "isso"). Never record a fact said only in earlier
segments; it was already recorded.

Fact types (use only these):
- PAIN_IDENTIFIED: a problem or limitation in how they work today.
- IMPACT_IDENTIFIED: a consequence of a problem: time, money, people, errors or sales lost (losing time
  is an IMPACT, not a PAIN).
- STAKEHOLDER_IDENTIFIED: a person or role other than the lead who takes part in the purchase or decision.
- DECISION_PROCESS_IDENTIFIED: how the decision is made: who must approve, validate or be consulted,
  steps, criteria, a decision deadline ("decidimos até sexta"). Postponing ("agora não é o momento") is an
  objection, not a decision process.
- BUYING_SIGNAL_DETECTED: explicit intent to buy, start or move forward ("quero começar", "vamos fechar").
  Liking the proposal ("gostei") is not a buying signal.
- COMMERCIAL_TERM_MENTIONED: a price, plan, payment, contract or discount term stated by the lead.
- NEXT_STEP_IDENTIFIED: a concrete next action the lead proposes or agrees to (meeting, proposal, test,
  date). Agreeing to a date or meeting ("Fechado, quinta às 10.") is a NEXT_STEP.

Rules:
- value: the lead's own words copied EXACTLY from the cited segments, a short span (at most
  {MAX_VALUE_WORDS} words). Never paraphrase, summarize, translate or add words.
- segment_ids: the segments that support the fact; always include a target segment. Add the closer's
  question only when the target is a short answer to it.
- stakeholder_role: for STAKEHOLDER_IDENTIFIED only, else "none". "final_decision_maker" only if the
  call says this person decides or has the final word; "decision_participant" only if the call says they
  take part in, approve or validate the decision; otherwise "mentioned". Never infer a job title or an
  authority that was not said.
- Objections (too expensive, not now, unsure it helps) are handled elsewhere: never record them, in any
  type ("achei caro" is not an IMPACT nor a COMMERCIAL_TERM), except a stakeholder and a decision step
  they name ("Preciso validar com meu sócio." gives STAKEHOLDER "meu sócio" and DECISION_PROCESS
  "validar com meu sócio").
- Neutral information (team size, tools they use, company description, small talk, "entendi", "ok")
  is not a commercial fact unless the lead states it as a problem, an impact or an intent.
- If the target states no such fact, return {{"events": []}}.

Return ONLY JSON: {{"events": [{{"event_type": "...", "value": "...", "segment_ids": ["..."],
"stakeholder_role": "none"}}]}}"""


def _has(text: str, words: str) -> bool:
    """Whole-word span match on folded text ("ca" is not in "caro")."""
    return f" {words} " in f" {text} "


def _turn_scope(call: Call, targets: set[str]) -> set[str]:
    """The target segments + the other speaker's turn right before each target turn (the question
    being answered). Earlier lines of the lead's own turn are not in scope: "Sim, meu sócio." followed by
    "Fazemos tudo manualmente." must not re-cite the stakeholder as said again."""
    turns: list[list[str]] = []
    last_speaker = None
    for seg in sorted(call.segments, key=lambda s: s.segment_index):
        if turns and seg.speaker_id == last_speaker:
            turns[-1].append(seg.segment_id)
        else:
            turns.append([seg.segment_id])
        last_speaker = seg.speaker_id
    hit = [i for i, t in enumerate(turns) if targets & set(t)]
    if not hit:
        return set()
    return set(targets) | {sid for i in hit if i for sid in turns[i - 1]}  # per target turn (rebuild chunks)


def parse_facts(call: Call, target_segment_ids: tuple[str, ...], response: Any,
                state: CommercialState) -> tuple[list[CommercialEvent], list[dict[str, Any]]]:
    """Model answer -> grounded events + rejections (reason per dropped item). Raises TypeError when
    the answer is not the contract's shape at all."""
    if not isinstance(response, dict) or not isinstance(response.get("events"), list):
        raise TypeError("facts response must be {'events': [...]}")
    text = {s.segment_id: fold(s.text) for s in call.segments}
    targets = set(target_segment_ids)
    scope = _turn_scope(call, targets)
    scope_text = " ".join(text[i] for i in sorted(scope, key=list(text).index))
    target_text = " ".join(text[i] for i in text if i in targets)
    accepted: list[CommercialEvent] = []
    rejected: list[dict[str, Any]] = []

    def reject(item: Any, reason: str) -> None:
        rejected.append({"reason": reason, "item": item if isinstance(item, dict) else str(item)[:80]})

    for item in response["events"]:
        if not isinstance(item, dict):
            reject(item, "NOT_AN_OBJECT")
            continue
        etype, value, ids = item.get("event_type"), item.get("value"), item.get("segment_ids")
        if etype not in EXTRACTED_TYPES:
            reject(item, "UNKNOWN_TYPE")
            continue
        if not isinstance(value, str) or not fold(value) or len(value.split()) > MAX_VALUE_WORDS:
            reject(item, "BAD_VALUE")
            continue
        if not isinstance(ids, list) or not all(isinstance(i, str) and i in text for i in ids):
            reject(item, "BAD_EVIDENCE")  # not a list of this call's segment ids
            continue
        v = fold(value)
        # Evidence = what the model cited + every target segment that contains the value itself (the
        # 8B model often cites only the earlier mention of the same fact).
        ids = list(dict.fromkeys([*ids, *(i for i in target_segment_ids if _has(text[i], v))]))
        if not ids or not _has(" ".join(text[i] for i in ids), v):
            reject(item, "UNGROUNDED")  # not the lead's words in the cited segments
            continue
        if etype == "COMMERCIAL_TERM_MENTIONED" and not _TERM_CUE.search(v):
            reject(item, "NOT_A_TERM")
            continue
        if etype == "DECISION_PROCESS_IDENTIFIED" and not _DECISION_CUE.search(v):
            reject(item, "NOT_A_DECISION_STEP")
            continue
        role = None
        if etype == "STAKEHOLDER_IDENTIFIED":
            role = item.get("stakeholder_role") if item.get("stakeholder_role") in ROLES else "mentioned"
            if role == "final_decision_maker" and not _FINAL_CUE.search(scope_text):
                role = "decision_participant"
            if role == "decision_participant" and not _PARTICIPANT_CUE.search(scope_text):
                role = "mentioned"
        event = CommercialEvent(etype, value.strip(), tuple(ids), "lead", "OBSERVED", role)
        if not _has(scope_text, v) or not targets & set(ids):
            # Only in older context: allowed solely as an update of a known stakeholder whose stronger
            # role is stated now ("Ele é quem dá a palavra final."), with that target line as its new
            # evidence; anything else is a replay of an old fact.
            known = state.get(event)
            cue = _FINAL_CUE if role == "final_decision_maker" else _PARTICIPANT_CUE
            if not (known and role and known.role and ROLES.index(role) > ROLES.index(known.role)
                    and cue.search(target_text)):
                reject(item, "NOT_IN_TARGET")
                continue
            event = CommercialEvent(etype, value.strip(), tuple(dict.fromkeys([*ids, *(
                i for i in target_segment_ids if cue.search(text[i]))])), "lead", "OBSERVED", role)
        accepted.append(event)
    return accepted, rejected
