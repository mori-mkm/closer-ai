# Glossary

Termos de domínio usados no código e na documentação. Manter em ordem alfabética.

- **Buying Signal** — indício, dentro da call, de que o lead está inclinado a fechar.
- **Call** — uma chamada de venda gravada/transcrita, associada a um Deal. Nunca carrega
  outcome comercial — ver Outcome.
- **Call↔Deal Matching** — processo de associar uma Call a um Deal por evidência (id externo,
  email, telefone, proximidade de nome/data), nunca por certeza absoluta. `CallDealMatch` é
  candidato; a relação atual vem só de `MatchDecision` + `resolve_current_match` (ADR-003).
- **Closer** — vendedor responsável por conduzir a call de fechamento.
- **Commitment** — compromisso assumido por lead ou closer durante a call (próximo passo).
- **Deal** — negociação comercial canônica; unidade analítica central do produto. Não é o card do
  CRM: a ligação card → Deal é uma decisão de identidade (ADR-002). Possui no máximo um Outcome
  comercial canônico, nunca duplicado por Call associada.
- **E0 / E1 / E2** — braços experimentais do classifier de objeções: só transcript; + guia curto de
  taxonomia; + full-context knowledge (Knowledge Context Builder). E2 não é RAG semântico.
- **Golden Set** — amostra de calls rotulada manualmente, usada como referência de qualidade
  para avaliar extração automática.
- **Lead** — pessoa/empresa potencial cliente associada a um Deal.
- **Matching Confidence** — nível (HIGH/MEDIUM/LOW) + score numérico opcional que expressa o
  quão forte é a evidência de um `CallDealMatch` — nunca um número solto sem semântica.
- **Matching Method** — a técnica usada para produzir um `CallDealMatch` (id externo exato,
  email exato, nome+data, manual, etc.) — determinístico ou heurístico, nunca ambíguo sobre
  qual dos dois.
- **MatchDecision** — decisão autoritativa (automática ou manual) do matching de uma Call, numa
  cadeia linear por call; o head define a relação atual Call → Deal (ADR-003).
- **Moment** — trecho relevante da call marcado por tipo (objeção, sinal, risco, etc.).
- **Objection** — resistência expressa pelo lead durante a call.
- **Outcome** — resultado comercial do Deal. Existe **só no Deal**, nunca na Call. O canônico
  (`won`/`rejected`/`open`/`unknown`) vem do `OutcomeAssessment` atual (ADR-001); `Deal.outcome` é só
  a projeção legada do estado do CRM.
- **Risk** — sinal de que o deal pode não fechar.
- **Source record** — registro operacional de um sistema de origem (ex.: card do Kommo); nunca é
  um Deal por si só (ADR-002).
- **Stage** — etapa do Deal no funil de vendas. Eixo separado de Outcome: won/lost nunca é um
  Stage, só um Outcome.
- **Stage Event** — registro histórico (append-only) de uma transição de Stage de um Deal —
  nunca sobrescrito pelo `current_stage` cacheado no Deal.
- **Strategy** — abordagem usada pelo closer para lidar com uma objeção ou avançar o deal.
