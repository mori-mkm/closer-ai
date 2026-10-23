"""Post-call Brief v0: a grounded presentation of the call's CommercialState (no new interpretation).

    Commercial State = facts        Post-call Brief = presentation of those facts

`build_brief` reads only the state (`CommercialState.view()`) and the session's own recommendation
records. Nothing is re-classified and no LLM is called:
- every listed fact is a state fact, copied with its `segment_ids` (traceable to the transcript);
- the summary is deterministic: fixed pt-BR phrases + the state's values verbatim, so it cannot state
  a fact the state does not have (grounded by construction; `summary_is_grounded` re-checks it);
- risks are deterministic rules over the state, conservative: knowing a stakeholder is not a risk.

Rendered as JSON (`brief.to_json()`) and Markdown (`render_markdown`). Never written to disk here.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from closer_ai.live.commercial_state import FIELDS

SECTIONS = tuple(FIELDS.values())  # pain_points, impacts, stakeholders, ... (CommercialState order)
TITLES = {"pain_points": "Pain", "impacts": "Impact", "stakeholders": "Stakeholders",
          "decision_process": "Decision Process", "buying_signals": "Buying Signals", "objections": "Objections",
          "commercial_terms": "Commercial Terms", "next_steps": "Next Steps"}
ROLE_LABELS = {"mentioned": "citado", "decision_participant": "participa da decisão",
               "final_decision_maker": "dá a palavra final"}
CATEGORY_LABELS = {  # same short labels as the live panel (session.LABELS), lowercase in sentences
    "PRICE_BUDGET": "preço / orçamento", "TIMING_PRIORITY": "timing / prioridade",
    "NEED_VALUE_FIT": "necessidade / valor", "AUTHORITY_INTERNAL_BUY_IN": "decisão / aprovação interna",
    "TRUST_RISK": "confiança / risco", "COMPETITION_EXISTING_SOLUTION": "concorrência / solução atual",
    "IMPLEMENTATION_INTEGRATION": "implementação / integração", "TERMS_PROCESS": "termos / processo de compra",
}


REBUILT_NOTE = ("Runtime reiniciado durante a call: fatos não-objeção reconstruídos da transcrição; objeções e "
                "recomendações anteriores ao restart não estão incluídas.")


@dataclass(frozen=True)
class Risk:
    code: str
    label: str
    segment_ids: tuple[str, ...] = ()  # the facts it rests on; empty for an absence ("nothing recorded")


@dataclass(frozen=True)
class PostCallBrief:
    meeting_id: str
    finalized_at: float
    summary: str
    facts: dict[str, list[dict[str, Any]]]  # CommercialState.view(): value, segment_ids, status, role
    risks: tuple[Risk, ...]
    recommendation_stats: dict[str, Any]
    notes: tuple[str, ...] = field(default=())  # coverage caveats (e.g. rebuilt after a restart)

    def to_json(self) -> dict[str, Any]:
        return {"meeting_id": self.meeting_id, "finalized_at": self.finalized_at, "summary": self.summary,
                **self.facts, "risks": [{**asdict(r), "segment_ids": list(r.segment_ids)} for r in self.risks],
                "recommendation_stats": self.recommendation_stats, "notes": list(self.notes)}


def _q(value: str) -> str:
    return f"“{value}”"


def _stakeholder(f: dict[str, Any]) -> str:
    role = f.get("role")
    return f"{f['value']} ({ROLE_LABELS[role]})" if role in ROLE_LABELS and role != "mentioned" else f["value"]


def build_summary(facts: dict[str, list[dict[str, Any]]]) -> str:
    """Short, factual pt-BR summary: one sentence per non-empty field, values verbatim (quoted when they
    are the lead's words). No coaching, no inference."""
    def vals(name: str) -> str:
        return "; ".join(_q(f["value"]) for f in facts[name])

    parts = []
    if facts["pain_points"]:
        parts.append(f"O lead relatou como dor: {vals('pain_points')}.")
    if facts["impacts"]:
        parts.append(f"Impacto relatado: {vals('impacts')}.")
    if facts["stakeholders"]:
        parts.append("Outras pessoas citadas: " + "; ".join(_stakeholder(f) for f in facts["stakeholders"]) + ".")
    if facts["decision_process"]:
        parts.append(f"Processo de decisão: {vals('decision_process')}.")
    if facts["buying_signals"]:
        parts.append(f"Sinal de compra: {vals('buying_signals')}.")
    if facts["objections"]:
        parts.append("Objeções detectadas: " + "; ".join(CATEGORY_LABELS.get(f["value"], f["value"])
                                                        for f in facts["objections"]) + ".")
    if facts["commercial_terms"]:
        parts.append(f"Termos comerciais mencionados: {vals('commercial_terms')}.")
    if facts["next_steps"]:
        parts.append(f"Próximo passo: {vals('next_steps')}.")
    return " ".join(parts) or "Nenhum fato comercial registrado nesta call."


def summary_is_grounded(summary: str, facts: dict[str, list[dict[str, Any]]]) -> bool:
    """Every quoted span in the summary is a state value (the guard if the summary ever stops being
    pure template: an LLM summary would have to pass this too)."""
    values = {f["value"] for items in facts.values() for f in items}
    return all(q in values for q in re.findall(r"“([^”]*)”", summary))


def derive_risks(facts: dict[str, list[dict[str, Any]]]) -> tuple[Risk, ...]:
    """Conservative, deterministic. A known stakeholder is a fact, never a risk by itself."""
    risks = []
    for f in facts["objections"]:  # the copilot does not track whether it was resolved
        risks.append(Risk("OBJECTION_RAISED", f"objeção levantada: {CATEGORY_LABELS.get(f['value'], f['value'])} "
                                              "(resolução não registrada)", tuple(f["segment_ids"])))
    deciders = [f for f in facts["stakeholders"] if f.get("role") in ("decision_participant", "final_decision_maker")]
    if deciders and not facts["decision_process"]:
        risks.append(Risk("DECISION_PROCESS_NOT_RECORDED",
                          "outra pessoa participa da decisão e o processo de decisão não foi registrado",
                          tuple(i for f in deciders for i in f["segment_ids"])))
    if not facts["next_steps"]:
        risks.append(Risk("NO_NEXT_STEP_RECORDED", "nenhum próximo passo registrado"))
    return tuple(risks)


def recommendation_stats(timings: list[dict[str, Any]], counters: dict[str, int]) -> dict[str, Any]:
    """What the live copilot actually did in this runtime (no success metrics)."""
    by_cat: dict[str, int] = {}
    for t in timings:
        if t.get("outcome") == "RECOMMENDED" and t.get("category"):
            by_cat[t["category"]] = by_cat.get(t["category"], 0) + 1
    return {"recommendations_created": counters.get("recommendations_created", 0),
            "recommendations_by_category": by_cat,
            "categories_detected": sorted({t["category"] for t in timings
                                           if t.get("category") and t.get("outcome") in ("RECOMMENDED", "KEPT")}
                                          | set(by_cat)),
            "analyses_completed": counters.get("analyses_completed", 0)}


def build_brief(meeting_id: str, facts: dict[str, list[dict[str, Any]]], timings: list[dict[str, Any]],
                counters: dict[str, int], finalized_at: float, rebuilt: bool = False) -> PostCallBrief:
    summary = build_summary(facts)
    if not summary_is_grounded(summary, facts):  # cannot happen with the template; fail closed anyway
        summary = "Resumo indisponível (validação de grounding falhou)."
    notes = (REBUILT_NOTE,) if rebuilt else ()
    return PostCallBrief(meeting_id, finalized_at, summary, {k: list(facts[k]) for k in SECTIONS},
                         derive_risks(facts), recommendation_stats(timings, counters), notes)


def _fact_line(name: str, f: dict[str, Any]) -> str:
    if name == "stakeholders":
        text = _stakeholder(f)
    elif name == "objections":
        text = f"{f['value']} ({CATEGORY_LABELS.get(f['value'], f['value'])})"
    else:
        text = f["value"]
    return f"- {text} [{', '.join(f['segment_ids'])}]"


def render_markdown(brief: PostCallBrief) -> str:
    out = ["# Post-call Brief", "", "## Summary", brief.summary]
    for name in SECTIONS:
        out += ["", f"## {TITLES[name]}", *([_fact_line(name, f) for f in brief.facts[name]] or ["- -"])]
    out += ["", "## Risks", *([f"- {r.code}: {r.label}" + (f" [{', '.join(r.segment_ids)}]" if r.segment_ids else "")
                               for r in brief.risks] or ["- -"])]
    s = brief.recommendation_stats
    out += ["", "## Recommendation Stats", f"- recommendations_created: {s['recommendations_created']}",
            f"- categories_detected: {', '.join(s['categories_detected']) or '-'}",
            "- recommendations_by_category: " + (", ".join(f"{k}={v}" for k, v in s["recommendations_by_category"].items())
                                                 or "-")]
    if brief.notes:
        out += ["", "## Notes", *(f"- {n}" for n in brief.notes)]
    return "\n".join(out) + "\n"
