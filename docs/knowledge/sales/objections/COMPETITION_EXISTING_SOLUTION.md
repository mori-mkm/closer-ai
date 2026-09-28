# COMPETITION_EXISTING_SOLUTION

## Metadata

- concept_id: `objection_category.COMPETITION_EXISTING_SOLUTION`
- version: 0.1
- status: PROVISIONAL (taxonomy candidate; not a domain enum value)
- source_strength: S4 (`SRC_HUBSPOT_OBJECTIONS`); framework mapping S5 (`SRC_MEDDPICC`)

## Definition

Resistência em que o lead apresenta uma **alternativa existente** — fornecedor atual, concorrente com quem
já negocia ou contrato vigente com outro — como razão para não avançar. Termos relacionados: competitor
objection, "happy with current vendor", "already signed with X", concorrente, fornecedor atual.

## Use when

- o lead diz estar satisfeito com o fornecedor atual e por isso não troca;
- o lead diz que já fechou ou está fechando com outro fornecedor;
- o lead diz estar preso a contrato com outro fornecedor e isso impede avançar.

## Do not use when

- o lead só **informa** que avalia outras opções ("também estamos conversando com X") — informação
  competitiva, não resistência;
- o lead pede comparação com concorrente sem resistir;
- a alternativa é "não fazer nada"/processo interno sem fornecedor → provisoriamente NEED_VALUE_FIT
  (CIT-O6);
- o concorrente é mencionado pelo closer.

## Minimum transcript evidence

A alternativa existente aparece, na fala do lead, **como razão para não avançar ou como impedimento**.

## Positive signals

Pistas contextuais, **não classificadores por palavra-chave**: "já usamos X e estamos satisfeitos", "já
fechamos com", "temos contrato com X até", "não vamos trocar de fornecedor".

## Negative / falsifying signals

- "Também estamos avaliando o fornecedor X." — informação, sem resistência.
- "Hoje usamos o sistema X." — fato neutro.
- "Qual a diferença de vocês para o X?" — pergunta comparativa.

## Often confused with

- NEED_VALUE_FIT — status quo e "o que temos já basta";
- TIMING_PRIORITY — "só depois que acabar o contrato atual";
- TERMS_PROCESS — o contrato vigente como impedimento formal;
- TRUST_RISK — preferir o fornecedor conhecido por receio do novo.

## Positive examples

*Sintéticos.*

- Lead: "A gente usa o sistema X há cinco anos e está todo mundo satisfeito; não vejo motivo pra trocar
  de fornecedor."
- Lead: "Semana passada assinamos com outra empresa para isso, então não tem como seguir."

## Counterexamples

*Sintéticos.*

- Lead: "Estamos vendo duas outras propostas também." → informação competitiva.
- Lead: "Vocês integram com o sistema X, que já usamos?" → pergunta.

## Ambiguous examples

*Sintético.* Lead: "Temos contrato com o fornecedor atual até dezembro." → barreira competitiva,
de momento ou contratual? Sem fala que diga o que impede, AMBIGUOUS {COMPETITION_EXISTING_SOLUTION,
TIMING_PRIORITY}.

## Observed vs inferred risks

- **Concorrente mencionado ≠ objeção competitiva.** Observado: existe alternativa. Não observado:
  "prefere o concorrente", "está usando o concorrente para negociar preço".

## Framework mappings

- MEDDPICC *Competition* (`SRC_MEDDPICC`): elemento separado da qualificação; existir concorrência ≠
  objeção competitiva.

## Source-backed notes

- `SRC_HUBSPOT_OBJECTIONS` (S4) trata Competition como grupo próprio, com casos como prospect já
  negociando com outro fornecedor, preso a contrato com concorrente ou satisfeito com concorrente.
- A pesquisa: evidência **STRONG** para competition como tipo de objeção (convergência S4 + S5, não
  pesquisa peer-reviewed).
- Status quo não é categoria v0.1; quando o bloqueio dito é o fornecedor atual, cai aqui (proposal).

## Sources

- `SRC_HUBSPOT_OBJECTIONS` — S4
- `SRC_MEDDPICC` — S5 (mapping)

## Open questions

- Solução interna/planilha: aqui ou NEED_VALUE_FIT? (CIT-O6)
- Contrato vigente com concorrente: COMPETITION, TIMING ou TERMS? Pilot.
