# Glossary

Termos de domínio usados no código e na documentação. Manter em ordem alfabética.

- **Buying Signal** — indício, dentro da call, de que o lead está inclinado a fechar.
- **Call** — uma chamada de venda gravada/transcrita, associada a um Deal. Nunca carrega
  outcome comercial — ver Outcome.
- **Call↔Deal Matching** — processo de associar uma Call a um Deal por evidência (id externo,
  email, telefone, proximidade de nome/data), nunca por certeza absoluta. Ver
  `docs/domain/DEAL_MODEL.md` (`CallDealMatch`).
- **Closer** — vendedor responsável por conduzir a call de fechamento.
- **Commitment** — compromisso assumido por lead ou closer durante a call (próximo passo).
- **Deal** — oportunidade comercial no CRM; unidade analítica central do produto. Possui no
  máximo um Outcome comercial final, nunca duplicado por Call associada.
- **Golden Set** — amostra de calls rotulada manualmente, usada como referência de qualidade
  para avaliar extração automática.
- **Lead** — pessoa/empresa potencial cliente associada a um Deal.
- **Matching Confidence** — nível (HIGH/MEDIUM/LOW) + score numérico opcional que expressa o
  quão forte é a evidência de um `CallDealMatch` — nunca um número solto sem semântica.
- **Matching Method** — a técnica usada para produzir um `CallDealMatch` (id externo exato,
  email exato, nome+data, manual, etc.) — determinístico ou heurístico, nunca ambíguo sobre
  qual dos dois.
- **Moment** — trecho relevante da call marcado por tipo (objeção, sinal, risco, etc.).
- **Objection** — resistência expressa pelo lead durante a call.
- **Outcome** — resultado final do Deal (ganho, perdido, etc.) e métricas associadas. Existe
  **só no Deal**, nunca na Call — ver `docs/domain/DEAL_MODEL.md`.
- **Risk** — sinal de que o deal pode não fechar.
- **Stage** — etapa do Deal no funil de vendas. Eixo separado de Outcome: won/lost nunca é um
  Stage, só um Outcome.
- **Stage Event** — registro histórico (append-only) de uma transição de Stage de um Deal —
  nunca sobrescrito pelo `current_stage` cacheado no Deal.
- **Strategy** — abordagem usada pelo closer para lidar com uma objeção ou avançar o deal.
