# Data Model v0 (conceitual)

Não é schema de banco. É o modelo conceitual que orienta nomenclatura e limites de módulo.
Schema real de persistência é decisão futura (ADR).

## Unidade analítica: o Deal

O produto raciocina sobre **Deal**, não sobre call isolada. Uma call é evidência dentro de
um deal; outcome é medido no nível do deal.

```
Deal
├── Lead
├── Closer
├── Stage
├── Calls[]
│   ├── Moments
│   ├── Objections
│   ├── Strategies
│   ├── Buying Signals
│   ├── Risks
│   ├── Questions
│   └── Commitments
└── Outcome
```

## Relação de interesse (hipótese central do produto)

```
lead profile + stage + objection + strategy + moment + closer → outcome
```

Ou seja: o que explica o outcome não é só "quem vendeu" — é a combinação de perfil do lead,
etapa, objeção levantada, estratégia usada e momento da call.

## Notas

- `Calls[]` é uma lista porque um deal pode ter múltiplas calls ao longo do funil.
- Cada sub-item de uma call (Moment, Objection, etc.) é evidência estruturada extraída pela
  camada `ai/`, não texto bruto. Hoje só `ObjectionEvent` v0 existe como contrato de domínio;
  as predições do classifier experimental (E0/E1/E2) são eval layer, não persistidas no domínio — texto bruto de transcrição nunca é persistido fora do
  ambiente controlado do cliente (ver [`data/README.md`](../../data/README.md)).
- Este documento evolui conforme o Golden Set e a taxonomia forem definidos. Mudança de
  modelo aqui é decisão relevante — considerar ADR quando afetar contrato entre módulos.

## Deal-level: Call outcome != Deal outcome

`Call` (`closer_ai.normalization.Call`) nunca tem outcome comercial, `value` ou `closed_at`.
O resultado da venda existe **uma única vez**, no `Deal`, nunca duplicado por call:

```
Deal
│
├── Call A
│   ├── Objection 1
│   └── Objection 2
│
├── Call B
│   └── Objection 3
│
├── Stage Events (histórico append-only, nunca sobrescrito)
│
└── Outcome (só aqui — nunca na Call)
```

**Outcome canônico ≠ `Deal.outcome`.** `Deal.outcome` (`open`/`won`/`lost`/`unknown`) e
`closed_at` são a **projeção legada do estado do CRM**, mantida por compatibilidade. O outcome
comercial canônico (`won`/`rejected`/`open`/`unknown`) vem da cadeia append-only do Outcome Domain
([ADR-001](../decisions/ADR_001-outcome-contract-v0.md), `src/closer_ai/domain/outcome.py`):

```
OutcomeEvidence (observação de uma fonte, estado bruto preservado)
  ↓ EvidenceDisposition (invalida/corrige evidência sem apagar)
  ↓ evidência elegível
OutcomeAssessment (cadeia linear por Deal, CAS, autoridade humana)
  ↓ resolve_current_outcome
Outcome canônico atual (available / review_pending / no_assessment / conflict)
```

A policy que transforma sinais reais em status ainda não existe (D-G1/D-G2/D-G5/D-G6); o núcleo
estrutural sim.

No schema real (não conceitual), `Deal` **não embute** `Call`/`Objection` — a árvore acima é a
visão conceitual; a ligação real é por id via `CallDealMatch`, nunca nesting:

```
Call
  ↓
candidate Deals (o registro do CRM resolve para um Deal via Deal Identity — ADR-002)
  ↓
CallDealMatch (candidatos/tentativas; uma linha por candidato — nunca um vencedor silencioso)
  ↓
MatchDecision (cadeia linear por call, CAS, autoridade manual)
  ↓
resolve_current_match → matched / ambiguous / rejected / unmatched / manual_review / no_decision / conflict
  ↓
Deal canônico — só quando o estado ATUAL é `matched`
```

Uma linha `CallDealMatch(status="matched")` sozinha **não** estabelece a relação atual
([ADR-003](../decisions/ADR_003-authoritative-call-deal-matching.md)). A composição Call → match atual
→ Deal → outcome atual é `closer_ai.domain.commercial_state.resolve_call_commercial_state`.

Um **registro do CRM (card) não é um Deal**: a ligação card → Deal canônico é uma
`DealIdentityDecision` ([ADR-002](../decisions/ADR_002-canonical-deal-identity.md),
`src/closer_ai/domain/deal_identity.py`).

Contrato completo (`Lead`, `Deal`, `StageEvent`, `CallDealMatch`, `MatchEvidence`, cardinalidades,
invariantes, IDs determinísticos): [`docs/domain/DEAL_MODEL.md`](../domain/DEAL_MODEL.md).
Implementação: `src/closer_ai/domain/{lead,deal,deal_identity,matching,outcome,commercial_state}.py`.
