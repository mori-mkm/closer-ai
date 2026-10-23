"""Live sales session: incremental utterances -> rolling window -> at most one recommendation.

See docs/product/LIVE_MEET_COPILOT_V0.md. Reuses the existing pieces unchanged: the E0/E1/E2
classifier (`classify_call`), exact-category retrieval + CommercialGuidance (`guide_episode`) and its
fail-closed grounding. What is new here is only the live policy around them:

- Rolling context: only the last `window_seconds` (at most `max_window_utterances`) go to the model.
- Trigger: a new complete lead utterance, long enough and not a repeat of the last analyzed one.
- Emission is conservative (the classifier over-detects): a recommendation needs a valid
  classifier run (after dropping context cited from before the anchor), a PRESENT category other than OTHER, anchored on a lead utterance that is new
  since the previous analysis, a single candidate category, the lead's own words for a category
  in `CORROBORATION`, and GUIDED (grounded) guidance.
  Anything else is NO_RECOMMENDATION; showing nothing beats showing a false objection.
- One recommendation at a time: same category inside the cooldown keeps the current one (no LLM
  guidance call); another category, or the same after the cooldown, replaces it; it expires after
  `ttl_seconds` or when dismissed.
- Latency is recorded per analysis as technical timings only (no transcript text).
"""
from __future__ import annotations

import dataclasses
import difflib
import re
import threading
import time
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from closer_ai.ai.objection_classifier import (
    Arm,
    ClassificationProvider,
    EpisodePrediction,
    MalformedResponseError,
    classify_call,
    validate_predictions,
)
from closer_ai.ai.objection_guidance import ObjectionKnowledge, _generic, guide_episode
from closer_ai.ai.ollama_provider import OllamaError
from closer_ai.demo.analyze_call import InputTooLargeError
from closer_ai.live.commercial_state import (
    FACTS_SCHEMA,
    CommercialEvent,
    CommercialState,
    build_facts_prompt,
    objection_event,
    parse_facts,
)
from closer_ai.live.playbook import PlaybookComplianceState, evaluate, load_playbook
from closer_ai.live.post_call_brief import PostCallBrief, build_brief
from closer_ai.normalization.models import Call, Participant, TranscriptSegment

LABELS = {  # short pt-BR label for the panel; the category itself is always shown too
    "PRICE_BUDGET": "Preço / orçamento",
    "TIMING_PRIORITY": "Timing / prioridade",
    "NEED_VALUE_FIT": "Necessidade / valor",
    "AUTHORITY_INTERNAL_BUY_IN": "Decisão / aprovação interna",
    "TRUST_RISK": "Confiança / risco",
    "COMPETITION_EXISTING_SOLUTION": "Concorrência / solução atual",
    "IMPLEMENTATION_INTEGRATION": "Implementação / integração",
    "TERMS_PROCESS": "Termos / processo de compra",
}


MOVE_LABELS = {  # seller response codes (taxonomy v0.1) -> the action line of the panel
    "ACKNOWLEDGE_VALIDATE": "Reconheça e valide", "CLARIFY": "Esclareça antes de responder",
    "PROBE_EXPLORE": "Explore antes de defender", "ADDRESS_EXPLAIN": "Responda e explique",
    "PROVIDE_EVIDENCE": "Traga evidência", "REFRAME": "Reenquadre", "NEGOTIATE_OFFER_ALTERNATIVE": "Negocie uma alternativa",
    "DEFER_FOLLOW_UP": "Combine o próximo passo", "CONFIRM_UNDERSTANDING": "Confirme o entendimento",
    "IGNORE_CHANGE_TOPIC": "Não force; mude de assunto",
}
OBJECTIVES = {  # the same codes as the seller-facing "Objetivo: ..." line (small, under the suggestion)
    "ACKNOWLEDGE_VALIDATE": "reconhecer e validar", "CLARIFY": "esclarecer antes de responder",
    "PROBE_EXPLORE": "explorar antes de defender", "ADDRESS_EXPLAIN": "responder e explicar",
    "PROVIDE_EVIDENCE": "trazer evidência", "REFRAME": "reenquadrar", "NEGOTIATE_OFFER_ALTERNATIVE": "negociar uma alternativa",
    "DEFER_FOLLOW_UP": "combinar o próximo passo", "CONFIRM_UNDERSTANDING": "confirmar o entendimento",
    "IGNORE_CHANGE_TOPIC": "não forçar; mudar de assunto",
}


def _action(code: str | None, guidance: str, question: str) -> str:
    """Panel action line: the move's code label + its guidance, unless the guidance is the question itself."""
    label = MOVE_LABELS.get(code or "", "")
    detail = "" if guidance.strip(' "“”') == question.strip(' "“”') else guidance
    return f"{label}: {detail}" if label and detail else label or detail


def _first_sentence(text: str) -> str:
    end = min((i for i in (text.find(". "), text.find("! ")) if i >= 0), default=-1)
    return text[:end + 1] if end >= 0 else text


# Emission gate for categories measured to over-detect live (benchmark + live probe, Oct 2026): the
# lead's own words must mention putting the solution in place. Without it ("a gente perde tempo com
# isso" = pain, not resistance) the episode is not shown.
# ponytail: stem list, misses paraphrases (recall ceiling); replace with a measured precision fix.
CORROBORATION: dict[str, re.Pattern[str]] = {  # matched on the accent-folded objection words
    "IMPLEMENTATION_INTEGRATION": re.compile("|".join(map(re.escape, (
        "implant", "implement", "integr", "instal", "configur", "migr", "treina", "aplicar", "tocar isso",
        "gente pra", "equipe pra", "equipe nao", "formato", "presencial", "adapt")))),
}  # + AUTHORITY_INTERNAL_BUY_IN, below


# Live category normalization (real Meet, Oct 2026): after noise and a pain line, E1 labeled "Gostei da
# proposta, mas achei muito caro." NEED_VALUE_FIT (its definition includes "the benefit does not pay
# off") while its own summary said "too expensive". PRICE_BUDGET wins over NEED_VALUE_FIT only when the
# lead's objection words themselves are unambiguously about money, and never when they also deny the
# need or fit (mixed = ambiguous = left as classified). Matched on accent-folded text, whole words.
# ponytail: word list, high precision / low recall by design; replace with a measured classifier fix.
_PRICE_WORDS = re.compile(r"\b(caro|caros|carissim[oa]s?|preco|precos|orcamento|orcamentos|budget|custo|custos"
                          r"|custa|custam|custar|verba)\b")
_NEED_DENIAL = re.compile(r"\b(nao (preciso|precisamos|resolve|serve|faz sentido|vejo valor|compensa)"
                          r"|desnecessari\w*)\b")


def price_override(category: str | None, objection_text: str) -> str | None:
    """PRICE_BUDGET when NEED_VALUE_FIT rests on explicit price words alone; otherwise the category unchanged."""
    text = _fold(objection_text)
    if category == "NEED_VALUE_FIT" and _PRICE_WORDS.search(text) and not _NEED_DENIAL.search(text):
        return "PRICE_BUDGET"
    return category


# Live category normalization (real Meet, Oct 2026): Meet emitted "Preciso falar com o meu sócio antes"
# ("de fechar." came as a separate, too-short line) and E1 labeled it TIMING_PRIORITY ("antes" reads as
# postponing) while its own summary said "needs to speak with their partner before proceeding";
# reproduced 4/4. AUTHORITY wins over TIMING_PRIORITY only when the objection words state that a named
# third party must be consulted, must approve or decides; a role word alone ("meu sócio gostou") never
# counts, and any explicit time marker ("mês que vem", "viajando", "novembro") leaves it as classified.
# ponytail: phrase patterns, high precision / low recall by design; replace with a measured classifier fix.
_THIRD_PARTY = (r"(?:o |a |os |as )?(?:meu |minha |meus |minhas |nosso |nossa |nossos |nossas )?"
                r"(?:socios?|socias?|chefes?|gerentes?|diretor(?:es|a|as)?|diretoria|conselho|board|presidente|ceo|cfo|"
                r"dono|dona|donos|patrao|superior|gestor(?:a|es)?|marido|esposa|esposo|mulher|financeiro|juridico|"
                r"compras|investidor(?:es)?)")
_AUTHORITY_DEPENDENCY = re.compile(
    r"\b(?:"
    r"(?:falar|conversar|consultar|validar|alinhar|checar|confirmar|discutir|ver|levar isso|passar isso|aprovar)"
    rf"(?: isso| isto| a proposta| essa proposta)? (?:com|pra|para|por|pelo|pela) {_THIRD_PARTY}"
    rf"|(?:quem|que) (?:decide|aprova|assina|bate o martelo)\b.*\b(?:e|eh|sao) {_THIRD_PARTY}"
    rf"|{_THIRD_PARTY} (?:e|eh|sao) quem (?:decide|aprova|assina|bate o martelo)"
    rf"|(?:aprovacao|autorizacao|aval|ok|decisao) (?:do|da|dos|das) {_THIRD_PARTY}"
    rf"|(?:depende|dependo|dependemos) (?:do|da|dos|das) {_THIRD_PARTY}"
    r")\b")
_TIME_MARKER = re.compile(
    r"\b(mes que vem|semana que vem|ano que vem|proxim[oa] (mes|semana|ano|trimestre)|viajando|de ferias|so volta"
    r"|janeiro|fevereiro|marco|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro"
    r"|safra|colheita|fim do ano|final do ano|depois d[aeo]s? (feriado|ferias|carnaval|natal))\b")


def authority_override(category: str | None, objection_text: str) -> str | None:
    """AUTHORITY_INTERNAL_BUY_IN when TIMING_PRIORITY rests on an explicit third-party decision dependency."""
    text = _fold(objection_text)
    if category == "TIMING_PRIORITY" and _AUTHORITY_DEPENDENCY.search(text) and not _TIME_MARKER.search(text):
        return "AUTHORITY_INTERNAL_BUY_IN"
    return category


# Emission gate for AUTHORITY_INTERNAL_BUY_IN (real Meet + qwen3 matrix, Oct 2026): E1 labels a short answer
# to a discovery question ("Quem participa da decisão?" -> "Sim, meu sócio.") AUTHORITY 6/6. Naming a
# stakeholder is a fact for the Commercial State, not an objection. An authority objection needs the lead's
# own words to state a dependency that blocks moving forward: an obligation to consult/get approval
# ("preciso falar com", "precisa aprovar"), not being able to decide alone ("não posso decidir"), or moving
# only after someone's approval ("depois da aprovação"). Same mechanism as the IMPLEMENTATION gate.
# ponytail: phrase patterns, high precision by design; paraphrases without these verbs are not shown.
_AUTHORITY_BLOCKING = re.compile(
    r"\b(?:"
    r"(?:precis\w*|tenho que|temos que|tem que|teria que|teriamos que|ter que|vou|vamos|deixa eu)"
    r" (?:de )?(?:falar|conversar|consultar|validar|alinhar|checar|confirmar|discutir|ver|levar|passar|mostrar"
    r"|apresentar|aprovar|autorizar|liberar|assinar|dar o (?:ok|aval)|pedir)\b"
    r"|(?:nao|nem) (?:posso|podemos|consigo|conseguimos|da pra|tenho como|temos como|decido|fecho|assino)"
    r"(?: \w+)? (?:decidir|fechar|assinar|aprovar|avancar|seguir|bater o martelo|sozinh\w*)"
    r"|(?:decid\w*|fech\w*|assin\w*|resolv\w*) (?:\w+ )?sozinh\w*"
    r"|(?:depois|antes) d[aeo]s? (?:aprovacao|autorizacao|aval|ok|validacao|liberacao|sinal verde)"
    r"|(?:depende|dependo|dependemos|dependem) (?:do|da|dos|das|de)"
    r"|(?:aprovacao|autorizacao|aval|ok) (?:do|da|dos|das) "
    r")")
CORROBORATION["AUTHORITY_INTERNAL_BUY_IN"] = _AUTHORITY_BLOCKING


# Deterministic fast path (P1 latency): for a few unambiguous phrasings the LLM classifier call (~9-10 s,
# mostly output tokens) is replaced by a rule. It only proposes the category of ONE new lead line; the rest
# of the live policy (validation, anchoring, normalizations, CORROBORATION gates, cooldown, retrieval,
# guidance + grounding) runs unchanged. Anything not clearly one category -> the LLM, as before.
# ponytail: phrase patterns, precision over recall by design (PRICE_BUDGET, AUTHORITY_INTERNAL_BUY_IN only).
_FAST_PRICE = re.compile(
    r"\b(?:(?:achei|acho|achamos|ta|esta|ficou|ficaram|fica|e|eh|sao|muito|bem|meio|bastante|um pouco|tao)"
    r" (?:\w+ )?(?:caro|caros|carissimo|carissima)|caro demais|caro pra (?:gente|nos|mim)"
    r"|(?:nao|nem) (?:tenho|temos|tem|ha) (?:\w+ )?(?:orcamento|verba|budget)"
    r"|(?:nao|nem) cabe no (?:\w+ )?orcamento|(?:acima|fora|alem) d[oa] (?:\w+ )?orcamento"
    r"|sem (?:orcamento|verba)|estourou o (?:\w+ )?orcamento)\b")
_FAST_AUTHORITY = re.compile(
    r"\b(?:(?:precis\w*|tenho que|temos que|vou ter que|vamos ter que) (?:falar|conversar|consultar|validar|alinhar|ver)"
    rf" com (?:um |uma )?{_THIRD_PARTY}"
    r"|(?:nao|nem) (?:posso|podemos|consigo|conseguimos) (?:decidir|fechar|assinar) (?:isso |isto |nada )?sozinh\w*"
    rf"|{_THIRD_PARTY} (?:precisa|tem que|vai ter que) (?:aprovar|validar|autorizar|dar o (?:ok|aval))"
    r"|(?:so|somente) (?:consigo|posso|podemos|conseguimos) (?:avancar|seguir|fechar) depois d[aeo]s? "
    r"(?:aprovacao|autorizacao|aval|ok)"
    r")\b")
# Never fast-path these: a negated price ("não achei caro"), price + acceptance ("caro, mas vale"), a
# question, a comparison with someone else's price, or two categories at once (timing/need words).
_FAST_PRICE_NEGATED = re.compile(r"\b(?:nao|nem|nunca) (?:\w+ )?(?:\w+ )?(?:caro|caros|carissim\w*|acima)\b")
_FAST_BLOCKERS = re.compile(
    r"\?|\bmas (?:vale|compensa|faz sentido|tudo bem|ok|cabe)\b|\b(?:concorrente|outra ferramenta|outro fornecedor"
    r"|o outro|a outra)\b|\b(?:nao sei se|precisa disso|precisamos disso|nao resolve|nao faz sentido|barato)\b")


def fast_path_category(text: str) -> str | None:
    """The one category this lead line states unambiguously, or None (-> the LLM classifier)."""
    t = _fold(text)
    if _FAST_BLOCKERS.search(t) or _TIME_MARKER.search(t):
        return None
    price = bool(_FAST_PRICE.search(t)) and not _FAST_PRICE_NEGATED.search(t)
    authority = bool(_FAST_AUTHORITY.search(t)) and bool(_AUTHORITY_BLOCKING.search(t))
    if price == authority:  # neither, or both (mixed = ambiguous)
        return None
    return "PRICE_BUDGET" if price else "AUTHORITY_INTERNAL_BUY_IN"


@dataclass(frozen=True)
class LiveUtterance:
    meeting_id: str
    speaker: str  # as captioned; "unknown" when the adapter could not read it
    role: str  # closer | lead | unknown (never guessed from text)
    text: str
    timestamp: float  # epoch seconds, from the caption source
    sequence: int
    received_at: float  # epoch seconds, when the runtime got it (latency start)
    caption_changed_at: float | None = None  # browser: last time the caption text changed (before emission)


@dataclass(frozen=True)
class LiveConfig:
    window_seconds: float = 90.0
    max_window_utterances: int = 12
    min_lead_chars: int = 12
    repeat_similarity: float = 0.85  # a lead utterance this similar to the last analyzed one is skipped
    cooldown_seconds: float = 25.0
    ttl_seconds: float = 90.0
    arm: Arm = "E1"
    # Deterministic fast path for unambiguous PRICE / AUTHORITY lines (skips the LLM classifier only).
    fast_path: bool = True
    # Commercial facts extraction (Commercial State): on/off, context lines before the first new lead
    # line, and lines per call.
    commercial_facts: bool = True
    # Background worker: extract only after this much silence (no new utterance), so the extra call does
    # not hold Ollama while the conversation is flowing (the next lead line would wait behind it) and
    # several lines go in one call.
    facts_idle_seconds: float = 4.0
    facts_context_utterances: int = 6
    facts_chunk_utterances: int = 8


@dataclass
class Recommendation:
    id: int
    category: str
    move: str
    rationale: str
    question: str
    grade: str
    shown_at: float
    state: str = "ACTIVE"  # ACTIVE | EXPIRED | REPLACED | DISMISSED
    # Retrieval provenance, shown in the debug panel: proves which knowledge unit/move was used.
    knowledge_unit: str | None = None
    move_id: str | None = None
    move_code: str | None = None
    lead_said: str = ""  # the lead's objection words, verbatim from the captions ("Cliente disse")

    def view(self) -> dict[str, Any]:
        return {"state": self.state, "id": self.id, "category": self.category,
                "label": LABELS.get(self.category, self.category), "move": self.move,
                "lead_said": self.lead_said, "objective": OBJECTIVES.get(self.move_code or ""),
                "rationale": self.rationale, "question": self.question, "grade": self.grade,
                # only GUIDED guidance becomes a Recommendation, so grounding passed by construction
                "knowledge_unit": self.knowledge_unit, "move_id": self.move_id, "move_code": self.move_code,
                "grounding": "VALID"}


def _ms(seconds: float) -> int:
    return round(seconds * 1000)


def _norm(text: str) -> str:
    return " ".join(text.lower().split())


def _fold(text: str) -> str:
    return unicodedata.normalize("NFKD", _norm(text)).encode("ascii", "ignore").decode()


def _usage(provider: Any) -> dict[str, Any]:
    inner = getattr(provider, "inner", provider)  # ContextGuard wraps the Ollama provider
    u = getattr(inner, "last_usage", {}) or {}
    out = {"prompt_tokens": u.get("prompt_eval_count"), "output_tokens": u.get("eval_count")}
    if u.get("done_reason"):  # "length" = generation cut by the context window (truncated output)
        out["done_reason"] = u["done_reason"]
    for k in ("load", "prompt_eval", "eval", "total"):  # Ollama reports nanoseconds
        if isinstance(u.get(f"{k}_duration"), int):
            out[f"ollama_{k}_ms"] = round(u[f"{k}_duration"] / 1e6)
    return out


def error_type(exc: BaseException) -> str:
    """Technical analysis error -> one type (reliability taxonomy). Never a fail-closed rejection."""
    if isinstance(exc, OllamaError):
        cause = exc.__cause__
        cause = getattr(cause, "reason", cause)  # urllib.error.URLError wraps the socket error
        return "OLLAMA_TIMEOUT" if isinstance(cause, TimeoutError) or "timed out" in str(exc) else "OLLAMA_ERROR"
    if isinstance(exc, MalformedResponseError):
        return "INVALID_JSON" if str(exc).startswith("model output is") else "SCHEMA_VALIDATION"
    if isinstance(exc, InputTooLargeError):
        return "INPUT_TOO_LARGE"
    return "OTHER"


def _target_turns(call: Call, new_ids: set[str]) -> set[str]:
    """Segment ids an anchored episode may use: the uninterrupted lead turns (consecutive segments of the
    same speaker) that contain a new lead segment. Earlier lead turns, after another speaker spoke, are
    context only."""
    turns: list[list[TranscriptSegment]] = []
    for seg in sorted(call.segments, key=lambda s: s.segment_index):
        if turns and turns[-1][-1].speaker_id == seg.speaker_id:
            turns[-1].append(seg)
        else:
            turns.append([seg])
    # ponytail: a long lead monologue is one turn, so an old objection inside it could still be folded
    # into a new episode there; the LIVE TARGET prompt is the guard for that case. Add a time gap if seen.
    return {s.segment_id for turn in turns if any(s.segment_id in new_ids for s in turn) for s in turn}


@dataclass
class LiveSalesSession:
    meeting_id: str
    provider: ClassificationProvider
    knowledge: ObjectionKnowledge
    classification_kb: Path
    config: LiveConfig = field(default_factory=LiveConfig)
    clock: Callable[[], float] = time.time
    utterances: list[LiveUtterance] = field(default_factory=list)
    current_recommendation: Recommendation | None = None
    open_objections: list[str] = field(default_factory=list)
    last_guidance: Any = None  # the CommercialGuidance behind the current recommendation
    last_guidance_at: float | None = None
    timings: list[dict[str, Any]] = field(default_factory=list)
    _last_analyzed_seq: int = -1
    _last_analyzed_lead: str = ""
    # Live analysis queue, latest-wins: at most ONE pending lead utterance (its sequence). A newer
    # eligible lead line replaces it; closer lines never set it. Every utterance stays in the transcript.
    pending_lead_seq: int | None = None
    last_trigger_reason: str | None = None  # why the latest added utterance did (None) or did not trigger
    _superseded: int = 0  # pending lead lines replaced by a newer one before their analysis started
    last_outcome: str | None = None  # outcome:reason of the latest finished analysis (sidebar status)
    # Observability: the analysis running now vs the last one that finished. Never mixed: each names
    # its own utterance, and a finish swaps both (plus the recommendation) under one lock.
    active_analysis: dict[str, Any] | None = None
    last_completed_analysis: dict[str, Any] | None = None
    _next_id: int = 1
    last_add_status: str | None = None  # why the latest add() did or did not insert (delivery contract)
    error_reasons: dict[str, int] = field(default_factory=dict)  # technical analysis errors by error_type
    error_examples: dict[str, str] = field(default_factory=dict)  # error_type -> first message (no call text)
    # Reliability counters (technical only, no text): delivery into the session and analysis lifecycle.
    counters: dict[str, int] = field(default_factory=lambda: dict.fromkeys((
        "received", "accepted", "duplicates_suppressed", "rejected", "rehydrated", "analyses_started",
        "analyses_completed",
        "analysis_errors", "recommendations_created"), 0))
    _short_ids: dict[int, str] = field(default_factory=dict)
    lock: threading.RLock = field(default_factory=threading.RLock)
    # Temporary debug for the first real-Meet tests (`--debug`): stage log + last-event summary for the panel.
    debug: Callable[..., None] | None = None
    debug_state: dict[str, Any] = field(default_factory=dict)
    fast_path_counters: dict[str, int] = field(default_factory=lambda: dict.fromkeys(
        ("attempts", "hits", "llm_calls_saved"), 0))
    fast_path_by_category: dict[str, int] = field(default_factory=dict)
    # Commercial State (see commercial_state.py): facts, extraction high-water mark, technical counters.
    commercial: CommercialState = field(default_factory=CommercialState)
    _last_extracted_seq: int = -1
    _rehydrated_upto: int = -1  # extractions of lines up to here rebuild the state after a restart
    _facts_in_flight: int = 0  # extractions claimed but not applied yet (finalize waits for them)
    brief: PostCallBrief | None = None  # set once by finalize(); the same brief is returned after that
    _analysis_done_at: float = 0.0  # the last objection analysis finished (the closer usually answers now)
    compliance_ms: float = 0.0  # last Playbook Compliance evaluation (deterministic, read-time only)
    fact_counters: dict[str, int] = field(default_factory=lambda: dict.fromkeys((
        "extractions", "rebuild_extractions", "extraction_errors", "events_accepted", "events_rejected",
        "facts_added", "facts_updated"), 0))

    def _dbg(self, tag: str, **fields: Any) -> None:
        if self.debug:
            self.debug(tag, **fields)

    # --- input --------------------------------------------------------------------------------

    def add(self, utt: LiveUtterance) -> bool:
        """Insert in sequence order. False (ignored) for a repeated sequence or a repeated caption.

        Idempotent per `sequence` (the utterance id): a retry of an utterance already here is answered
        DUPLICATE_SEQUENCE and changes nothing. `last_add_status` says why: ACCEPTED | DUPLICATE_SEQUENCE |
        DUPLICATE_TEXT (same speaker repeated the same caption) | EMPTY."""
        with self.lock:
            self.counters["received"] += 1
            if any(u.sequence == utt.sequence for u in self.utterances):
                return self._refuse("DUPLICATE_SEQUENCE")
            if not utt.text.strip():
                return self._refuse("EMPTY")
            recent = self.utterances[-3:]
            if any(u.speaker == utt.speaker and _norm(u.text) == _norm(utt.text) for u in recent):
                return self._refuse("DUPLICATE_TEXT")
            self.counters["accepted"] += 1
            self.last_add_status = "ACCEPTED"
            i = len(self.utterances)
            while i and self.utterances[i - 1].sequence > utt.sequence:
                i -= 1
            self.utterances.insert(i, utt)
            self._short_ids[utt.sequence] = f"seg_{len(self._short_ids) + 1}"
            self.last_trigger_reason = self._trigger_reason(utt)
            if self.last_trigger_reason is None:
                if self.pending_lead_seq is not None:
                    self._superseded += 1
                self.pending_lead_seq = utt.sequence
            return True

    def rehydrate(self, utts: list[LiveUtterance]) -> int:
        """Restore utterances this meeting already had before a runtime restart (sent back by the extension).

        Context only: they go into the transcript/window in sequence order, but never trigger or queue an
        analysis, never touch the recommendation and are not counted as live delivery. Idempotent per
        sequence. Returns how many were added."""
        with self.lock:
            added = []
            for utt in sorted(utts, key=lambda u: u.sequence):
                if not utt.text.strip() or any(u.sequence == utt.sequence for u in self.utterances):
                    continue
                i = len(self.utterances)
                while i and self.utterances[i - 1].sequence > utt.sequence:
                    i -= 1
                self.utterances.insert(i, utt)
                self._short_ids[utt.sequence] = f"seg_{len(self._short_ids) + 1}"
                added.append(utt)
            if added:
                # already seen by the previous runtime: never analyzed again as new lines (the commercial
                # state is rebuilt from them by extraction only: see extract())
                self._last_analyzed_seq = max(self._last_analyzed_seq, max(u.sequence for u in added))
                self._rehydrated_upto = max(self._rehydrated_upto, self._last_analyzed_seq)
                if self.pending_lead_seq is not None and self.pending_lead_seq <= self._last_analyzed_seq:
                    self.pending_lead_seq = None
                leads = [u for u in added if u.role == "lead"]
                if leads and leads[-1].sequence == self._last_analyzed_seq:
                    self._last_analyzed_lead = _norm(leads[-1].text)  # repeat suppression keeps working
            self.counters["rehydrated"] += len(added)
            return len(added)

    def _refuse(self, status: str) -> bool:
        self.last_add_status = status
        self.counters["rejected" if status == "EMPTY" else "duplicates_suppressed"] += 1
        return False

    def _trigger_reason(self, utt: LiveUtterance) -> str | None:
        """Only this NEW lead utterance can trigger: None = it becomes the pending analysis, else why not."""
        if utt.role != "lead":
            return "NOT_LEAD"
        if utt.sequence <= self._last_analyzed_seq or (self.pending_lead_seq or -1) > utt.sequence:
            return "OLDER_THAN_PENDING_OR_ANALYZED"
        if len(utt.text.strip()) < self.config.min_lead_chars:
            return "LEAD_UTTERANCE_TOO_SHORT"
        ratio = difflib.SequenceMatcher(None, _norm(utt.text), self._last_analyzed_lead).ratio()
        if ratio >= self.config.repeat_similarity:
            return "REPEAT_OF_LAST_ANALYZED"
        return None

    def _sid(self, sequence: int) -> str:
        # Short "seg_<n>" per session, never the raw sequence: the extension's sequences are epoch-ms
        # (13 digits) and qwen3:8b then answers evidence_segment_ids as integers ([1792615952359]),
        # which the guidance validator rejects. Same failure as bare "u<n>" ids.
        return self._short_ids[sequence]

    def transcript(self, n: int = 8) -> list[LiveUtterance]:
        """The last `n` utterances the session accepted: exactly what the runtime received."""
        with self.lock:
            return self.utterances[-n:]

    def recent_window(self) -> list[LiveUtterance]:
        with self.lock:
            if not self.utterances:
                return []
            newest = self.utterances[-1].timestamp
            window = [u for u in self.utterances if newest - u.timestamp <= self.config.window_seconds]
            return window[-self.config.max_window_utterances:]

    @property
    def current_objection(self) -> str | None:
        rec = self.current()
        return rec.category if rec else None

    def should_analyze(self) -> bool:
        """A pending lead utterance is waiting (set only by a new, eligible lead line)."""
        with self.lock:
            return self.pending_lead_seq is not None

    # --- output -------------------------------------------------------------------------------

    def current(self) -> Recommendation | None:
        """The one active recommendation, or None. Expiry is applied lazily here."""
        with self.lock:
            rec = self.current_recommendation
            if rec and rec.state == "ACTIVE" and self.clock() - rec.shown_at > self.config.ttl_seconds:
                rec.state = "EXPIRED"
            return rec if rec and rec.state == "ACTIVE" else None

    def dismiss(self) -> None:
        with self.lock:
            if self.current():
                self.current_recommendation.state = "DISMISSED"

    def mark_displayed(self, rec_id: int) -> None:
        """First time the panel received this recommendation (end of the end-to-end latency)."""
        with self.lock:
            for t in reversed(self.timings):
                if t.get("recommendation_id") == rec_id:
                    if t.get("displayed_at") is None:
                        t["displayed_at"] = self.clock()
                        t["displayed_latency_ms"] = _ms(t["displayed_at"] - t["caption_received_at"])
                    return

    # --- analysis -----------------------------------------------------------------------------

    def _window_call(self, window: list[LiveUtterance]) -> Call:
        t0 = window[0].timestamp
        roles = {u.speaker: u.role for u in window}
        return Call(
            call_id=f"live_{self.meeting_id}", company_id="live", source="google_meet_captions",
            source_id=self.meeting_id, occurred_at=datetime.fromtimestamp(t0, UTC),
            duration_seconds=max(window[-1].timestamp - t0, 0.0) + 1.0,
            participants=[Participant(id=s, name=s, role=r if r in ("closer", "lead") else "unknown")
                          for s, r in roles.items()],
            segments=[TranscriptSegment(segment_id=self._sid(u.sequence), segment_index=i, speaker_id=u.speaker,
                                        start_ts=u.timestamp - t0, end_ts=u.timestamp - t0 + 1.0, text=u.text)
                      for i, u in enumerate(window)],
        )

    def analyze(self) -> dict[str, Any]:
        """One analysis of the rolling window. Returns its timing record (also kept in `timings`).

        `outcome`: RECOMMENDED | KEPT (same category inside the cooldown) | NO_RECOMMENDATION.
        Ollama, malformed-output and too-large errors are recorded as NO_RECOMMENDATION with reason ERROR:<type>.
        """
        with self.lock:
            # Take the one pending lead (latest wins). Lead lines in the window that were superseded
            # while waiting are still new and can still anchor the objection; nothing is dropped.
            trigger = next((u for u in self.utterances if u.sequence == self.pending_lead_seq), None)
            superseded, self.pending_lead_seq, self._superseded = self._superseded, None, 0
            window = self.recent_window()
            new_seqs = ({u.sequence for u in window if u.sequence > self._last_analyzed_seq and u.role == "lead"}
                        if trigger else set())
            if window:
                self._last_analyzed_seq = max(self._last_analyzed_seq, window[-1].sequence)
            if trigger:
                self._last_analyzed_lead = _norm(trigger.text)
            started = self.clock()
            if trigger is not None:
                self.counters["analyses_started"] += 1
            self.active_analysis = None if trigger is None else {
                "sequence": trigger.sequence, "segment_id": self._sid(trigger.sequence), "speaker": trigger.speaker,
                "role": trigger.role, "text_preview": trigger.text[:140], "started_at": started}
        t: dict[str, Any] = {"sequence": trigger.sequence if trigger else None,
                             "caption_received_at": trigger.received_at if trigger else started,
                             "window_utterances": len(window), "superseded_leads": superseded,
                             "analysis_started_at": started}
        t["queue_wait_ms"] = _ms(started - t["caption_received_at"])
        if trigger and trigger.caption_changed_at is not None:  # browser side, before the runtime saw it
            t["caption_stable_wait_ms"] = _ms(trigger.timestamp - trigger.caption_changed_at)
            t["caption_to_runtime_ms"] = _ms(trigger.received_at - trigger.timestamp)
        try:
            outcome, reason = self._decide(window, new_seqs, t)
        except (OllamaError, MalformedResponseError, InputTooLargeError) as exc:  # live: no recommendation, no crash
            outcome, reason = "NO_RECOMMENDATION", f"ERROR:{type(exc).__name__}"
            t.update(error_type=error_type(exc), error_detail=str(exc)[:200], error_usage=_usage(self.provider),
                     error_stage="guidance" if t.get("policy_finished_at") else "classifier")
        except Exception as exc:  # noqa: BLE001 - any other failure must still finish the analysis below,
            # or active_analysis stays set and the dock shows "Analisando..." forever
            outcome, reason = "NO_RECOMMENDATION", f"ERROR:UNEXPECTED:{type(exc).__name__}"
            t.update(error_type="OTHER", error_detail=f"{type(exc).__name__}: {exc}"[:200])
        t.update(outcome=outcome, reason=reason)
        new_rec = t.pop("_new_rec", None)
        # Queue wait and inference are reported separately (never mixed).
        if t.get("classifier_finished_at"):
            t["classifier_latency_ms"] = _ms(t["classifier_finished_at"] - started)
        if t.get("guidance_finished_at"):
            t["guidance_latency_ms"] = _ms(t["guidance_finished_at"] - t["classifier_finished_at"])
        if t.get("policy_finished_at"):  # classifier done -> guidance call starts (validation, gates, retrieval)
            t["policy_ms"] = _ms(t["policy_finished_at"] - t["classifier_finished_at"])
        # Time outside Ollama: prompt build + parse + validation (classifier); retrieval + prompt build +
        # validation/grounding (guidance).
        if "classifier_latency_ms" in t and "ollama_total_ms" in t.get("classifier", {}):
            t["classifier_local_ms"] = t["classifier_latency_ms"] - t["classifier"]["ollama_total_ms"]
        if "guidance_latency_ms" in t and "ollama_total_ms" in t.get("guidance", {}):
            t["guidance_local_ms"] = t["guidance_latency_ms"] - t["policy_ms"] - t["guidance"]["ollama_total_ms"]
        t["end_to_end_latency_ms"] = _ms(self.clock() - t["caption_received_at"])  # caption -> outcome ready
        with self.lock:  # one atomic swap: recommendation, active -> None, last completed -> this result
            if new_rec is not None:
                if self.current_recommendation and self.current_recommendation.state == "ACTIVE":
                    self.current_recommendation.state = "REPLACED"
                self.current_recommendation = new_rec
            self.last_outcome = f"{outcome}:{reason}"
            self.last_completed_analysis = {
                "sequence": t["sequence"], "segment_id": self._sid(t["sequence"]) if t["sequence"] is not None else None,
                "category": t.get("category"), "outcome": outcome, "reason": reason, "finished_at": self.clock()}
            self.active_analysis = None
            self._analysis_done_at = self.clock()
            self.timings.append(t)
            if t["sequence"] is not None:
                self.counters["analyses_completed"] += 1
                self.counters["analysis_errors"] += reason.startswith("ERROR:")
                if reason.startswith("ERROR:"):
                    et = t.get("error_type", "OTHER")
                    self.error_reasons[et] = self.error_reasons.get(et, 0) + 1
                    self.error_examples.setdefault(et, t.get("error_detail", ""))
                self.counters["recommendations_created"] += new_rec is not None
        self._dbg("POLICY" if outcome != "RECOMMENDED" else "STATE", outcome=outcome, reason=reason,
                  segment=self.last_completed_analysis["segment_id"],
                  recommendation=(self.current_recommendation.state if self.current_recommendation else "NONE"))
        return t

    def _decide(self, window: list[LiveUtterance], new_seqs: set[int], t: dict[str, Any]) -> tuple[str, str]:
        if not new_seqs:
            return "NO_RECOMMENDATION", "NO_PENDING_LEAD_UTTERANCE"
        call = self._window_call(window)
        # Latest-utterance anchoring: the lead lines new since the last analysis are the TARGET (the newest
        # is the trigger; older ones were superseded while waiting); the rest of the window is context.
        new_ids = {self._sid(s) for s in new_seqs}
        targets = tuple(seg.segment_id for seg in call.segments if seg.segment_id in new_ids)
        t["target_segment_ids"] = list(targets)
        fast = None
        if self.config.fast_path:
            with self.lock:
                self.fast_path_counters["attempts"] += 1
            if len(targets) == 1:  # one new lead line, read alone (a continuation or a batch -> the LLM)
                fast = fast_path_category(next(s.text for s in call.segments if s.segment_id == targets[0]))
        if fast:
            # the fast path proposes a category; validation and every gate below still apply
            t["classification_source"] = "deterministic_fast_path"
            detection, raw_episodes, spans = "OBJECTIONS_FOUND", (EpisodePrediction(
                prediction_id="fp1", objection_segment_ids=targets, context_segment_ids=(), category_status="PRESENT",
                category=fast, category_candidates=(), reaction_status="ABSENT", reaction=None,
                reaction_candidates=(), resolution_status="unknown", summary="Deterministic fast path."),), ()
            with self.lock:
                self.fast_path_counters["hits"] += 1
                self.fast_path_counters["llm_calls_saved"] += 1
                self.fast_path_by_category[fast] = self.fast_path_by_category.get(fast, 0) + 1
            t.update(classifier_finished_at=self.clock(), classifier={}, episodes=1)
            self._dbg("CLASSIFIER", source="deterministic_fast_path", category=fast, objection=list(targets))
        else:
            t["classification_source"] = "llm"
            # structured: the classifier's own output schema, enforced by Ollama (see CLASSIFIER_SCHEMA)
            run = classify_call(call, self.config.arm, self.provider, self.classification_kb, structured=True,
                                target_segment_ids=targets)
            detection, raw_episodes, spans = run.call_detection, run.episodes, run.uncertain_spans
            t.update(classifier_finished_at=self.clock(), classifier=_usage(self.provider),
                     episodes=len(run.episodes))
            self._dbg("CLASSIFIER", source="llm", detection=run.call_detection,
                      validation_errors=list(run.validation_errors),
                      episodes=[{"category": e.category, "status": e.category_status,
                                 "objection": e.objection_segment_ids, "context": e.context_segment_ids}
                                for e in run.episodes],
                      new_lead_ids=sorted(self._sid(s) for s in new_seqs), usage=t["classifier"],
                      raw=run.raw_response)
        # Live: the trigger is the newest utterance, so the model tends to cite the lines *before* it
        # as context, which the classifier contract forbids. Keep only post-anchor context (less
        # evidence, never more) and re-run the classifier's own validator; still invalid -> nothing.
        order = {seg.segment_id: seg.segment_index for seg in call.segments}
        episodes = tuple(dataclasses.replace(e, context_segment_ids=tuple(
            c for c in e.context_segment_ids if order.get(c, -1) > order.get(e.anchor_segment_id, -1)))
            for e in raw_episodes)
        if errors := validate_predictions(call, detection, episodes, spans):
            self._dbg("CLASSIFIER", status="INVALID", errors=list(errors))
            return "NO_RECOMMENDATION", "CLASSIFIER_INVALID"
        if detection != "OBJECTIONS_FOUND":
            return "NO_RECOMMENDATION", "NO_OBJECTION"
        allowed = _target_turns(call, new_ids)
        candidates = [e for e in episodes if self._qualifies(e, new_ids, allowed)]
        categories = {e.category for e in candidates}
        if not candidates:
            return "NO_RECOMMENDATION", "NO_QUALIFYING_EPISODE"
        if len(categories) > 1:
            return "NO_RECOMMENDATION", "AMBIGUOUS_CATEGORIES"
        episode = candidates[0]
        objection_text = " ".join(seg.text for seg in call.segments if seg.segment_id in episode.objection_segment_ids)
        category = authority_override(price_override(episode.category, objection_text), objection_text)
        if category != episode.category:
            t["category_before"] = episode.category
            self._dbg("CLASSIFIER", category_normalized=f"{episode.category} -> {category}",
                      reason=("explicit price words" if category == "PRICE_BUDGET"
                              else "explicit third-party decision dependency") + " in the objection evidence")
            episode = dataclasses.replace(episode, category=category)
        cues = CORROBORATION.get(episode.category)
        if cues:
            said = " ".join(_fold(seg.text) for seg in call.segments if seg.segment_id in episode.objection_segment_ids)
            if not cues.search(said):
                t["category"] = episode.category
                return "NO_RECOMMENDATION", "UNCORROBORATED_CATEGORY"
        t["category"] = episode.category
        # The engine's own decision feeds the Commercial State (never re-classified there).
        self._record([objection_event(episode.category, episode.objection_segment_ids)], call)
        current = self.current()
        if (current and current.category == episode.category
                and self.clock() - current.shown_at < self.config.cooldown_seconds):
            return "KEPT", "COOLDOWN"
        # Guidance evidence, two scopes (CommercialGuidance and grounding unchanged):
        # - objection evidence = the episode's objection segments (what the panel quotes);
        # - allowed factual call evidence = every captured segment of this window. The classifier
        #   contract keeps only post-anchor context, but a fact the lead said a moment earlier ("Hoje a
        #   gente perde tempo...") is real call text; grounding checks against it, knowledge never counts.
        factual = tuple(seg.segment_id for seg in call.segments if seg.segment_id not in episode.objection_segment_ids)
        guidance_episode = dataclasses.replace(episode, context_segment_ids=factual)
        self._dbg("POLICY", emit=True, category=episode.category, anchor=episode.objection_segment_ids[0],
                  objection_evidence=list(episode.objection_segment_ids), factual_evidence=list(factual))
        t["policy_finished_at"] = self.clock()
        with self.lock:  # UI only: the objection is known before its guidance is ready ("Objeção detectada")
            if self.active_analysis is not None:
                self.active_analysis.update(detected_category=episode.category,
                                            label=LABELS.get(episode.category, episode.category))
        # live: one-sentence rationale (debug-only in the sidebar) + schema-enforced shape; see guide_episode
        guidance = guide_episode(call, guidance_episode, self.knowledge, self.provider, live=True)
        t.update(guidance_finished_at=self.clock(), guidance=_usage(self.provider))
        self._dbg("GUIDANCE", status=guidance.status, errors=list(guidance.errors), usage=t["guidance"],
                  move=guidance.knowledge_move_id)
        self._dbg("GROUNDING", valid=not any("ungrounded" in e for e in guidance.errors),
                  errors=[e for e in guidance.errors if "ungrounded" in e])
        if guidance.status != "GUIDED":
            # fail-closed, not a technical error: grounding rejected an invented fact, or the answer broke
            # the guidance contract (wrong keys/ids/move)
            if guidance.status == "INVALID_RESPONSE":
                t["guidance_rejection"] = ("GROUNDING_REJECTED" if all("ungrounded" in e for e in guidance.errors)
                                           else "GUIDANCE_INVALID")
            return "NO_RECOMMENDATION", f"GUIDANCE_{guidance.status}"
        with self.lock:  # built here, made current by analyze() in the same swap as last_completed_analysis
            g = guidance.generated_guidance
            t["_new_rec"] = Recommendation(
                id=self._next_id, category=episode.category,
                move=_action(guidance.recommended_move.code, _generic(guidance.recommended_move.guidance),
                             g.suggested_question),
                rationale=_first_sentence(g.rationale), question=g.suggested_question, grade=guidance.knowledge_grade,
                shown_at=self.clock(), knowledge_unit=guidance.knowledge_unit_id,
                move_id=guidance.knowledge_move_id, move_code=guidance.recommended_move.code,
                lead_said=objection_text)
            self._next_id += 1
            self.last_guidance, self.last_guidance_at = guidance, self.clock()
            if episode.category not in self.open_objections:
                self.open_objections.append(episode.category)
            t["recommendation_id"] = t["_new_rec"].id
        return "RECOMMENDED", "GUIDED"

    @staticmethod
    def _qualifies(e: EpisodePrediction, new_ids: set[str], allowed: set[str]) -> bool:
        """A NEW objection: it includes a new lead segment, and every objection segment is in the same
        uninterrupted lead turn as one (a continuation). An objection from an earlier turn, alone or
        folded together with the new line, never satisfies the current analysis."""
        ids = set(e.objection_segment_ids)
        return (e.category_status == "PRESENT" and e.category in LABELS
                and bool(ids & new_ids) and ids <= allowed)

    # --- commercial state -------------------------------------------------------------------------

    def _record(self, events: list[CommercialEvent], call: Call) -> None:
        order = {seg.segment_id: seg.segment_index for seg in call.segments}
        with self.lock:
            for e in events:
                result = self.commercial.apply(e, order)
                if result == "ADDED":
                    self.fact_counters["facts_added"] += 1
                elif result == "UPDATED":
                    self.fact_counters["facts_updated"] += 1
                self._dbg("COMMERCIAL", event=e.event_type, value=e.value, segments=list(e.segment_ids),
                          role=e.stakeholder_role, result=result)

    def _facts_todo(self) -> list[LiveUtterance]:
        return [u for u in self.utterances if u.role == "lead" and u.sequence > self._last_extracted_seq]

    def should_extract(self) -> bool:
        """Lead lines not yet read for commercial facts (live, or rehydrated after a restart)."""
        with self.lock:
            return self.config.commercial_facts and bool(self._facts_todo())

    def facts_idle(self) -> bool:
        """No live utterance and no finished analysis for `facts_idle_seconds` (the background worker
        extracts only then: right after a recommendation the closer answers and the lead may reply).
        Lines rehydrated after a restart are old: their rebuild never waits."""
        with self.lock:
            last = max((u.received_at for u in self.utterances if u.sequence > self._rehydrated_upto),
                       default=0.0)
            last = max(last, self._analysis_done_at)
            return self.clock() - last >= self.config.facts_idle_seconds

    def extract(self) -> dict[str, Any]:
        """One commercial-facts extraction over the oldest unread lead lines (+ a few lines of context).

        Never touches the recommendation or the objection analysis counters. One LLM call, skipped when
        the new lead lines are single words ("Ok.", "Sim."). Errors are recorded; the lines are not retried."""
        with self.lock:
            todo = self._facts_todo()
            if not todo:
                return {"kind": "commercial_facts", "outcome": "NOTHING"}
            first = self.utterances.index(todo[0])
            chunk = self.utterances[max(first - self.config.facts_context_utterances, 0):
                                    first + self.config.facts_chunk_utterances]
            new = [u for u in chunk if u in todo]
            self._last_extracted_seq = new[-1].sequence
            self._facts_in_flight += 1
            rebuild = new[-1].sequence <= self._rehydrated_upto
            call = self._window_call(chunk)
        targets = tuple(self._sid(u.sequence) for u in new if len(u.text.split()) >= 2)
        t: dict[str, Any] = {"kind": "commercial_facts", "rebuild": rebuild, "target_segment_ids": list(targets)}
        if not targets:
            with self.lock:
                self._facts_in_flight -= 1
            return {**t, "outcome": "SKIPPED_SHORT"}
        started = self.clock()
        try:
            response = self.provider.classify(build_facts_prompt(call, targets), schema=FACTS_SCHEMA)
            with self.lock:
                events, rejected = parse_facts(call, targets, response, self.commercial)
            self._record(events, call)
            t.update(outcome="EXTRACTED", accepted=len(events), rejected=[r["reason"] for r in rejected])
        except (OllamaError, MalformedResponseError, InputTooLargeError, TypeError, ValueError) as exc:
            events, rejected = [], []
            t.update(outcome="ERROR", error_type=error_type(exc), error_detail=str(exc)[:200])
        except Exception as exc:  # noqa: BLE001 - never kill the worker: objection analysis shares it
            events, rejected = [], []
            t.update(outcome="ERROR", error_type="OTHER", error_detail=f"{type(exc).__name__}: {exc}"[:200])
        t["latency_ms"] = _ms(self.clock() - started)
        t.update(usage=_usage(self.provider))
        with self.lock:
            self._facts_in_flight -= 1
            self.fact_counters["rebuild_extractions" if rebuild else "extractions"] += 1
            self.fact_counters["extraction_errors"] += t["outcome"] == "ERROR"
            self.fact_counters["events_accepted"] += len(events)
            self.fact_counters["events_rejected"] += len(rejected)
        self._dbg("COMMERCIAL", **{k: v for k, v in t.items() if k != "usage"})
        return t

    # --- playbook compliance ------------------------------------------------------------------------

    def compliance(self) -> PlaybookComplianceState:
        """Playbook Compliance of the call so far: a pure function of the Commercial State and the
        transcript, recomputed when read (never on the recommendation's path, no LLM). Rebuilt for free
        after a restart: rehydrated lines + the rebuilt Commercial State give the same result."""
        with self.lock:
            started = time.perf_counter()
            state = evaluate(load_playbook(), self.commercial.view(),
                             [(self._sid(u.sequence), u.role, u.text) for u in self.utterances])
            self.compliance_ms = round((time.perf_counter() - started) * 1000, 2)
            return state

    # --- post-call brief ----------------------------------------------------------------------------

    def busy(self) -> bool:
        """An objection analysis is waiting/running or an extraction is in flight."""
        with self.lock:
            return bool(self.active_analysis or self.pending_lead_seq is not None or self._facts_in_flight)

    def finalize(self) -> PostCallBrief:
        """End of call: read the lead lines not read yet (no pause wait), then build the brief from the
        CommercialState. Idempotent: the first brief is kept and returned again; nothing is re-analyzed.
        Callers wait for `busy()` to clear first (Runtime.finalize)."""
        with self.lock:
            if self.brief is not None:
                return self.brief
        while self.should_extract():
            self.extract()
        with self.lock:
            if self.brief is None:
                self.brief = build_brief(self.meeting_id, self.commercial.view(), list(self.timings),
                                         dict(self.counters), self.clock(), rebuilt=self._rehydrated_upto >= 0,
                                         compliance=self.compliance().view())
            return self.brief
