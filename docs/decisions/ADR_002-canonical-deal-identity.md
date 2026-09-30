# ADR-002 — Canonical Deal Identity (CRM source record ≠ Deal)

## Status

Proposed

Registra uma decisão **já implementada** como contrato estrutural (PR #21, #22, #23) e já decidida
por Matheus nos pontos DI-M1 e DI-M2. Fica **Proposed** porque a própria proposta define
**DI-M3: "ADR após validação de Gabriel"**. As perguntas DI-G1–DI-G4 continuam abertas. Para passar
a Accepted, Matheus aceita este texto depois dessa validação.

Contrato detalhado (**como**): [`DEAL_IDENTITY_RESOLUTION_PROPOSAL.md`](../domain/DEAL_IDENTITY_RESOLUTION_PROPOSAL.md).
Este ADR registra **por que** e as **consequências**.

## Context

- Um card do CRM não é necessariamente uma negociação. Existem cards de reabertura, cards paralelos,
  duplicatas, cards criados por automação, cards errados e cards com informação insuficiente.
- Antes desta decisão, `Deal` era o snapshot de um card: `deal_id = hash(company_id, source,
  external_id)`. Qualquer ingestão futura criaria um Deal por card, e juntar dois cards da mesma
  negociação exigiria fundir Deals, movendo Outcome e matches (um problema de MDM).
- Outcome (ADR-001) e Call matching precisam apontar para a **negociação**, não para um card
  arbitrário. Cards paralelos com status diferentes não podem virar dois Outcomes.

## Decision

1. **Um source record nunca é um Deal.** A ligação record → Deal canônico é uma **decisão de
   identidade** (`DealIdentityDecision`), nunca uma derivação automática. A chave do record é
   `(company_id, provider, external_record_id)`, em namespace próprio (`srk_`), sem PII.
2. **Cadeia linear append-only por source record**, com as mesmas regras do matching
   ([ADR-003](ADR_003-authoritative-call-deal-matching.md)): o head é o estado atual; `created_at`
   nunca ordena; um fork resolve para `conflict`; escrita com CAS; decisão `automatic` nunca
   substitui `manual`.
3. **Estados:** `linked` (exatamente um Deal), `ambiguous` (≥ 2 candidatos), `unresolved`,
   `not_a_deal` (só manual), mais `no_decision`/`conflict` na resolução.
4. **O único `linked` automático é o self-link de fundação.** Ele é identidade estrutural do próprio
   registro. Ligar um card a qualquer outro Deal exige decisão manual. Nome, closer, pipeline,
   datas ou similaridade nunca ligam. "Card mais recente vence" e "card aberto vence" são proibidos.
5. **Fundação explícita (DI-M1 = 7a):** um Deal só nasce quando um caller decide que um registro é
   uma negociação nova (`found_deal`); a ingestão nunca funda um Deal por card. `deal_id` continua
   derivado do card fundador, portanto a mudança é aditiva. Um fundador fica ligado ao seu Deal para
   sempre em v0; repair/merge ficam deferred.
6. **Sem entidade `SourceRecord` em v0 (DI-M2 = D):** o estado do card entra como evidência
   (`OutcomeEvidence`/`StageEvent`).
7. **Provider-agnostic:** a chave inclui o provider; não há campos específicos de Kommo/Pipedrive.
8. **Ambiguidade é estado legítimo e persistente**; nada é consolidado para "resolver" incerteza.

## Alternatives considered

Da proposta, §4 e §11:

| Alternativa | Por que foi rejeitada |
|---|---|
| 1 card = 1 Deal | duplica Outcome por card; não representa reabertura/card paralelo |
| `Deal.source_record_ids: list` | segunda fonte de verdade mutável num snapshot frozen; sem incerteza nem autoridade |
| Entidade `SourceRecord` + MDM completo em v0 | nenhum atributo do card exige isso hoje |
| Deal com identidade própria (7b) | breaking para `derive_deal_id`, `Deal`, matcher e testes, sem ganho em v0 |
| Dedup automático, fuzzy ou por LLM; identidade por nome | consolidaria negociações distintas silenciosamente |

## Consequences

### Positive

- Um Outcome por negociação, independentemente de quantos cards estejam `linked`.
- Incerteza explícita e auditável; autoridade humana persiste.
- O Call matching gera candidatos via identidade: `ExactExternalIdMatcher(provider)` só gera
  candidato para um card `linked`, sem fallback para `Deal.external_id`.

### Negative

- Fundação errada ou duplicada só se corrige com repair/merge, que está deferred.
- `Deal` ainda exige campos do card fundador (`current_stage`, `outcome` legado, `created_at`).
- A atribuição de `OutcomeEvidence` exigindo card `linked` depende de um write path futuro.
- A atomicidade real do CAS depende de storage (TD-09).

## Implementation status (2026-09-29)

- **IMPLEMENTED:** `src/closer_ai/domain/deal_identity.py` (`DealIdentityDecision`,
  `resolve_deal_for_source_record`, `append_deal_identity_decision`, `found_deal`); integração com o
  matcher (`src/closer_ai/domain/matching.py`); testes em `tests/unit/domain/test_deal_identity.py`,
  `test_deal_foundation.py` e `test_matcher.py`.
- **NOT IMPLEMENTED:** adapter real de CRM, sinais automáticos de identidade, fusão de Deals,
  storage.
- **NOT VALIDATED:** nenhum dado real de CRM foi processado.
- **OPEN:** DI-G1–DI-G4 (Gabriel).
