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
  camada `ai/`, não texto bruto — texto bruto de transcrição nunca é persistido fora do
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
└── Outcome (OPEN / WON / LOST / UNKNOWN — só aqui)
```

No schema real (não conceitual), `Deal` **não embute** `Call`/`Objection` — a árvore acima é a
visão conceitual; a ligação real é por id via `CallDealMatch`, nunca nesting:

```
Call
  ↓
candidate Deals
  ↓
CallDealMatch (uma linha por candidato avaliado — nunca um vencedor escolhido silenciosamente)
  ↓
MATCHED / AMBIGUOUS / REJECTED / UNMATCHED / MANUAL_REVIEW
  ↓
Deal (via CallDealMatch.deal_id, quando o status permite)
```

Contrato completo (`Lead`, `Deal`, `StageEvent`, `CallDealMatch`, `MatchEvidence`, cardinalidades,
invariantes, IDs determinísticos): [`docs/domain/DEAL_MODEL.md`](../domain/DEAL_MODEL.md).
Implementação: `src/closer_ai/domain/{lead,deal,matching}.py`.
