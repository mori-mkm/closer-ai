"""Grounding validator: generated text may not introduce facts absent from the call evidence."""
from __future__ import annotations

import pytest

from closer_ai.ai.grounding import has_date, ungrounded

EVIDENCE = "Olha, aqui eu não fecho nada sem o meu sócio aprovar. Te dou retorno na sexta-feira."


@pytest.mark.parametrize("text", [
    "O que o seu sócio precisa entender para conseguir avaliar essa decisão?",
    "Combine uma data objetiva de retorno.",
    "Consegue me dar o retorno na sexta-feira, como você falou?",
    "Quem mais participa dessa decisão?",
    "Faz sentido conversarmos depois que você falar com a sua sócia?",  # stem match: sócio/sócia
])
def test_grounded_text_passes(text):
    assert ungrounded(text, EVIDENCE) == []


@pytest.mark.parametrize("text, needle", [
    ("Então marcamos 5 de abril pra revisar. Faz sentido?", "abril"),
    ("Consegue falar com ele até quinta?", "quinta"),
    ("Fechamos amanhã?", "amanha"),
    ("Consegue decidir até 12/04?", "12/04"),
    ("Se ficar em R$ 50.000, resolve?", "50.000"),
    ("E se fosse 30% menos?", "%"),
    ("O seu CFO aprova isso?", "cfo"),
    ("A sua esposa participa da decisão?", "esposa"),
    ("Posso te dar um desconto?", "desconto"),
    ("Podemos parcelar em 12x?", "parcel"),
    ("Você já usou o Pipedrive para isso?", "Pipedrive"),
])
def test_invented_facts_are_flagged(text, needle):
    problems = ungrounded(text, EVIDENCE)
    assert any(needle in p for p in problems), problems


@pytest.mark.parametrize("placeholder", ["[data]", "[X]", "{produto}", "<X>", "TODO", "TBD"])
def test_placeholders_are_flagged_even_if_present_in_evidence(placeholder):
    text = f"Marcamos {placeholder} pra revisar?"
    assert any("placeholder" in p for p in ungrounded(text, f"{EVIDENCE} {placeholder}"))


def test_names_from_the_call_and_sentence_initial_words_pass():
    assert ungrounded("Renato, o que o seu sócio precisa ver?", "Bom dia, Renato. " + EVIDENCE) == []
    assert ungrounded("Quem decide? Faz sentido?", EVIDENCE) == []


@pytest.mark.parametrize("text, expected", [
    ("sexta-feira", True), ("primeira semana de abril", True), ("12/04", True), ("semana que vem", True),
    ("depois", False), ("mais pra frente", False), ("qualquer dia", False), ("em breve", False),
])
def test_has_date_rejects_vague_timing(text, expected):
    assert has_date(text) is expected
