"""Grounding validator v0: model-generated text may not introduce specific facts absent from the call.

Deterministic, fail-closed, pt-BR oriented. `ungrounded(text, evidence)` lists every specific fact in
`text` that `evidence` (the CALL EVIDENCE the model was shown) does not contain:

- placeholders: [..], {..}, <..>, TODO, TBD — never allowed, never filled in;
- dates and deadlines: weekdays, months, numeric dates, explicit relative dates (amanhã, semana
  que vem, ...);
- numbers and amounts: every digit run, R$, %, "mil", "reais", ...;
- decision stakeholders: sócio, esposa, CFO, diretor, conselho, decisor, ...;
- commercial conditions: desconto, parcela, garantia, reembolso, ...;
- proper names: capitalized words mid-sentence and acronyms.

Comparison is on casefolded, accent-free text, by word stem, so "sócia" in the call grounds
"sócio" in the guidance. Sales knowledge is deliberately NOT a grounding source for facts: a move
template's "30 dias" or "[data]" is strategy, not something that happened in this negotiation.
Generic phrasing ("combine uma data objetiva de retorno") contains none of these and passes.

ponytail: lexical rules, not semantics — an invented problem or product with a lowercase common
noun passes. Upgrade path: an entailment check per sentence, once there is gold to measure it against.
"""
from __future__ import annotations

import re
import unicodedata

PLACEHOLDER = re.compile(r"\[[^\]]*\]|\{[^}]*\}|<[^>]*>|\bTODO\b|\bTBD\b")

_WEEKDAYS = ("segunda", "terca", "quarta", "quinta", "sexta", "sabado", "domingo")
_MONTHS = ("janeiro", "fevereiro", "marco", "abril", "maio", "junho", "julho", "agosto", "setembro",
           "outubro", "novembro", "dezembro")
_RELATIVE_DATES = ("amanha", "depois de amanha", "ontem", "hoje", "semana que vem", "mes que vem",
                   "ano que vem", "proxima semana", "proximo mes", "proximo ano", "fim de semana",
                   "fim do mes", "inicio do mes")
# Generic words that only become a deadline with one of the date words above.
DATE_TERMS = (*_WEEKDAYS, *_MONTHS)
_NUMERIC_DATE = re.compile(r"\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b")
_DIGITS = re.compile(r"\d+(?:[.,]\d+)*")
_AMOUNT_TERMS = ("r$", "%", "reais", "mil", "milhao", "milhoes", "por cento", "dolar", "dolares")
_STAKEHOLDER_STEMS = ("soci", "esposa", "marido", "conjuge", "namorad", "cfo", "ceo", "cto", "diretor",
                      "diretoria", "conselho", "financeiro", "juridico", "chefe", "gerente", "presidente",
                      "contador", "advogad", "familia", "decisor", "patrao", "dono", "dona")
_CONDITION_STEMS = ("desconto", "parcel", "garanti", "reembols", "gratis", "gratuit", "bonus", "brinde",
                    "cashback", "juros", "multa", "cancel", "estorno", "promoc")
_WORD = re.compile(r"[a-z0-9$%]+")
_SENTENCE_START = re.compile(r"(^|[.!?:;]\s+|[\"'“(]\s*)$")


def normalize(text: str) -> str:
    """casefold + strip accents, so 'Março' == 'marco' and 'sócio' == 'socio'."""
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def _words(text: str) -> list[str]:
    return _WORD.findall(normalize(text))


def _has_stem(words: list[str], stem: str) -> bool:
    return any(w == stem or (len(stem) >= 4 and w.startswith(stem)) for w in words)


def _phrase_in(phrase: str, norm_text: str) -> bool:
    return re.search(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", norm_text) is not None


def _contains(term: str, norm_text: str) -> bool:
    return _phrase_in(term, norm_text) if term[0].isalpha() else term in norm_text


def _proper_names(text: str) -> set[str]:
    """Capitalized words that do not start a sentence, plus acronyms (2+ capitals)."""
    names = set()
    for m in re.finditer(r"\b[A-ZÀ-Ý][\wÀ-ÿ]*\b", text):
        word = m.group(0)
        if len(word) >= 2 and (word.isupper() or not _SENTENCE_START.search(text[: m.start()])):
            names.add(word)
    return names


def has_date(text: str) -> bool:
    """True if `text` states a date or deadline (not 'depois', 'mais pra frente', 'qualquer dia')."""
    norm = normalize(text)
    words = _words(text)
    return (bool(_NUMERIC_DATE.search(text))
            or any(_has_stem(words, t) for t in DATE_TERMS)
            or any(_phrase_in(p, norm) for p in _RELATIVE_DATES))


def ungrounded(text: str, evidence: str) -> list[str]:
    """Every specific fact in `text` that `evidence` does not contain. Empty list = grounded."""
    problems = [f"placeholder {m.group(0)!r}" for m in PLACEHOLDER.finditer(text)]
    norm_text, norm_ev = normalize(text), normalize(evidence)
    words, ev_words = _words(text), _words(evidence)

    for m in _NUMERIC_DATE.finditer(text):
        if m.group(0) not in evidence:
            problems.append(f"date {m.group(0)!r} not in call evidence")
    for term in DATE_TERMS:
        if _has_stem(words, term) and not _has_stem(ev_words, term):
            problems.append(f"date {term!r} not in call evidence")
    for phrase in _RELATIVE_DATES:
        if _phrase_in(phrase, norm_text) and not _phrase_in(phrase, norm_ev):
            problems.append(f"date {phrase!r} not in call evidence")

    ev_numbers = set(_DIGITS.findall(evidence))
    for number in _DIGITS.findall(text):
        if number not in ev_numbers:
            problems.append(f"number {number!r} not in call evidence")
    for term in _AMOUNT_TERMS:
        if _contains(term, norm_text) and not _contains(term, norm_ev):
            problems.append(f"amount term {term!r} not in call evidence")

    for stem in _STAKEHOLDER_STEMS:
        if _has_stem(words, stem) and not _has_stem(ev_words, stem):
            problems.append(f"stakeholder {stem!r}* not in call evidence")
    for stem in _CONDITION_STEMS:
        if _has_stem(words, stem) and not _has_stem(ev_words, stem):
            problems.append(f"commercial condition {stem!r}* not in call evidence")

    for name in sorted(_proper_names(text)):
        if not _has_stem(ev_words, normalize(name)):
            problems.append(f"name {name!r} not in call evidence")
    return list(dict.fromkeys(problems))
