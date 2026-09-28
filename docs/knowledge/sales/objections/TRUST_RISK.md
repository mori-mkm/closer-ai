# TRUST_RISK

## Metadata

- concept_id: `objection_category.TRUST_RISK`
- version: 0.1
- status: PROVISIONAL — **AI CLOSER PROVISIONAL ABSTRACTION** (união de trust e risk)
- source_strength: S4 (`SRC_HUBSPOT_OBJECTIONS`); **AC** (a união)

## Definition

Resistência em que o lead diz ter **receio de um resultado negativo** ou **dúvida relevante sobre a
capacidade da solução/empresa de cumprir o prometido**, e liga isso a não avançar. Termos relacionados:
trust objection, risk, "how do I know it will work", medo de dar errado, receio, desconfiança do
fornecedor.

`TRUST_RISK` **não é categoria acadêmica consolidada**: a pesquisa diz que trust e risk não aparecem
juntos como categoria nas fontes; a junção é abstração operacional (AC).

## Use when

- o lead diz que teme que a solução não funcione no caso dele e isso impede seguir;
- o lead declara que uma experiência negativa anterior o faz não querer avançar agora;
- o lead questiona a capacidade do fornecedor de entregar e condiciona a decisão a isso.

## Do not use when

- o lead só **pede** prova, case ou referência ("vocês têm case de empresa grande?") → pedido de
  informação;
- o receio dito é sobre o **esforço técnico de implantar** → IMPLEMENTATION_INTEGRATION;
- o lead diz que a solução não serve → NEED_VALUE_FIT;
- o lead só relata uma experiência ruim passada sem ligá-la à decisão atual.

## Minimum transcript evidence

Uma fala do lead com **receio ou dúvida** sobre resultado/fornecedor **ligada à disposição de avançar**.

## Positive signals

Pistas contextuais, **não classificadores por palavra-chave**: "tenho medo de", "como vou saber que
funciona", "já nos queimamos com", "não sei se vocês conseguem entregar" — quando ligadas à decisão.

## Negative / falsifying signals

- "Vocês têm algum cliente parecido com a gente?" — pedido de informação.
- "Já tivemos problema com outra plataforma." (sem ligação com a decisão) — experiência observada, não
  objeção automática.
- "Tenho um pouco de receio da migração." — preocupação; objeção só se funcionar como barreira (e aí
  pode ser IMPLEMENTATION_INTEGRATION).

## Often confused with

- NEED_VALUE_FIT — "não sei se isso resolve pra nós";
- IMPLEMENTATION_INTEGRATION — receio de migração/integração;
- COMPETITION_EXISTING_SOLUTION — preferir o fornecedor conhecido;
- pedido de prova/case (não é objeção).

## Positive examples

*Sintéticos.*

- Lead: "A última empresa que contratamos sumiu depois da venda; antes de ter garantia de suporte eu não
  fecho."
- Lead: "Meu receio é pagar tudo isso e a ferramenta não aguentar o nosso volume. Enquanto eu não tiver
  segurança, fica parado."

## Counterexamples

*Sintéticos.*

- Lead: "Vocês podem me passar o contato de um cliente de referência?" → pedido de informação.
- Lead: "Tivemos um fornecedor ruim anos atrás, mas vocês estão bem recomendados." → experiência passada,
  sem resistência atual.

## Ambiguous examples

*Sintético.* Lead: "Não sei se isso funciona para uma operação como a nossa." → dúvida de risco (TRUST_RISK)
ou de adequação (NEED_VALUE_FIT)? AMBIGUOUS se o contexto não decidir.

## Observed vs inferred risks

- **Experiência ruim passada ≠ desconfiança atual automaticamente.** Observado: houve experiência
  negativa. Não observado: "não confia no vendedor", "está desconfiado".
- Não usar tom, hesitação ou demora como evidência de desconfiança.
- A distinção objeção × contra-argumento (crença prévia contrariada, `SRC_HUNT_BASHAW`) **não** é label
  aqui: anote como objeção; crença prévia só se dita.

## Framework mappings

Nenhum framework da pesquisa mapeia esta categoria de forma útil. Não usado.

## Source-backed notes

- `SRC_HUBSPOT_OBJECTIONS` (S4) inclui trust entre as causas fundamentais de objeções e cita
  preocupações com risco, compromisso, fornecedor e capacidade de entregar valor.
- A pesquisa classifica o suporte como **MODERATE** e diz que separar RISK de TRUST é teoricamente
  possível, mas **não sustentado** por critérios discriminantes nas fontes.

## Sources

- `SRC_HUBSPOT_OBJECTIONS` — S4
- AI Closer abstraction — AC (união)

## Open questions

- Manter a união ou separar TRUST (fornecedor) de RISK (resultado)? Só com dados do pilot (CIT-O2).
- Fronteira com IMPLEMENTATION_INTEGRATION quando o receio é de migração.
