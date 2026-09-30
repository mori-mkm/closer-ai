# ADR-003 — Authoritative Call ↔ Deal Matching (DEP-1)

## Status

Accepted

Registra uma decisão **já implementada e mergeada** (PR #16), que [ADR-001](ADR_001-outcome-contract-v0.md)
já trata como "DEP-1 — RESOLVED". O contrato nasceu em formato ADR dentro de
[`CURRENT_MATCH_RESOLVER.md`](../domain/CURRENT_MATCH_RESOLVER.md) e foi promovido aqui na
reconciliação de documentação. Aceito formalmente na reconciliação de 2026-09-29.

Contrato detalhado (**como**): tabelas de campos, estados, invariantes testados e migração ficam em
`CURRENT_MATCH_RESOLVER.md`. Este ADR registra **por que** e as **consequências**.

## Context

- `CallDealMatch` é um log de **candidatos/tentativas**: uma linha por (call, deal candidato,
  método, tentativa). Um batch ambíguo produz várias linhas.
- A regra antiga ("latest row by `created_at` with `status='matched'`") estava errada. Filtrar por
  status antes de resolver o que é atual ressuscita um match que uma decisão posterior rejeitou,
  tornou ambíguo ou substituiu. `created_at` não ordena de forma confiável (empates, relógios).
- Outcome (ADR-001) e ObjectionEpisode dependem de uma regra única: *o linkage Call → Deal só existe
  quando o resultado autoritativo atual é `matched`*.

## Decision

1. **Candidato ≠ resultado.** Uma linha `CallDealMatch` (inclusive `status="matched"`) nunca
   estabelece sozinha a relação atual Call → Deal.
2. **`MatchDecision`**, uma entidade aditiva: o resultado autoritativo do matching de uma call,
   numa **cadeia linear append-only por call**. A relação atual vem só de
   `resolve_current_match(call_id, decisions)`: primeiro o head da cadeia, depois o status.
3. **Só `state == "matched"` fornece `deal_id`.** `ambiguous`, `rejected`, `unmatched`,
   `manual_review`, `no_decision` e `conflict` não fornecem Deal. Ambiguidade nunca escolhe um Deal
   silenciosamente.
4. **Autoridade humana persiste:** uma decisão `automatic` não substitui um head `manual`; só outra
   decisão `manual` o substitui.
5. **Concorrência por CAS:** cada escrita declara o head esperado (`supersedes_decision_id`); head
   divergente → `MatchDecisionConflict`. Nenhum vencedor por timestamp. Um fork persistido resolve
   para `conflict`, com reparo manual.
6. **Correção e desligamento são decisões novas** que supersedem o head. Exemplos: MATCHED A →
   MATCHED B, ou MATCHED → `rejected`/`unmatched`. Nada é apagado.
7. **Legado sem decisão resolve para `no_decision`.** Nada é inferido de linhas antigas.

## Alternatives considered

| Alternativa | Por que foi rejeitada |
|---|---|
| Latest `created_at` / `status='matched'` | empates, relógios; ressuscita histórico |
| Batch/run id + latest run | volta a depender de tempo; não expressa correção manual nem CAS |
| Cadeia de supersessão nas linhas `CallDealMatch` | uma decisão ambígua tem várias linhas (vira fork); breaking no schema/ids |
| Ponteiro mutável "current" | mutação perde auditoria |

## Consequences

### Positive

- Uma única regra de relação atual, usada por Outcome (`commercial_state.resolve_call_commercial_state`),
  pela documentação de ObjectionEpisode e pela análise futura.
- Auditável, determinística, aditiva: `CallDealMatch`, seus ids e o matcher não mudaram.

### Negative

- Toda consulta "qual o Deal desta call" precisa passar pelo resolver.
- A atomicidade real do CAS depende de storage (TD-09). Sem ela, um fork é possível e vira
  `conflict` (nunca um vencedor).
- O matcher ainda não grava decisões num pipeline, e reconciliar forks está deferred.

## Implementation status (2026-09-29)

- **IMPLEMENTED:** `src/closer_ai/domain/matching.py` (`MatchDecision`, `resolve_current_match`,
  `append_match_decision`, `decision_from_matcher_output`, `CurrentMatchResult`);
  `src/closer_ai/domain/commercial_state.py`; testes em `tests/unit/domain/test_match_resolver.py`
  e `test_commercial_state.py`.
- **NOT IMPLEMENTED:** storage/atomicidade, pipeline de decisões automáticas, workflow de revisão
  manual, `reviewed_by`.
- **NOT VALIDATED:** nenhum matching rodou contra Calls e Deals reais.
