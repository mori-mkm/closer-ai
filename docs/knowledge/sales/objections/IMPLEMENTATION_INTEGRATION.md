# IMPLEMENTATION_INTEGRATION

## Metadata

- concept_id: `objection_category.IMPLEMENTATION_INTEGRATION`
- version: 0.1
- status: PROVISIONAL — **operation-dependent**: se o pilot não mostrar utilidade/discriminabilidade
  suficiente, pode ser fundida em OTHER ou em outra categoria (não decidido)
- source_strength: S4 (`SRC_HUBSPOT_OBJECTIONS`, menção — não taxonomia)

## Definition

Resistência em que o **esforço, a viabilidade ou o impacto operacional/técnico de colocar a solução em
funcionamento** é dito como barreira para avançar. Termos relacionados: implementation objection,
integration, migração, implantação, "doesn't integrate with", "no team to implement".

## Use when

- o lead diz que não tem equipe/tempo/capacidade para implantar ou migrar e por isso não segue;
- o lead diz que a solução não integra com a infraestrutura dele e isso impede avançar;
- o lead diz que o impacto operacional da implantação é inaceitável.

## Do not use when

- o lead **pergunta** como funciona a integração/implantação (pedido de informação);
- o receio é sobre o fornecedor cumprir o prometido → TRUST_RISK;
- o lead diz que a solução não resolve o problema dele → NEED_VALUE_FIT;
- o problema é **quando** implantar por prioridade/momento, não o esforço → TIMING_PRIORITY.

## Minimum transcript evidence

Uma dificuldade de implementação **explicitamente ligada** a não avançar, na fala do lead.

## Positive signals

Pistas contextuais, **não classificadores por palavra-chave**: "não temos equipe para", "não integra
com", "a migração inviabiliza", "não conseguimos parar a operação para implantar".

## Negative / falsifying signals

- "Como funciona a integração?" — pergunta neutra; **não** é objeção.
- "A integração é via API?" — pergunta técnica.
- "Tenho um pouco de receio da migração." — preocupação; só vira objeção se funcionar como barreira.

## Often confused with

- TRUST_RISK — receio de dar errado na migração;
- NEED_VALUE_FIT — "não funciona para o nosso sistema" (adequação × esforço);
- TIMING_PRIORITY — implantação "não cabe agora".

## Positive examples

*Sintéticos.*

- Lead: "Nosso time de TI são duas pessoas; não temos braço para uma migração dessas, então não dá."
- Lead: "Se não conversa com o nosso sistema de notas fiscais, não tem como a gente usar."

## Counterexamples

*Sintéticos.*

- Lead: "Quanto tempo leva a configuração inicial?" → pergunta.
- Lead: "Quem da nossa equipe precisa participar do treinamento?" → dúvida operacional.

## Ambiguous examples

*Sintético.* Lead: "Isso vai dar muito trabalho pra nossa equipe." (sem mais contexto) → barreira de
implantação ou comentário? AMBIGUOUS até o lead ligar isso à decisão.

## Observed vs inferred risks

- **Pergunta técnica ≠ objeção de implementação.** Observado: o lead quer entender a integração. Não
  observado: "acha difícil", "não tem capacidade técnica".
- Concern ≠ objection: preocupação com migração só é objeção quando dita como impedimento (proposal,
  CIT-O3).

## Framework mappings

Nenhum framework da pesquisa mapeia esta categoria de forma útil. Não usado.

## Source-backed notes

- `SRC_HUBSPOT_OBJECTIONS` (S4) menciona implementação entre as preocupações que podem estar escondidas
  atrás de objeções aparentemente simples e usa integração complexa como exemplo de preocupação a tratar.
- A pesquisa: evidência **MODERATE**; "comercialmente plausível", mas sem o mesmo suporte taxonômico de
  budget/authority/need/timing.
- Relevância para as operações reais do AI Closer **não verificada** (proposal, CIT-O5).

## Sources

- `SRC_HUBSPOT_OBJECTIONS` — S4

## Open questions

- A categoria aparece nas calls reais com frequência e concordância suficientes? Se não, fundir (OTHER ou
  outra) — decisão pós-pilot (CIT-O5).
- Fronteira com TRUST_RISK quando o receio é de migração.
