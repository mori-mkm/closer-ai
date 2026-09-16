# Product Spec — AI Closer

## O que é

Sistema de Sales Intelligence para operações de vendas high-ticket. Extrai inteligência
estruturada de calls de venda, liga isso a oportunidades de CRM (deals), e mede outcome —
para entender o que realmente move conversão, não achismo.

## Corpus inicial

- 108 calls Beefpoint/AgroTalento
- 35 calls Empreende Brazil
- Total: 143 transcrições reais

Nenhum dado real entra neste repositório — ver [`data/README.md`](../../data/README.md).

## Fluxo do produto (visão completa)

```
Segurança
↓
Normalização das calls
↓
Golden Set + Taxonomia
↓
Call Intelligence
↓
CRM + Matching Call ↔ Deal
↓
Outcome Intelligence
↓
Manager Intelligence
↓
Validação com clientes
↓
Cortex / Realtime Copilot
↓
Experimentation Engine
↓
Playbook Learning
↓
ROI Proof
```

Escopo do primeiro milestone: [`MVP_SCOPE.md`](MVP_SCOPE.md).
Sequência completa: [`ROADMAP.md`](ROADMAP.md).

## Unidade analítica

O produto analisa **Deals**, não calls isoladas. Uma call é evidência dentro de um deal.
Modelo conceitual: [`docs/architecture/DATA_MODEL.md`](../architecture/DATA_MODEL.md).
