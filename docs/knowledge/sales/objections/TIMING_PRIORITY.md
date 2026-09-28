# TIMING_PRIORITY

## Metadata

- concept_id: `objection_category.TIMING_PRIORITY`
- version: 0.1
- status: PROVISIONAL (taxonomy candidate; not a domain enum value)
- source_strength: S4 (`SRC_HUBSPOT_OBJECTIONS`, `SRC_GONG_OBJECTIONS`)

## Definition

Resistência em que o **momento** ou a **prioridade atual** é dito como razão para não avançar agora ou
adiar. Termos relacionados: timing objection, "not now", "not a priority", objeção de prazo/momento,
"não é prioridade".

## Use when

- o lead diz que agora não é o momento e dá **um motivo de momento/prioridade** ("outro projeto vem
  antes", "só entra no plano do ano que vem");
- o lead declara que o tema não é prioridade atual e que isso impede seguir;
- o lead liga uma data ou evento ao adiamento da decisão.

## Do not use when

- o lead tenta encerrar ou adiar **sem motivo concreto** ("me manda por e-mail que eu te procuro") →
  brush-off: AMBIGUOUS, não TIMING_PRIORITY;
- o motivo dito é **verba** que só existe numa data → fronteira com PRICE_BUDGET (ver Open questions);
- o lead só informa um cronograma sem resistir ("queremos começar mês que vem");
- o prazo resistido é de **implantação** da solução → IMPLEMENTATION_INTEGRATION;
- o adiamento vem de uma etapa formal de compra → TERMS_PROCESS.

## Minimum transcript evidence

Uma fala do lead que liga **momento ou prioridade** ao **impedimento ou adiamento** de avançar, com o
motivo dito.

## Positive signals

Pistas contextuais, **não classificadores por palavra-chave**: "agora não", "não é prioridade", "depois
de [evento]", "ano que vem", "outro projeto na frente" — quando justificam não avançar.

## Negative / falsifying signals

- "Talvez mais para frente." — sem motivo; pode ser timing real ou brush-off.
- "Me manda a proposta por e-mail e depois a gente vê." — afastamento sem barreira dita.
- "Queremos começar em março." — cronograma informado, sem resistência.

## Often confused with

- brush-off (não é categoria; AMBIGUOUS quando não há motivo dito);
- PRICE_BUDGET — ciclo orçamentário;
- TERMS_PROCESS — espera por etapa formal de compra;
- NEED_VALUE_FIT — "por enquanto não precisamos" (necessidade ausente × adiada);
- AUTHORITY_INTERNAL_BUY_IN — adiamento até a reunião de quem aprova;
- COMPETITION_EXISTING_SOLUTION — "só depois que acabar o contrato atual";
- IMPLEMENTATION_INTEGRATION — implantação "não cabe agora" (momento × esforço).

## Positive examples

*Sintéticos.*

- Lead: "Este semestre a equipe inteira está na troca do ERP; qualquer projeto novo só depois disso."
- Lead: "Faz sentido, mas hoje isso não está entre as três prioridades da diretoria."

## Counterexamples

*Sintéticos.*

- Lead: "Qual é o prazo de ativação depois de assinar?" → pergunta, sem resistência.
- Lead: "Me manda o material e qualquer coisa eu te chamo." → sem motivo dito; não TIMING_PRIORITY.

## Ambiguous examples

*Sintético.* Lead: "Não sei se é pra agora." (sem mais contexto) → momento, preço ou necessidade? Categoria
UNKNOWN/AMBIGUOUS conforme a guideline.

## Observed vs inferred risks

- **Observado:** o lead pediu para adiar ou disse que não é prioridade. **Não observado:** "está sem
  interesse", "está enrolando", "é desculpa". Brush-off é leitura de intenção; nunca registrar como fato.
- Não converter "talvez depois" em TIMING_PRIORITY com baixa confiança: o contrato não tem `confidence`;
  use AMBIGUOUS (proposal).

## Framework mappings

- BANT *Timing* (via `SRC_HUBSPOT_OBJECTIONS`): dimensão de qualificação ≠ objeção. Discutir prazo não é
  resistir.

## Source-backed notes

- `SRC_HUBSPOT_OBJECTIONS` (S4) relaciona timing a urgência/prioridade e diz explicitamente que timing
  genuíno deve ser distinguido de brush-off.
- `SRC_GONG_OBJECTIONS` (S4 aqui) lista timing entre os tipos recorrentes de objeção.
- A pesquisa: não existe regra lexical confiável para separar timing de brush-off; depende de contexto.
- Regra "motivo concreto dito → TIMING_PRIORITY; sem motivo → AMBIGUOUS" é **AC** (proposal).

## Sources

- `SRC_HUBSPOT_OBJECTIONS` — S4
- `SRC_GONG_OBJECTIONS` — S4 (uso descritivo)

## Open questions

- Ciclo orçamentário ("orçamento só reabre em janeiro"): a pesquisa descreve casos parecidos ora como
  TIMING_PRIORITY, ora como PRICE_BUDGET. Pilot decide; até lá, AMBIGUOUS se o dito não separar.
- Frequência de brush-off nas operações reais (GL-2 da guideline).
