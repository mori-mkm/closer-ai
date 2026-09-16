# Architecture v0

Arquitetura conceitual, não definitiva. Evitamos decisão prematura — decisões reais de
banco, storage e provedor de LLM entram por ADR quando houver caso de uso concreto.

## Fluxo de dados (alto nível)

```
transcrição bruta (fora do repo)
  → normalization/   (schema canônico de call)
  → ai/               (extração estruturada: eventos, objeções, sinais)
  → integrations/     (CRM: leitura de deals)
  → domain/           (matching call ↔ deal, modelo de Deal/Outcome)
  → analytics/        (outcome intelligence, agregados)
  → experiments/       (experimentation engine — fase futura)
```

`storage/` e `api/` existem como pastas para quando houver decisão de persistência e
exposição real — hoje estão vazias por design.

## Módulos (`src/closer_ai/`)

| Módulo | Responsabilidade |
|---|---|
| `domain/` | Entidades centrais (Deal, Call, Outcome) e regras de negócio — ver `DATA_MODEL.md` |
| `ingestion/` | Entrada de transcrições/dados brutos (fonte a definir) |
| `normalization/` | Transcrição bruta → schema canônico |
| `ai/` | Extração estruturada via LLM (objeções, momentos, sinais) |
| `analytics/` | Agregação e outcome intelligence |
| `experiments/` | Experimentation engine (fase futura) |
| `integrations/` | Conectores externos (CRM, etc.) |
| `storage/` | Persistência (sem decisão de banco ainda) |
| `api/` | Exposição externa (sem API pública ainda) |

## Integrações previstas

Ver [`INTEGRATIONS.md`](INTEGRATIONS.md) — hoje é só inventário, sem implementação.

## Princípio

Contrato entre módulos > implementação interna. Um módulo não deve depender do interno de
outro. Mudança de contrato entre módulos é decisão arquitetural — passa por ADR.
