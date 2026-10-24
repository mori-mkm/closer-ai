"""Deterministic transcript signals shared by Playbook Compliance and Opportunity Detection (no LLM).

A signal is a high-precision lexical fact about ONE line: who said it (closer or lead), what kind of
thing it is (`type`), and its segment id. Compliance and opportunities read the same signals, so a
detector is written once. Lead facts that need understanding (pain, impact, stakeholders...) stay in the
Commercial State; signals only cover phrasings the playbook itself lists.

ponytail: phrase patterns, precision over recall by design (a missed phrasing = no signal, never a guess);
widen a pattern only when real calls show the miss.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from closer_ai.live.commercial_state import fold

Segment = tuple[str, str, str]  # (segment_id, role, text), call order


@dataclass(frozen=True)
class Signal:
    type: str
    segment_ids: tuple[str, ...]
    role: str  # closer | lead
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def segment_id(self) -> str:
        return self.segment_ids[0]

    def view(self) -> dict[str, Any]:
        return {"type": self.type, "segment_ids": list(self.segment_ids), "role": self.role, **self.details}


def plain(text: str) -> str:
    """Lowercase, no accents, punctuation kept ("14:00", "R$", "10%", "?")."""
    return unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode()


# --- dates, times, quantities, prohibited phrases (plain text) ---------------------------------------

_NOT_A_DAY = r"(?![ -]?(?:cadeira|vez|opcao|parcela|pessoa|etapa|reuniao|call|geracao|parte|fase|turma|pergunta))"
DATE = re.compile(rf"\b(?:(?:segunda|terca|quarta|quinta|sexta){_NOT_A_DAY}(?:[ -]feira)?|sabado|domingo|amanha"
                  r"|hoje|dia \d{1,2}|\d{1,2}/\d{1,2})\b")
TIME = re.compile(r"\b\d{1,2} ?h(?:\d{2})?\b|\b\d{1,2}:\d{2}\b|\b(?:as|a partir das|ate as) \d{1,2}\b|\bmeio[ -]dia\b"
                  r"|\b(?:as|a) (?:uma|duas|tres|quatro|cinco|seis|sete|oito|nove|dez|onze|doze)"
                  r" (?:horas?|da tarde|da manha|da noite)\b")
_STEP_CUE = re.compile(r"\b(?:lig\w*|marc\w*|agend\w*|reuni\w*|convers\w*|fal\w*|retorn\w*|call|encontro|cham\w*"
                       r"|mand\w*|envi\w*|fechado|combinado|pode ser|confirm\w*|nos vemos|contato|procuro)\b")
_MEETING_CUE = re.compile(r"\b(?:marc\w*|agend\w*|reuni\w*|convers\w*|call|encontro|chamar|trazer|participar)\b")
_OWNER = re.compile(r"\b(?:eu (?:te |lhe )?|te )(?:ligo|chamo|mando|envio|retorno|marco|agendo|procuro|confirmo)\b")
_NEGATION = re.compile(r"\b(?:nao|nunca|nem|sem)\b")
_NUMBER = (r"(?:\d+(?:[.,]\d+)?|meia|uma?|dois|duas|tres|quatro|cinco|seis|sete|oito|nove|dez|quinze|vinte|trinta"
           r"|quarenta|cinquenta|cem|duzentos|trezentos|quinhentos|mil)")
_UNIT = (r"(?:mil|milhao|milhoes|reais|real|%|por cento|horas?|dias?|semanas?|meses|mes|anos?|cabecas?|bezerros?"
         r"|animais|matrizes|arrobas?|hectares?|ha|litros?|sacas?|funcionarios?|pessoas?|clientes?|vendas?|pedidos?)")
_QUANTITY = re.compile(rf"r\$ ?\d[\d.,]*(?: mil)?|\b{_NUMBER} (?:de )?{_UNIT}(?!\w)|\b\d+(?:[.,]\d+)? ?%")
_MONEY = re.compile(r"r\$ ?\d|\b\d{1,3}(?:\.\d{3})+\b|\b\d+(?:[.,]\d+)? mil\b|\b(?:vinte|trinta|quarenta|cinquenta"
                    r"|sessenta|setenta|oitenta|noventa|cem|duzentos|trezentos|quatrocentos)(?: e \w+)? mil\b")


def schedule(text: str) -> dict[str, str] | None:
    """Date AND time AND a next-step cue in one line, else None ("semana que vem" is not a date)."""
    t = plain(text)
    d, h = DATE.search(t), TIME.search(t)
    if not (d and h and _STEP_CUE.search(t)):
        return None
    return {"date": d.group(0), "time": h.group(0)}


def quantity(text: str) -> str | None:
    """A number with a unit ("8 horas", "R$ 10 mil", "15%", "uma hora"), or None ("muito tempo")."""
    m = _QUANTITY.search(plain(text))
    return m.group(0) if m else None


@lru_cache(maxsize=8192)  # a line never changes: matched once per call
def phrase_hits(text: str, phrases: tuple[str, ...]) -> tuple[str, ...]:
    """Phrases (folded) said affirmatively: no negation in the 3 words before ("não garanto")."""
    words = fold(text)
    hits = []
    for p in phrases:
        for m in re.finditer(rf"\b{re.escape(p)}\b", words):
            if not _NEGATION.search(" ".join(words[:m.start()].split()[-3:])):
                hits.append(p)
                break
    return tuple(hits)


# --- who decides (lead) ---------------------------------------------------------------------------

# a person other than the lead (or a pronoun for one); folded words
PARTY = (r"(?:socios?|socias?|pai|mae|pais|sogro|sogra|marido|esposa|esposo|mulher|filhos?|filhas?|irmaos?|irmas?"
         r"|diretor(?:es|a|as)?|diretoria|conselho|gerente|chefe|dono|dona|financeiro|juridico|investidor(?:es)?"
         r"|familia|patrao|ele|ela|eles|elas)")
_POSS = r"(?:(?:o|a|os|as|com o|com a) )?(?:(?:meu|minha|meus|minhas|nosso|nossa|seu|sua) )?"
_PRONOUNS = {"ele", "ela", "eles", "elas"}
_WITH_PARTY = re.compile(rf"\bcom {_POSS}(?P<p>{PARTY})\b")  # "com seu sócio" / "com ele"
# A decision dependency that blocks moving forward (the playbook's DECISION_AUTHORITY), never a mere
# mention ("Meu sócio.", "Eu e minha esposa.", "O financeiro também participa." are discovery).
_DEPENDENCY = re.compile(
    r"\b(?:"
    r"(?:precis\w*|tenho que|temos que|vou ter que|vamos ter que|teria que) (?:de )?(?:falar|conversar|consultar"
    r"|validar|alinhar|ver|checar|mostrar|levar|passar|apresentar|avaliar)(?: isso| isto| a proposta| essa proposta)?"
    rf" (?:com|pra|para|pro) {_POSS}(?P<p1>{PARTY})"
    rf"|{_POSS}(?P<p2>{PARTY}) (?:precisa|tem que|vai ter que|vai precisar|teria que) (?:aprovar|validar|autorizar"
    r"|ver|concordar|dar o ok|dar o aval|dar a palavra final)"
    rf"|(?:a )?decisao (?:final )?(?:e|eh|fica) (?:do|da|dos|das|com o|com a) {_POSS}(?P<p3>{PARTY})"
    rf"|quem (?:decide|aprova|assina|bate o martelo) (?:e|eh|sao) {_POSS}(?P<p4>{PARTY})"
    rf"|(?:depende|dependo|dependemos) (?:do|da|dos|das) {_POSS}(?P<p5>{PARTY})"
    r"|(?:nao|nem) (?:posso|podemos|consigo|conseguimos) (?:decidir|fechar|assinar)(?: isso| isto| nada)? sozinh\w*"
    r"|(?:so|somente) (?:consigo|posso|podemos|conseguimos) (?:avancar|seguir|fechar) depois d[aeo]s? "
    r"(?:aprovacao|autorizacao|aval|ok)"
    r")\b")


def party_key(word: str | None) -> str | None:
    """'sócia'/'sócios' -> 'socio'; pronouns and None -> None (the subject comes from context)."""
    if not word or word in _PRONOUNS:
        return None
    w = word.rstrip("s") if word not in ("pais",) else "pai"
    return {"socia": "socio", "esposo": "esposa", "mulher": "esposa", "irma": "irmao", "filha": "filho",
            "diretora": "diretor", "diretore": "diretor", "investidore": "investidor"}.get(w, w)


def decision_dependency(text: str) -> tuple[bool, str | None]:
    m = _DEPENDENCY.search(fold(text))
    if not m:
        return False, None
    return True, party_key(next((g for g in m.groups() if g), None))


# --- line signals -----------------------------------------------------------------------------------

# lead: what the lead says (OP triggers); matched on folded text
LEAD = {
    "THINK_IT_OVER": re.compile(
        r"\b(?:(?:vou|preciso|deixa eu|quero|vamos|tenho que) (?:pensar|analisar|avaliar)"
        r"|(?:vou|preciso) ver (?:isso )?com calma"
        r"|(?:me |nos )?(?:manda|mande|envia|envie|passa) (?:\w+ ){0,3}(?:por escrito|por e ?mail|no e ?mail))\b"),
    "BUYING_QUESTION": re.compile(
        r"\b(?:como (?:eu )?(?:faco|faz|faria|fazemos) (?:pra|para) (?:entrar|participar|comecar|fechar|garantir)"
        r"|(?:pode|posso|da pra|da para|consigo|aceita\w*) (?:ser |pagar |parcelar )?(?:no|com|em|pelo|via|por) "
        r"(?:cartao|pix|boleto)"
        r"|(?:e )?se eu (?:pagar|parcelar)|cartao da empresa|quantas (?:vezes|parcelas)"
        r"|(?:qual|quanto) (?:e |fica |seria )?(?:o valor da |a )?parcela"
        r"|quando (?:eu )?(?:comeco|comecaria|comeca|comecamos|inicia|iniciamos|posso comecar|da pra comecar)"
        r"|(?:quando|qual) (?:e |sera )?(?:o )?proximo encontro|onboarding|data de inicio)\b"),
    "OWNER_DEPENDENCY": re.compile(
        r"\b(?:tudo depende de mim|depende tudo de mim|tudo passa por mim|sem mim (?:nada|a fazenda) (?:anda|funciona)"
        r"|(?:nao consigo|nao da pra|nao posso) sair da operacao|o gerente nao decide"
        r"|(?:eu )?(?:preciso|tenho que) resolver tudo)\b"),
    "FINANCIAL_BLINDNESS": re.compile(
        r"\b(?:(?:nao|nem) sei (?:qual e |qual )?(?:a |o )?(?:minha |meu |nossa |nosso )?(?:margem|custo|lucro)"
        r"|(?:nao|nem) sei quanto (?:sobra|ganho|lucro|custa produzir)"
        r"|(?:nao|nem) tenho (?:controle|nocao|ideia) (?:do|de|dos|da|das) (?:custos?|margem|financeiro|numeros)"
        r"|nao tenho controle financeiro)\b"),
    "TIME_CONCERN": re.compile(
        r"\b(?:(?:nao tenho|nao temos|estou sem|to sem|tou sem) tempo|tenho pouco tempo"
        r"|quanto tempo (?:isso |eu |a gente )?(?:toma|tomaria|vai tomar|leva|exige|preciso dedicar|tenho que dedicar"
        r"|precisa|vou precisar)|minha agenda (?:e|esta|ta) (?:cheia|apertada|lotada))\b"),
    "PRIOR_BAD_EXPERIENCE": re.compile(
        r"\b(?:(?:ja|eu ja) (?:fiz|comprei|participei|entrei|paguei|tive)\b.{0,40}"
        r"\b(?:mentorias?|cursos?|programas?|consultorias?|treinamentos?)\b.{0,40}"
        r"\b(?:nao (?:apliquei|usei|coloquei|funcionou|deu certo|aproveitei|implementei|serviu)|nada em pratica"
        r"|nunca usei|dinheiro jogado)"
        r"|sou cetico com (?:mentoria|curso)s?)\b"),
    "SUCCESSION": re.compile(
        r"\b(?:(?:meu|minha) (?:filho|filha|genro|nora|sobrinho|neto) (?:vai|que vai|ta|esta) assumi\w*"
        r"|(?:estou|to|tou) passando (?:\w+ ){0,3}(?:pro|pra|para(?: o| a)?) (?:meu |minha )?(?:filho|filha|genro"
        r"|nora|sucessor)|sucessao|sucessor\w*)\b"),
    "CASH_TIGHT": re.compile(
        r"\b(?:caixa (?:esta |ta |anda )?apertado|(?:estou|to|tou|estamos|tamos) endividad\w*|safra so entra"
        r"|nao tenho esse dinheiro|sem caixa agora|o dinheiro so entra)\b"),
}
# closer: what the closer does (resolutions / compliance evidence); (pattern, needs a "?")
CLOSER = {
    "DECISION_ASK": (re.compile(
        r"\b(?:faz sentido (?:a gente |pra voce |pra voces |para voce |para voces )?(?:seguir|fechar|avancar|comecar"
        r"|entrar)|(?:voce|voces) (?:quer|querem|topa|topam) (?:entrar|fechar|seguir|participar|fazer parte)"
        r"|(?:podemos|posso) (?:fechar|te inscrever|fazer (?:a )?sua inscricao|garantir (?:a |sua )?vaga)"
        r"|pe na peia|voce entra|qual (?:e )?a sua decisao)\b"), False),
    "DECISION_ASK_SHORT": (re.compile(r"\b(?:vamos (?:fechar|seguir|avancar)(?: entao| juntos)?|fechamos)$"), True),
    "CAUSE_PROBE": (re.compile(
        r"\b(?:o que (?:exatamente |especificamente )?(?:voce |voces |o senhor |a senhora )?(?:precisa|precisam|quer"
        r"|querem|gostaria de) (?:pensar|avaliar|analisar|decidir|ver|entender)"
        r"|o que (?:esta|ta) na balanca|quando (?:voce|voces) (?:diz|fala|falam|dizem) (?:que )?(?:\w+ )?"
        r"(?:caro|pensar|analisar|avaliar|momento|tempo)"
        r"|em relacao a (?:que|o que)|comparando com (?:o )?que"
        r"|o que (?:te|lhe|voces) (?:preocupa|trava|impede|incomoda|segura)"
        r"|o que (?:precisaria|precisa) acontecer (?:para|pra))\b"), False),
    "TIMING_PROBE": (re.compile(r"\b(?:prioridade|momento|caixa|safra|quando (?:voce |voces )?pretende"
                                r"|outro investimento)\b"), True),
    "NUMBER_PROBE": (re.compile(r"\b(?:margem|custo|quanto sobra|lucro|quanto (?:voce|voces) (?:ganha|perde))\b"),
                     True),
    "TIME_PROBE": (re.compile(r"\b(?:agenda|dedica\w*|prioridade|tempo)\b"), True),
    "EXPERIENCE_PROBE": (re.compile(
        r"\b(?:o que (?:faltou|falhou|aconteceu|deu errado|impediu|travou|nao funcionou)"
        r"|por que (?:nao )?(?:aplicou|funcionou|deu certo|colocou)|como foi (?:essa|a) experiencia)\b"), True),
    "CASH_PROBE": (re.compile(r"\bquando (?:entra|vai entrar) (?:o caixa|a safra|o dinheiro|a receita)\b"), False),
    "PAYMENT_TERMS_MENTIONED": (re.compile(r"\b(?:a vista|\d{1,2} ?x|\d{1,2} vezes|parcel\w*|pix|cartao|boleto"
                                           r"|sem juros)\b"), False),
    "SECOND_SEAT_OFFERED": (re.compile(
        r"\bsegunda cadeira\b|\b(?:traga|trazer|traz) (?:o |a )?(?:seu |sua )?(?:socio|socia|esposa|marido|filho"
        r"|filha|pai|mae|conjuge|sucessor|genro|braco direito)\b"), False),
}
# Meet captions often drop the "?". A probe without one still counts when the line OPENS with a known
# interrogative structure (after short lead-ins: "Entendo. Qual é a sua prioridade"); a statement using
# the same words ("O momento é agora.", "Como eu falei, o tempo é curto") does not. DECISION_ASK_SHORT keeps
# needing the "?": "Vamos seguir." is also "let's move on" (fail closed).
_ASK = (r"^(?:(?:e|mas|entao|agora|hoje|certo|entendo|ok|perfeito|legal|beleza|sim|me (?:diz|conta|fala)"
        r"|deixa eu te perguntar|so pra entender) )*")
QUESTION_FORMS = {
    "TIMING_PROBE": re.compile(_ASK + r"(?:qual (?:e |seria )?(?:a )?(?:sua |tua )?prioridade"
                               r"|como (?:esta|ta|anda) (?:o |a )?(?:seu |sua )?(?:momento|caixa)"
                               r"|quando (?:voce |voces )?pretende)\b"),
    "NUMBER_PROBE": re.compile(_ASK + r"(?:qual (?:e |seria )?(?:a |o )?(?:sua |seu )?(?:margem|custo|lucro)"
                               r"|quanto (?:sobra|(?:voce|voces) (?:ganha|perde|lucra)))\b"),
    "TIME_PROBE": re.compile(_ASK + r"(?:quanto tempo (?:voce |voces )?(?:tem|consegue|conseguiria|teria|dedica|pode)"
                             r"|como (?:esta|ta) (?:a )?(?:sua )?agenda|qual (?:e |seria )?(?:a )?(?:sua )?prioridade)\b"),
    "EXPERIENCE_PROBE": re.compile(_ASK + r"(?:como foi (?:essa|a) experiencia"
                                   r"|o que (?:te |lhe )?(?:faltou|impediu|travou) (?:pra|para|de)"
                                   r"|por que (?:voce |voces )?nao (?:aplicou|colocou|implementou))\b"),
}
_PRICE_CUE = re.compile(r"\b(?:investimento|o valor|valor (?:do|da|e)|fica (?:em|por)|sai (?:por|a)|a vista|parcel\w*"
                        r"|\d{1,2} ?x|\d{1,2} vezes|preco (?:do|da|e))\b")
PILLARS = {"lucro_incontestavel": re.compile(r"\blucro incontestavel\b"),
           "fazenda_autonoma": re.compile(r"\bfazenda autonoma\b"),
           "alavanca_do_legado": re.compile(r"\b(?:alavanca do legado|pilar do legado|legado)\b")}
PROGRAM_BLOCKS = {"pillars": re.compile(r"\b(?:lucro incontestavel|fazenda autonoma|legado|sucessao)\b"),
                  "six_weeks": re.compile(r"\b(?:6|seis) semanas\b|\bprimeira vitoria\b|\bplacar\b"),
                  "year_rhythm": re.compile(r"\b(?:encontros? presencia\w*|imersa\w*|mentorias? mensa\w*"
                                            r"|encontros? online)\b")}


def buying_signal_value(text: str) -> str | None:
    """A lead line's BUYING_QUESTION as a Commercial State value: the lead's sentence that asks it (exact
    words, at most 10), else the matched words; None when the line asks none. Classifier Quality v1: the facts
    model stored "Pode pagar no cartão da empresa?" as a commercial term only, while OP-14 saw the buying
    question; the same lexical signal now also records it as a buying signal."""
    rx = LEAD["BUYING_QUESTION"]
    for sentence in re.split(r"(?<=[.?!])\s+", text):
        if m := rx.search(fold(sentence)):
            value = sentence.strip(" .,!?;:")
            return value if len(value.split()) <= 10 else m.group(0)
    return None


_DECISION_QUESTION = re.compile(
    r"\b(?:quem (?:mais )?(?:participa|decide|assina|aprova|bate o martelo|vai decidir|esta envolvido"
    r"|precisa (?:concordar|aprovar))|alguem (?:mais )?participa)\b")
_NAMED = re.compile(rf"\b(?P<p>{PARTY})\b")


def extract(segments: list[Segment]) -> list[Signal]:
    """Every signal of the call, in call order. One cross-line signal: DECIDER_NAMED, a lead line naming a
    person right after the closer asked who decides ("Quem participa da decisão?" -> "Meu sócio.")."""
    out: list[Signal] = []
    prev: tuple[str, str, str] | None = None
    for sid, role, text in segments:
        if role not in ("closer", "lead"):
            continue
        out += line_signals(sid, role, text)
        if role == "lead" and prev and prev[1] == "closer" and _DECISION_QUESTION.search(fold(prev[2])):
            m = _NAMED.search(fold(text))
            if m and party_key(m.group("p")):
                out.append(Signal("DECIDER_NAMED", (prev[0], sid), role, {"party": party_key(m.group("p"))}))
        prev = (sid, role, text)
    return out


@lru_cache(maxsize=8192)  # pure per line: re-reading a growing call costs O(new lines)
def line_signals(sid: str, role: str, text: str) -> tuple[Signal, ...]:
    out: list[Signal] = []
    f, p, question = fold(text), plain(text), "?" in text

    def add(kind: str, **details: Any) -> None:
        out.append(Signal(kind, (sid,), role, details))

    if (s := schedule(text)) is not None:
        owner = role if _OWNER.search(p) else None
        add("NEXT_STEP_SCHEDULED", **s, **({"owner": owner} if owner else {}))
        m = _WITH_PARTY.search(f)
        if m and _MEETING_CUE.search(p):
            add("DECISION_MEETING_SCHEDULED", party=party_key(m.group("p")), **s)
    if role == "lead":
        dep, party = decision_dependency(text)
        if dep:
            add("DECISION_DEPENDENCY", party=party)
        out += [Signal(kind, (sid,), role, {}) for kind, rx in LEAD.items() if rx.search(f)]
        return tuple(out)
    for kind, (rx, needs_q) in CLOSER.items():
        target = f.rstrip() if kind == "DECISION_ASK_SHORT" else f
        if (rx.search(target) and (question or not needs_q)) or (kind in QUESTION_FORMS
                                                                   and QUESTION_FORMS[kind].search(f)):
            add("DECISION_ASK" if kind == "DECISION_ASK_SHORT" else kind)
    if _MONEY.search(p) and _PRICE_CUE.search(f):
        add("PRICE_PRESENTED")
    for pillar, rx in PILLARS.items():
        if rx.search(f):
            add("PILLAR_MENTIONED", pillar=pillar)
    if blocks := [b for b, rx in PROGRAM_BLOCKS.items() if rx.search(f)]:
        add("PROGRAM_BLOCK_MENTIONED", blocks=blocks)
    return tuple(out)
