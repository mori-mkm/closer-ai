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
