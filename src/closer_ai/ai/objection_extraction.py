"""ObjectionExtractor interface + deterministic reference implementation.

See docs/domain/OBJECTION_MODEL.md for the ObjectionEvent contract this extracts into, and
docs/agents/tasks/objection-event-v0.md for the v0 scope this implements.

Design decisions worth knowing:

- `ObjectionExtractor` is a `Protocol`, not an ABC. There is no shared implementation logic
  between a rule-based extractor and a future Claude/OpenAI-backed one worth putting in a
  common base class (no template method, no shared state) — a Protocol is the minimal seam
  that lets callers depend on the shape (`extract(call) -> list[ObjectionEvent]`) without
  coupling to a concrete base. `@runtime_checkable` is added because it's free (one
  decorator) and lets the eval harness assert conformance with `isinstance(x,
  ObjectionExtractor)` if it wants to, without forcing inheritance on providers.
- `RuleBasedObjectionExtractor` never emits `category="other"`. A keyword matcher only has a
  signal when one of the four named categories' keywords hits some text — it has no
  independent "this is an objection but I don't know which kind" detector (that would require
  a real objection/non-objection classifier, which is exactly what the LLM-backed
  implementation is for, not v0's deterministic baseline). So `other` is reachable through the
  contract's type but not through this implementation; that's intentional, not an oversight.
- Detection is restricted to segments whose `speaker_id` resolves to a `role="lead"`
  participant on `Call.participants`. This is a grounding safeguard: an objection is
  lead-expressed by domain definition (docs/domain/GLOSSARY.md), and without this restriction
  a closer quoting/role-playing the lead's likely pushback ("o lead pode dizer que tá caro")
  would otherwise fire a false positive — a case explicitly flagged by the Evaluator as
  adversarial. Segments from any other role (closer, other, unknown) are skipped outright.
- Same-segment dedup falls out of the control flow rather than needing a post-hoc dedup step:
  for a given segment, each category in `_KEYWORDS` is checked once via `any(...)` over its
  keyword list, so at most one `ObjectionEvent` is constructed per (segment, category) pair no
  matter how many of that category's keywords appear in the segment's text (e.g. "tá caro e
  sem orçamento" only yields one `price` event, not two).
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from closer_ai.domain.objection import ObjectionCategory, ObjectionEvent, derive_objection_id
from closer_ai.normalization.models import Call


@runtime_checkable
class ObjectionExtractor(Protocol):
    """Provider-agnostic seam. A future Claude/OpenAI-backed extractor implements this same
    method signature; callers depend on this interface, never on a concrete implementation.
    """

    def extract(self, call: Call) -> list[ObjectionEvent]:
        ...


# Portuguese keyword/phrase matching per category. Lowercase, substring match against the
# lowercased segment text — deliberately simple (no stemming/lemmatization, no regex word
# boundaries): v0 is a deterministic baseline, not an NLP pipeline. Phrases are listed even
# when they contain a shorter phrase already in the list (e.g. "muito caro" alongside "caro")
# for readability at the source — matching is by substring `in`, so the shorter phrase alone
# would already catch it; the redundancy costs nothing here since dedup is per-category, not
# per-keyword.
_KEYWORDS: dict[ObjectionCategory, tuple[str, ...]] = {
    "price": (
        "caro",
        "muito caro",
        "tá caro",
        "está caro",
        "sem orçamento",
        "não tenho orçamento",
        "fora do orçamento",
        "não cabe no orçamento",
        "não tenho dinheiro",
    ),
    "timing_priority": (
        "não tenho tempo",
        "agora não",
        "depois eu vejo",
        "não é o momento",
        "não é prioridade",
        "mais pra frente",
        "mais para frente",
        "depois a gente vê",
    ),
    "trust_authority": (
        "preciso pensar",
        "falar com meu sócio",
        "falar com minha sócia",
        "falar com meu marido",
        "falar com minha esposa",
        "confiar",
        "não confio",
        "preciso de referências",
        "falar com a equipe",
    ),
    "no_need": (
        "não preciso",
        "não é pra mim",
        "não é para mim",
        "não faz sentido pra mim",
        "não vejo necessidade",
    ),
}


class RuleBasedObjectionExtractor:
    """Deterministic keyword-based reference implementation of `ObjectionExtractor`.

    No network call, no LLM call — the v0 deterministic baseline (see AGENTS.md / the task's
    "não é necessário chamar um provedor de LLM real nesta fase" framing).
    """

    def extract(self, call: Call) -> list[ObjectionEvent]:
        lead_ids = {p.id for p in call.participants if p.role == "lead"}

        events: list[ObjectionEvent] = []
        for segment in call.segments:
            if segment.speaker_id not in lead_ids:
                continue

            text = segment.text.lower()
            for category, keywords in _KEYWORDS.items():
                if not any(keyword in text for keyword in keywords):
                    continue
                objection_id = derive_objection_id(call.call_id, segment.segment_id, category)
                events.append(
                    ObjectionEvent(
                        objection_id=objection_id,
                        call_id=call.call_id,
                        segment_id=segment.segment_id,
                        category=category,
                    )
                )

        return events
