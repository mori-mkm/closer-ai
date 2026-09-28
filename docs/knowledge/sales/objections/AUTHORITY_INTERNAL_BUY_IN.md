# AUTHORITY_INTERNAL_BUY_IN

## Metadata

- concept_id: `objection_category.AUTHORITY_INTERNAL_BUY_IN`
- version: 0.1
- status: PROVISIONAL (taxonomy candidate; not a domain enum value)
- source_strength: S4 (`SRC_HUBSPOT_OBJECTIONS`, `SRC_GONG_OBJECTIONS`); framework mapping S5

## Definition

Resistência em que o lead diz que **não pode aprovar sozinho** ou que a **aprovação/concordância de
outra pessoa** é uma condição que impede avançar. Termos relacionados: authority objection, internal
buy-in, "need approval", "CFO approval", aprovação da diretoria, alçada, sócio precisa aprovar.

## Use when

- o lead declara falta de alçada/poder de decisão ("não tenho autonomia para fechar isso");
- o lead diz que sem a aprovação de alguém a compra **não segue** ("sem o OK do financeiro não assino");
- o lead diz que não consegue convencer/vender internamente.

## Do not use when

- o lead só diz que vai **conversar** ou **mostrar** a proposta a alguém ("vou falar com meu sócio") —
  prova que existe outro stakeholder, não que há bloqueio de autoridade;
- o lead descreve o processo normal de decisão sem resistir ("quem assina é a diretoria");
- a resistência é **de outra pessoa**, relatada pelo lead que não a assume (GL-1 da guideline);
- a etapa formal é procurement/jurídico/regra de compras → TERMS_PROCESS.

## Minimum transcript evidence

Uma fala do lead com **restrição explícita ao poder de decisão** ou **necessidade explícita de aprovação
que impede o avanço**.

## Positive signals

Pistas contextuais, **não classificadores por palavra-chave**: "não posso aprovar", "precisa ser aprovado
por", "sem o OK de", "não é decisão minha", "não consigo vender isso internamente".

## Negative / falsifying signals

- "Vou conversar com meu sócio." — stakeholder existe; nenhuma restrição dita.
- "Vou mostrar para minha diretora." — idem.
- "Quem assina os contratos aqui é o financeiro." — processo informado, sem resistência.

## Often confused with

- processo normal de decisão / consulta a stakeholder (não é objeção);
- TERMS_PROCESS — aprovação por compras/jurídico como etapa formal;
- TIMING_PRIORITY — "só consigo levar isso na reunião de conselho do mês que vem".

## Positive examples

*Sintéticos.*

- Lead: "Eu gosto, mas acima de 20 mil não tenho alçada; sem o diretor aprovar não sai."
- Lead: "O CFO já disse que ferramenta nova só com aprovação dele, e hoje ele não aprovaria."

## Counterexamples

*Sintéticos.*

- Lead: "Vou apresentar isso para a minha sócia amanhã." → consulta, sem bloqueio dito.
- Lead: "Quem aprova compras aqui é o financeiro; já passei pra eles e não tem impedimento." → processo
  de decisão informado, sem barreira.

## Ambiguous examples

*Sintético.* Lead: "Preciso ver com o conselho antes." → etapa normal ou bloqueio de autoridade? Sem fala
que diga que a decisão não é dele, AMBIGUOUS (ou não anotar, conforme a guideline).

## Observed vs inferred risks

- **Stakeholder mencionado ≠ bloqueio de autoridade.** Observado: há outra pessoa envolvida. Não
  observado: "não tem poder de decisão", "o sócio é o economic buyer", "o sócio vai recusar", "está usando
  o sócio como desculpa".
- Cargo não prova autoridade nem falta dela.

## Framework mappings

- BANT *Authority* (via `SRC_HUBSPOT_OBJECTIONS`), MEDDPICC *Economic Buyer* e *Decision Process*
  (`SRC_MEDDPICC`), Sandler *Decision* (`SRC_SANDLER`). **Economic Buyer existe ≠ objeção de autoridade.**
  Discutir o processo de decisão não é resistir.

## Source-backed notes

- `SRC_HUBSPOT_OBJECTIONS` (S4) define authority objection como incapacidade de aprovar sozinho ou
  necessidade de concordância de outros stakeholders.
- `SRC_GONG_OBJECTIONS` (S4 aqui) menciona internal buy-in como tema recorrente de objeção.
- A pesquisa: esta é uma das áreas em que observado × inferido é essencial; "vou conversar com minha
  diretora" não basta.
- **Divergência registrada:** o enum v0 junta `trust_authority`; a guideline v0 usa "preciso falar com meu
  sócio" como exemplo de `trust_authority`. Esta unidade exige restrição explícita (proposal). Item da
  guideline v0.1.

## Sources

- `SRC_HUBSPOT_OBJECTIONS` — S4
- `SRC_GONG_OBJECTIONS` — S4 (uso descritivo)
- `SRC_MEDDPICC` — S5 (mapping)
- `SRC_SANDLER` — S5 (mapping)

## Open questions

- Onde fica "preciso aprovar internamente" sem dizer que bloqueia? (pilot, junto de GL-1)
- Decisor do lado do lead com papel `other` não ancora episódio (D5 do contrato, aberta).
