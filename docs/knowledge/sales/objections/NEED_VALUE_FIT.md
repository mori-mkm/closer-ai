# NEED_VALUE_FIT

## Metadata

- concept_id: `objection_category.NEED_VALUE_FIT`
- version: 0.1
- status: PROVISIONAL — **AI CLOSER PROVISIONAL ABSTRACTION** (fusão de três conceitos)
- source_strength: S4 (`SRC_HUBSPOT_OBJECTIONS`, para Need); S2 (`SRC_SPIN`, suporte conceitual); **AC** (a fusão)

## Definition

Resistência em que o lead diz que **não precisa** da solução, que o **benefício não compensa** ou que a
solução **não serve** para o caso dele. Termos relacionados: need objection, no need, "don't see the
value", "not a fit", sem necessidade, não vê valor, não se aplica.

A união Need + Value + Fit **não é categoria estabelecida nas fontes**: é decisão de parcimônia da v0.1
(AC), porque as três fronteiras são as de menor concordância esperada.

## Use when

- o lead nega explicitamente necessidade ("hoje não temos esse problema");
- o lead diz que o benefício/retorno não justifica avançar;
- o lead diz que a solução não resolve o que importa para ele ou não se aplica ao caso dele.

## Do not use when

- o lead reconhece o valor, mas diz que não pode pagar → PRICE_BUDGET;
- a barreira dita é o **esforço de implantar** → IMPLEMENTATION_INTEGRATION;
- a razão dita é um **fornecedor atual** preferido → COMPETITION_EXISTING_SOLUTION;
- o lead descreve um problema ou necessidade (discovery), sem resistir;
- o lead só **pergunta** como a solução ajudaria.

## Minimum transcript evidence

Negação explícita, pelo lead, de **necessidade, utilidade, benefício ou adequação**, ligada a não
avançar.

## Positive signals

Pistas contextuais, **não classificadores por palavra-chave**: "não precisamos", "não vejo valor", "não
resolve", "não serve para o nosso caso", "o ganho não compensa".

## Negative / falsifying signals

- "Resolve o nosso problema, mas não temos dinheiro." — valor aceito; barreira é preço.
- "Como isso ajudaria na nossa operação?" — pergunta, não negação.
- "Nosso maior problema hoje é o retrabalho." — necessidade expressa (discovery), não objeção.

## Often confused with

- PRICE_BUDGET — "não sei se vale esse preço";
- IMPLEMENTATION_INTEGRATION — "não funciona com o nosso sistema";
- COMPETITION_EXISTING_SOLUTION — solução atual (fornecedor × solução interna);
- TIMING_PRIORITY — "por enquanto não precisamos";
- TRUST_RISK — "não sei se isso funciona pra nós" (adequação × receio de resultado).

## Positive examples

*Sintéticos.*

- Lead: "Sinceramente, o controle que a gente tem hoje já dá conta; não vejo motivo para trocar."
- Lead: "Esse módulo cobre vendas, mas o nosso gargalo é logística, então não serve pra nós."

## Counterexamples

*Sintéticos.*

- Lead: "A ferramenta faz exatamente o que precisamos, só que o valor não cabe agora." → PRICE_BUDGET.
- Lead: "Vocês atendem empresas do nosso tamanho?" → pedido de informação.

## Ambiguous examples

*Sintético.* Lead: "Não sei se vale o que vocês estão pedindo." → valor ou preço? AMBIGUOUS
{NEED_VALUE_FIT, PRICE_BUDGET}; não inferir.

## Observed vs inferred risks

- **Questionar valor ≠ não ter necessidade.** "Não sei se compensa" é dúvida de valor, não negação de
  necessidade.
- Expressar necessidade ≠ objeção (`SRC_SPIN`). Descrever um problema é discovery.
- **Não observado:** "não entendeu o produto", "o closer não mostrou valor".

## Framework mappings

- SPIN (`SRC_SPIN`): necessidade implícita × explícita ajuda a não confundir necessidade com objeção nem
  com preço. **SPIN não é taxonomia de objeções.**
- BANT *Need* (via `SRC_HUBSPOT_OBJECTIONS`): dimensão de qualificação ≠ objeção.

## Source-backed notes

- `SRC_HUBSPOT_OBJECTIONS` (S4) trata Need como grupo principal: objeções em que o prospect não percebe
  como a solução o ajuda.
- A pesquisa: evidência **STRONG para Need**, **MODERATE para fundir Need + Value + Fit**; "as fontes não
  estabelecem consenso" sobre a fusão.
- Status quo sem fornecedor ("fazemos na planilha e funciona") cai aqui provisoriamente (AC, proposal
  CIT-O6).

Possível divisão futura (**não implementada**):

| Sub-conceito | O que resiste | Sintético |
|---|---|---|
| NEED | não há o problema | "Hoje não temos dificuldade com isso." |
| VALUE | o benefício não compensa | "O ganho não justifica mudar." |
| FIT | não serve para o caso | "Não resolve a parte que importa pra nós." |

## Sources

- `SRC_HUBSPOT_OBJECTIONS` — S4
- `SRC_SPIN` — S2 (conceitual)
- AI Closer abstraction — AC (fusão)

## Open questions

- Manter a fusão depois do pilot, ou separar NEED / VALUE / FIT? (CIT-O2) O pilot registra em nota qual
  sub-conceito o anotador leu.
- Solução interna/planilha: NEED_VALUE_FIT ou COMPETITION_EXISTING_SOLUTION? (CIT-O6)
