# PRICE_BUDGET

## Metadata

- concept_id: `objection_category.PRICE_BUDGET`
- version: 0.1
- status: PROVISIONAL (taxonomy candidate; not a domain enum value)
- source_strength: S1 (`SRC_SCHURR`), S4 (`SRC_HUBSPOT_OBJECTIONS`, `SRC_GONG_OBJECTIONS`); framework mapping S5

## Definition

Resistência em que o **montante**, a **verba disponível** ou a **capacidade de pagar** funciona como
barreira dita para avançar. Termos relacionados: price objection, budget objection, "too expensive",
objeção de preço, falta de verba/orçamento.

## Use when

- o lead declara o preço excessivo **em relação à decisão de avançar**;
- o lead diz que não há verba, que a verba não comporta ou que não consegue pagar;
- o gasto é declarado incompatível com a capacidade atual e isso impede ou adia seguir.

## Do not use when

- o lead só **pergunta** preço, condições ou valores (pedido de informação);
- o preço aparece, mas a barreira dita é **retorno/valor** ("não vejo retorno que justifique") →
  considere NEED_VALUE_FIT;
- a barreira dita é a **estrutura contratual** (duração, regra de compras) → TERMS_PROCESS;
- o lead fala de preço no passado já superado, em hipótese, ou comparando com outro gasto sem resistir à
  oferta;
- o preço é mencionado por terceiros ou pelo closer.

## Minimum transcript evidence

Uma fala do lead que liga **custo ou verba** à **dificuldade de avançar**. Menção a valor, sozinha, não
basta.

## Positive signals

Pistas contextuais, **não classificadores por palavra-chave**: "caro", "orçamento", "budget", "não temos
verba", "não conseguimos pagar", "não cabe" — **somente** quando ligadas à decisão de seguir.

## Negative / falsifying signals

- "Quanto custa?" / "Qual o valor do plano?" — pergunta neutra.
- "Achei que ia ser caro, mas ficou abaixo do que eu esperava." — "caro" presente, sem resistência.
- "Caro mesmo é o que gastamos hoje com retrabalho." — "caro" não se refere à oferta.
- "Não vejo retorno suficiente para investir isso." — preço presente, barreira dita é valor.

## Often confused with

- NEED_VALUE_FIT — "não sei se vale esse preço" (preço × valor).
- TIMING_PRIORITY — verba ligada a ciclo/data ("orçamento só abre em janeiro").
- TERMS_PROCESS — forma de pagamento × estrutura de contrato.

## Positive examples

*Sintéticos.*

- Lead: "Gostei da proposta, mas esse valor passa do que temos reservado para o ano."
- Lead: "Do jeito que está, não conseguimos pagar a entrada."

## Counterexamples

*Sintéticos.*

- Lead: "A proposta vem com o valor total ou por mês?" → pedido de informação, sem resistência.
- Lead: "O valor mensal já inclui o suporte?" → pergunta sobre o preço, sem resistência.

## Ambiguous examples

*Sintético.* Lead: "É bastante dinheiro." (sem fala seguinte que explique) → comentário, preocupação ou
objeção? AMBIGUOUS até o contexto decidir.

## Observed vs inferred risks

- **Observado:** o lead falou de preço/verba. **Não observado:** "a empresa não pode pagar", "está sem
  dinheiro", "está usando preço como desculpa".
- "Está caro" pode esconder valor, risco ou aprovação interna; a pesquisa diz que a forma superficial ≠
  causa. Categorize pelo dito; a causa suposta vai para nota INFERIDO.

## Framework mappings

- BANT *Budget* (via `SRC_HUBSPOT_OBJECTIONS`) e Sandler *Budget* (`SRC_SANDLER`): **budget discutido ≠
  objeção de budget**. Só é objeção quando o tema funciona como barreira.

## Source-backed notes

- `SRC_HUBSPOT_OBJECTIONS` (S4) trata Budget como um dos quatro grandes grupos de objeção, com "too
  expensive" e falta de fundos como exemplos.
- `SRC_SCHURR` (S1) estudou objeções de preço diretamente (escopo: venda industrial).
- `SRC_GONG_OBJECTIONS` (S4 aqui) lista preço entre os temas recorrentes de objeção.
- **Conflito interno da pesquisa:** "nossa verba só retorna em janeiro" é descrito como possível
  PRICE_BUDGET com componente temporal, enquanto "me procure em janeiro porque o orçamento só reabre" é
  descrito como primariamente TIMING_PRIORITY. Não há regra estável; ver Open questions.
- Fronteira com TERMS_PROCESS ("não cabe pagar à vista" = PRICE_BUDGET; "não assinamos contrato de três
  anos" = TERMS_PROCESS) é **AC**, a validar no pilot.

## Sources

- `SRC_HUBSPOT_OBJECTIONS` — S4
- `SRC_SCHURR` — S1
- `SRC_GONG_OBJECTIONS` — S4 (uso descritivo)
- `SRC_SANDLER` — S5 (mapping)

## Open questions

- Barreira de **ciclo orçamentário** (verba existe, mas só numa data): PRICE_BUDGET, TIMING_PRIORITY ou
  AMBIGUOUS por padrão? Decidir com dados do pilot.
- Forma de pagamento (parcelamento, entrada) é PRICE_BUDGET ou TERMS_PROCESS quando a condição é o que
  impede? (AC provisória acima.)
