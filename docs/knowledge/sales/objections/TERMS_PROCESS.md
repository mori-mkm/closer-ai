# TERMS_PROCESS

## Metadata

- concept_id: `objection_category.TERMS_PROCESS`
- version: 0.1
- status: PROVISIONAL — **operation-dependent** (depende de venda B2B com processo formal); se o pilot
  não mostrar utilidade/discriminabilidade, pode ser fundida em outra categoria (não decidido)
- source_strength: S4 (`SRC_HUBSPOT_OBJECTIONS`); framework mapping S5 (`SRC_MEDDPICC`)

## Definition

Resistência em que **condições comerciais/contratuais** (duração, cláusulas, formato de contratação) ou o
**processo formal de compra** são ditos como impedimento ou condição para avançar. Termos relacionados:
contract terms, paper process, procurement, cláusula, prazo de contrato, regra de compras.

## Use when

- o lead recusa um termo contratual e isso impede fechar ("não assinamos contrato de três anos");
- o lead diz que a regra de compras/jurídico **não permite** o formato proposto;
- o lead impõe mudança de termo como condição para seguir.

## Do not use when

- o lead só descreve o **processo normal** ("nosso jurídico vai revisar o contrato", "compras precisa
  cadastrar vocês") — processo ≠ barreira;
- o lead pergunta sobre termos (multa, prazo, forma de assinatura) sem resistir;
- a barreira dita é o **valor** ou a capacidade de pagar → PRICE_BUDGET;
- a barreira é a **aprovação de uma pessoa** → AUTHORITY_INTERNAL_BUY_IN.

## Minimum transcript evidence

O termo ou processo **funciona, na fala do lead, como impedimento ou condição** para avançar.

## Positive signals

Pistas contextuais, **não classificadores por palavra-chave**: "não assinamos", "nossa política não
permite", "o jurídico não aceita essa cláusula", "só fechamos se o contrato for".

## Negative / falsifying signals

- "Nosso jurídico vai revisar o contrato." — etapa normal, não objeção automaticamente.
- "Qual é a multa se cancelarmos?" — pergunta, salvo resistência explícita.
- "O contrato é assinado digitalmente?" — dúvida operacional.

## Often confused with

- PRICE_BUDGET — forma de pagamento (parcelamento, entrada);
- AUTHORITY_INTERNAL_BUY_IN — aprovação interna × regra formal;
- TIMING_PRIORITY — espera pela etapa de compras;
- COMPETITION_EXISTING_SOLUTION — contrato vigente com outro fornecedor.

## Positive examples

*Sintéticos.*

- Lead: "Contrato com fidelidade de 24 meses a gente não assina; é política da empresa."
- Lead: "O nosso jurídico não aceita foro fora do nosso estado; do jeito que está, não dá para assinar."

## Counterexamples

*Sintéticos.*

- Lead: "Manda a minuta que o jurídico dá uma olhada esta semana." → processo normal.
- Lead: "Vocês emitem nota fiscal de serviço?" → pergunta.

## Ambiguous examples

*Sintético.* Lead: "Se der para parcelar em 12 vezes, a gente segue." → condição de pagamento: preço
(PRICE_BUDGET) ou termo (TERMS_PROCESS)? A própria pesquisa lista as duas. AMBIGUOUS até o pilot.

## Observed vs inferred risks

- **Processo mencionado ≠ processo como barreira.** Observado: existe etapa formal. Não observado:
  "o jurídico vai barrar", "estão criando obstáculo".

## Framework mappings

- MEDDPICC *Paper Process* e *Decision Process* (`SRC_MEDDPICC`): passos entre decisão e assinatura são
  fenômeno distinto; existir paper process ≠ objeção.

## Source-backed notes

- `SRC_HUBSPOT_OBJECTIONS` (S4) apresenta objeções sobre duração contratual e formas de pagamento.
- A pesquisa: evidência **MODERATE**, "parcialmente dependente de vendas B2B complexas"; PROCUREMENT
  separado não é recomendado na v0.1.
- Fronteira com PRICE_BUDGET ("não cabe à vista" = PRICE; estrutura de contrato = TERMS) é **AC**, a
  validar.
- Relevância para as operações reais do AI Closer **não verificada** (proposal, CIT-O5).

## Sources

- `SRC_HUBSPOT_OBJECTIONS` — S4
- `SRC_MEDDPICC` — S5 (mapping)

## Open questions

- Condição de pagamento: PRICE_BUDGET ou TERMS_PROCESS?
- A categoria aparece nas operações reais (venda high-ticket, não necessariamente B2B enterprise)?
  Decisão pós-pilot (CIT-O5).
