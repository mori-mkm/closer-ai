# Current Match Resolver (DEP-1)

Implementação: `src/closer_ai/domain/matching.py` (seção "Current authoritative match").
Testes: `tests/unit/domain/test_match_resolver.py`. Formato ADR (contrato entre módulos).

## Context

`CallDealMatch` é um log de **candidatos/tentativas**: uma linha por (call, deal candidato,
método, momento). Ambiguidade = várias linhas no mesmo batch. Não existe hoje nenhuma noção de
revisão, batch/run, supersessão ou resultado autoritativo; o matcher
(`ExactExternalIdMatcher`) só produz objetos, não persiste.

O docstring antigo definia o match atual como "latest row by created_at with
status='matched'". Isso é errado: filtrar por status antes de resolver currentness ressuscita
matches históricos (MATCHED A às 10h, REJECTED às 11h → devolveria A). `created_at` também não
ordena de forma autoritativa (empates, relógios).

O Outcome Contract (`OUTCOME_CONTRACT_V0_PROPOSAL.md` §14) e o ObjectionEpisode
(`OBJECTION_EPISODE_V1_PROPOSAL.md` §11/§19, DEP-1) dependem de: *linkage canônico Call → Deal
só existe quando o resultado autoritativo atual do matching é MATCHED.*

## Decision

Uma entidade nova, **aditiva**, `MatchDecision`: o resultado autoritativo do matching de uma
call num momento, numa **cadeia linear append-only** por call.

| Campo | Significado |
|---|---|
| `match_decision_id` | `mdc_` + sha256 de **todos** os campos de conteúdo (abaixo) |
| `call_id` | a call |
| `status` | `MatchStatus` existente: `matched`/`ambiguous`/`rejected`/`unmatched`/`manual_review` |
| `deal_id` | obrigatório ⟺ `matched`; proibido nos outros |
| `match_ids` | linhas `CallDealMatch` em que a decisão se baseia; obrigatório para `automatic` |
| `decided_by` | `automatic` \| `manual` |
| `supersedes_decision_id` | **head esperado** no momento da escrita (`None` só na primeira) |
| `created_at` | só para unicidade do id; **nunca** ordena |

`CallDealMatch`, seus ids e o matcher **não mudam**.

API pública (`closer_ai.domain`):

| Função | Papel |
|---|---|
| `resolve_current_match(call_id, decisions) -> CurrentMatchResult` | currentness primeiro (head da cadeia), status depois |
| `append_match_decision(history, decision) -> history` | append com CAS, idempotência e autoridade manual |
| `decision_from_matcher_output(rows, *, supersedes_decision_id, created_at)` | decisão `automatic` a partir de um batch do matcher |
| `CurrentMatchResult` | `state` + `deal_id` (só em `matched`) + `decision_id` do head |

`CurrentMatchResult.state`:

| state | Significado | Deal canônico? |
|---|---|---|
| `matched` | head é MATCHED | **sim**, `deal_id` |
| `ambiguous` / `rejected` / `unmatched` / `manual_review` | head com esse status | não |
| `no_decision` | nenhuma decisão para a call (nunca avaliada, ou só linhas legadas) | não |
| `conflict` | histórico não é uma cadeia linear (fork, supersessão pendente, várias raízes) | não |

`unmatched` ≠ `no_decision`: o primeiro é uma decisão ("procuramos, nenhum deal"); o segundo
é ausência de decisão.

## Semântica

- **Candidato ≠ resultado:** uma linha `CallDealMatch` nunca vira deal canônico sozinha. Só
  uma `MatchDecision` `matched` (de um batch com exatamente uma linha `matched`, ou manual)
  produz deal canônico. Batch ambíguo continua ambíguo.
- **Autoridade manual:** uma decisão `automatic` não pode substituir um head `manual`
  (`MatchDecisionConflict`). Só outra decisão `manual` substitui. Humano confirmando o mesmo
  resultado de um head automático **grava** uma decisão manual (a autoridade sobe).
- **Idempotência:** mesmo id + payload idêntico → histórico inalterado. Nova decisão com o
  mesmo (status, deal_id) do head e sem subir autoridade → no-op (rerun do matcher não cria
  decisão lógica nova).
- **Correção:** MATCHED A → MATCHED B é uma decisão nova superseding a anterior.

## Concurrency (CAS)

`append_match_decision` aceita a escrita só se `supersedes_decision_id == head atual`. Senão →
`MatchDecisionConflict("stale write ...")`: o caller recarrega, recomputa e tenta de novo.
Duas escritas partindo do mesmo head: a primeira entra; a segunda falha. Nenhuma escolha por
timestamp.

A função é a **regra**; a atomicidade (ler head + gravar) é responsabilidade do storage futuro
(TD-09). Sem ela, um fork pode surgir — e é detectado abaixo.

## Fork / corrupção

Se o histórico tiver dois heads, supersessão para id ausente, mais de uma raiz, nós
desconectados ou uma decisão `automatic` superseding uma `manual` (só possível se algo além de
`append_match_decision` gravou o histórico): `resolve_current_match` → `conflict`; `append_match_decision` recusa
qualquer escrita. Nenhum vencedor automático. Reparo é manual (fora deste contrato;
reconciliação multi-parent: deferred).

## Invariants (testados)

1. No máximo um head autoritativo válido por call; senão `conflict`.
2. Linha/decisão `matched` histórica nunca produz deal se o head não é `matched`.
3. `created_at` nunca decide autoridade (nem ordem da lista de entrada).
4. Fork → `conflict`.
5. Redelivery idêntica é idempotente.
6. Mesmo id + payload diferente → `ValueError` (hard error).
7. Supersessão só dentro da mesma call (decisão de outra call → `ValueError`; ponteiro para fora
   → CAS falha / `conflict`).
8. `matched` exige exatamente um `deal_id`; os outros status proíbem `deal_id`.
9. `ambiguous`/`rejected`/`unmatched`/`manual_review`/`no_decision`/`conflict` não fornecem deal.

## Alternatives

| Alternativa | Veredito |
|---|---|
| A. latest `created_at` | rejeitada: empates, relógios, ressuscita histórico |
| B. batch/run id + latest run | rejeitada: "latest run" volta a depender de tempo; não expressa correção manual nem CAS |
| C. cadeia de supersessão nas próprias linhas `CallDealMatch` | rejeitada: uma decisão ambígua tem várias linhas (vira fork); mudaria o id e o schema de `CallDealMatch` (breaking) |
| D. ponteiro mutável "current" | rejeitada: mutação perde auditoria; CAS equivalente sem histórico |
| **E. `MatchDecision` separado, cadeia linear + CAS** | **escolhida**: aditiva, auditável, determinística, 1 entidade pequena |

## Consequences / Outcome integration

Depois desta mudança vale:

```
Call → resolve_current_match → state == "matched" → deal_id → Outcome
Call → resolve_current_match → qualquer outro state → SEM linkage de Outcome por esta Call
```

Outcome e ObjectionEpisode **não** foram alterados; o DEP-1 citado neles passa a ter resolver.

Candidatos: `ExactExternalIdMatcher(provider)` resolve o registro do CRM da Call via Deal Identity
(só `linked` gera candidato); o candidato só vira canônico por `MatchDecision`.

Composição executável: `closer_ai.domain.commercial_state.resolve_call_commercial_state`
(Call → match atual → Deal → outcome atual; sem fallback para `Deal.outcome`).

## Migration

- **Aditivo:** `MatchDecision`, `CurrentMatchResult`, `MatchDecisionConflict`, funções novas.
  Nenhum campo, id ou validator existente mudou.
- **Docs corrigidos** (não código): docstrings de `matching.py`/`deal.py`, `DEAL_MODEL.md`,
  TD-09, que descreviam a consulta por `status='matched'`.
- **Legado:** linhas `CallDealMatch` sem `MatchDecision` resolvem para `no_decision`. Nada é
  inferido delas. Para dar currentness a um histórico legado, alguém (humano ou um backfill
  explícito e revisado) grava decisões; nunca o resolver.

## Deferred

Storage/atomicidade real do CAS (TD-09); reparo/reconciliação de forks; identidade de quem
decidiu manualmente (`reviewed_by`); matcher gravando decisões automaticamente num pipeline;
consulta "calls de um deal" (derivável: calls cujo resultado atual é `matched` com esse deal).
