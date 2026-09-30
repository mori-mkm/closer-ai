# Roadmap

Sequência de fases do produto, reconciliada com o estado real do repositório em 2026-09-29.
Não é cronograma com datas — é ordem de dependência. Estado operacional completo:
[`docs/context/CURRENT_STATE.md`](../context/CURRENT_STATE.md).

## DONE (código + testes, só dado sintético)

- Bootstrap: política de branches/PR, `.gitignore` defensivo, funil de contexto para agents, agent
  harness, CI (GitHub Actions).
- Canonical Call schema; Agro normalization vertical slice (contra hipótese de formato).
- Objection Intelligence v0: `ObjectionEvent`, extractor rule-based, eval harness sintético.
- Deal-level model: `Lead`, `Deal`, `StageEvent`, `CallDealMatch`, `ExactExternalIdMatcher`.
- Current Match Resolver (`MatchDecision`, DEP-1) — [ADR-003](../decisions/ADR_003-authoritative-call-deal-matching.md).
- Outcome Domain v0, núcleo estrutural (policy real pendente) — [ADR-001](../decisions/ADR_001-outcome-contract-v0.md).
- Deal Identity + fundação explícita de Deals (DEP-2) — [ADR-002](../decisions/ADR_002-canonical-deal-identity.md).
- Privacy boundary + OCI storage foundation (smoke test sintético) — [ADR-004](../decisions/ADR_004-real-data-privacy-boundary.md).
- Docs pré-pilot: Golden Set protocol v1, ObjectionEpisode v1 proposal, taxonomy v0.1, annotation
  guideline v0.1 (CIT-O1), Synthetic Calibration Kit v0.1, Sales Knowledge Base v0.1.
- Stack experimental de classificação:
  - **E0** (só transcript), **E1** (+ guia curto de taxonomia), **E2** (+ full-context knowledge
    augmentation via Knowledge Context Builder) — braços de experimento implementados;
  - `ClassificationProvider` + Ollama local-only — [ADR-005](../decisions/ADR_005-classification-provider-boundary.md);
  - Experiment Runner (compliance operacional + proveniência, artifacts privacy-first).

E2 é **full-context knowledge augmentation**, não RAG semântico: não há retrieval, embeddings nem
vector DB. Os braços são experimento de avaliação, não runtime de produto.

## NOW — sem dado real

- **Calibration Dataset Loader v0.1:** as 12 calls do kit v0.1 como `Call`s verificadas por hash.
- Análise de compliance do classifier (predições inválidas/malformed) em dado sintético, sem
  métricas de qualidade.
- Dry run do Calibration Kit v0.1 (anotadores humanos).

## NOW — bloqueado por decisão/acesso humano

- Autorização e acesso aos corpora reais (Agro 108 calls, Empreende 35) e ao Kommo.
- Validar `AgroRawCall`/`AGRO_INGESTION_CONTRACT.md` contra amostra real pequena.
- Decisões de negócio do Outcome (D-G1/D-G2/D-G5/D-G6) e da identidade de Deal (DI-G1–G4).
- Sign-off da política de storage para dado real (OCI).

## NEXT (depende de dado real)

- Pilot D3 (3–5 calls reais, dupla anotação) → Golden Set v1.
- Avaliação de qualidade E0/E1/E2 contra gold real (métricas da proposta de RAG); decisão sobre
  E3.
- Policy real do Outcome; ingestão CRM real (identidade card → Deal, fundação explícita).
- Call ↔ Deal real: decisões `MatchDecision` sobre candidatos reais.
- Outcome Intelligence — join Deal ↔ calls (match atual) ↔ eventos ↔ outcome canônico.
- Decidir migração de contrato (`ObjectionEpisode`, D7) com base no pilot.

## DEFERRED

- **E3** (seleção determinística de cards) — só se E2 for caro/limitado de forma medida.
- **E4** (semântico/híbrido), embeddings, vector DB — só se E3 perder recall ou o corpus crescer.
- Provider de LLM cloud — exige autorização/privacidade (ADR-004/005).
- Storage/banco de produto, API/FastAPI, dashboard, cloud de aplicação.

## LATER

- Experimentation Engine de playbook; Playbook Learning.
- Cortex / Realtime Copilot — depois de Outcome Intelligence validado com dado real.
- Multi-tenant hardening; productionization (storage definitivo, API, observability); ROI proof.

## Dependências explícitas

```
Dados reais autorizados (Agro + Kommo) — bloqueador transversal
  ├── Agro real → validação do parser → pilot D3 → gold → avaliação E0/E1/E2 → extractor de produto
  └── Kommo real → identidade card → Deal → Call ↔ Deal (MatchDecision) → Outcome canônico
                                                                        └──► Outcome Intelligence
```

Mapa de inputs/outputs/blockers por nó: `docs/context/DATA_DEPENDENCIES.md`.
Definition of done por camada: `docs/context/EXECUTION_GATES.md`.
