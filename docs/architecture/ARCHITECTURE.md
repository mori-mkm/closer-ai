# Architecture v0

Arquitetura conceitual, não definitiva. Evitamos decisão prematura — decisões reais de
banco, storage e provedor de LLM entram por ADR quando houver caso de uso concreto.

## Fluxo de dados (alto nível)

```
transcrição bruta (fora do repo)
  → ingestion/ + normalization/   (fonte → schema canônico de Call)
  → ai/                           (evidência estruturada: ObjectionEvent v0; classifier experimental E0/E1/E2)
  → domain/                       (Deal Identity, candidatos + MatchDecision, Outcome canônico)
  → Outcome Intelligence          (futuro — sem módulo ainda)
  → experimentos de playbook      (futuro)
```

Decisões duráveis estão nas ADRs ([`docs/decisions/`](../decisions/README.md)).

## Módulos (`src/closer_ai/`)

| Módulo | Responsabilidade | Estado |
|---|---|---|
| `normalization/` | Canonical Call (`Call`, `Participant`, `TranscriptSegment`), ids determinísticos | implementado |
| `ingestion/` | Fronteira de fonte (Agro/Zoom, hipótese de formato) + profiler | implementado, só dado sintético |
| `domain/` | Lead, Deal, StageEvent, Deal Identity (ADR-002), CallDealMatch + MatchDecision (ADR-003), Outcome (ADR-001), ObjectionEvent, composição Call → Deal → Outcome | implementado (contratos) |
| `ai/` | Extractor rule-based; Knowledge Context Builder; classifier E0/E1/E2 + `ClassificationProvider` (ADR-005); Ollama provider local; Experiment Runner | implementado; classifier é eval layer experimental |

Pacotes para analytics, experiments, integrations, storage e API **não existem**: os diretórios
vazios foram removidos em 2026-09-29 (YAGNI). Serão criados quando houver código e decisão
(storage/API entram por ADR).

## Fronteira experimental de AI

```
Sales Knowledge Base → Knowledge Context Builder ─┐
Canonical Call → prompt E0 / E1 / E2 ◄────────────┘ → ClassificationProvider → Ollama (loopback)
  → ClassificationRun → Experiment Runner (compliance + proveniência, artifacts privacy-first)
```

E2 = full-context knowledge augmentation; E3 (seleção) e E4 (semântico), embeddings e vector DB são
deferred. Predições do classifier não são entidades de domínio nem gold.

## Integrações previstas

Ver [`INTEGRATIONS.md`](INTEGRATIONS.md) — hoje é só inventário, sem implementação.

## Princípio

Contrato entre módulos > implementação interna. Um módulo não deve depender do interno de
outro. Mudança de contrato entre módulos é decisão arquitetural — passa por ADR.
