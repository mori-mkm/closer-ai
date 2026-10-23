# Current State

_Atualizar somente quando o estado real do sistema mudar. Não é diário, não registra commits.
Reconciliar o documento inteiro; não empilhar correções no fim._

## Snapshot

- Data do snapshot: 2026-10-22 (Live Copilot: Dock UX + P0 Reliability + session recovery)
- Code baseline reviewed: `aeb9352` (merge do Live Copilot v1) + branch `feat/live-copilot-dock-ux`
- Tests: **744 passed** (`pytest -q`) após Objection Guidance Engine v0/v0.1 + Live Meet Copilot
  v0/v1 + dock/reliability (+152 sobre 592: guidance, grounding, post-call, CLI/pilot runner, long-call
  chunking, live session, delivery/recovery). Extensão: `node --test` em
  `extensions/google-meet/meet_adapter.test.js` (12) e `sidebar_view.test.js` (15). Todos herméticos: nenhum teste exige Ollama, rede ou dado real
- Lint: `ruff check .` limpo
- CI: `.github/workflows/ci.yml` (import sanity check, `ruff check .`, `pytest -q`) em toda PR e
  push para `main`
- Branch protection no GitHub: **não verificável localmente** (TD-12)

Testes passando não significam produção. Nenhum componente abaixo foi validado com dado real de
cliente. Exceção parcial: o Live Meet Copilot v0 rodou ponta a ponta em um Google Meet real de teste
(contas próprias, sem cliente).

## Product thesis

```
Calls / transcripts → Canonical Call → evidência estruturada (objeções, …)
  → Call ↔ Deal (relação atual autoritativa) → Deal canônico → Outcome canônico
  → Outcome Intelligence → recomendações/experimentos → playbook aprendido
```

Call outcome ≠ Deal outcome: `Call` não tem outcome. `Deal.outcome` é a **projeção legada do CRM**.
O outcome canônico é o `OutcomeAssessment` atual (ADR-001).

## Arquitetura implementada (código)

```
CRM source record ──(DealIdentityDecision)──► Deal canônico            [ADR-002]
Canonical Call ─► CallDealMatch (candidatos) ─► MatchDecision
               ─► resolve_current_match ─► Deal canônico               [ADR-003]
Deal ─► OutcomeEvidence ─► EvidenceDisposition ─► OutcomeAssessment
     ─► resolve_current_outcome                                        [ADR-001]
Call ─► resolve_call_commercial_state (match atual → Deal → outcome atual; sem fallback a Deal.outcome)

Experimental AI (eval layer, não domínio):
Sales Knowledge Base ─► Knowledge Context Builder ─┐
Canonical Call ─► prompt E0 / E1 / E2 ◄───────────┘ ─► ClassificationProvider [ADR-005]
               ─► OllamaClassificationProvider (local) ─► ClassificationRun
               ─► Experiment Runner ─► compliance operacional + proveniência (artifact JSON privado)
```

## IMPLEMENTED

| Component | Evidence | Limits |
|---|---|---|
| Canonical Call (`Call`, `Participant`, `TranscriptSegment`, ids determinísticos) | `src/closer_ai/normalization/` | `normalize_call()` é entry point para dado sintético |
| Agro ingestion boundary (`AgroRawCall` → `Call`) + profiler | `src/closer_ai/ingestion/` | formato da fonte é **hipótese**; nunca processou call real; `unresolved_lead` sinaliza lead não resolvido (TD-14 mitigado) |
| `ObjectionEvent` v0 + `RuleBasedObjectionExtractor` + eval sintético | `src/closer_ai/domain/objection.py`, `src/closer_ai/ai/objection_extraction.py`, `evals/objection_v0/` | enum v0 (`price`, `timing_priority`, `trust_authority`, `no_need`, `other`); golden set de 9 exemplos sintéticos |
| Lead, Deal, StageEvent | `src/closer_ai/domain/{lead,deal}.py` | `Deal.outcome`/`closed_at` = projeção legada do CRM |
| Deal Identity + Deal Foundation (DEP-2) | `src/closer_ai/domain/deal_identity.py`; [ADR-002](../decisions/ADR_002-canonical-deal-identity.md) | contrato estrutural; DI-G1–G4 abertos; sem adapter CRM; fusão deferred |
| Call ↔ Deal matching: `CallDealMatch` (candidatos), `ExactExternalIdMatcher` via Deal Identity | `src/closer_ai/domain/matching.py` | um sinal determinístico; nunca rodou contra CRM real |
| Current Match Resolver (`MatchDecision`, `resolve_current_match`, CAS) (DEP-1) | `matching.py`; [`CURRENT_MATCH_RESOLVER.md`](../domain/CURRENT_MATCH_RESOLVER.md); [ADR-003](../decisions/ADR_003-authoritative-call-deal-matching.md) | atomicidade real depende de storage (TD-09) |
| Outcome Domain v0, núcleo estrutural | `src/closer_ai/domain/outcome.py`; [ADR-001](../decisions/ADR_001-outcome-contract-v0.md) | **policy comercial real não implementada** (D-G1/D-G2/D-G5/D-G6) |
| Call → match atual → Deal → outcome atual | `src/closer_ai/domain/commercial_state.py` | composição; nenhuma decisão nova |
| Sales Knowledge Base v0.1 (8 units + `SOURCES.md`) | `docs/knowledge/sales/` | provisória; conhecimento define, nunca prova ocorrência |
| Knowledge Context Builder v0.1 | `src/closer_ai/ai/knowledge_context.py`; [doc](../ai/KNOWLEDGE_CONTEXT_BUILDER_V0_1.md) | full-context (8 cards), sem retrieval; RAG-O4 aberta |
| Objection Classifier core + braços E0/E1/E2 | `src/closer_ai/ai/objection_classifier.py`; [doc](../ai/OBJECTION_CLASSIFIER_RUNNER_V0_1.md) | eval layer; predições ≠ `ObjectionEpisode` ≠ gold; labels CIT-O1, não enum do domínio |
| Ollama Classification Provider v0.1 (local-only) | `src/closer_ai/ai/ollama_provider.py`; [doc](../ai/OLLAMA_CLASSIFICATION_PROVIDER_V0_1.md); [ADR-005](../decisions/ADR_005-classification-provider-boundary.md) | loopback only; sem retry/reparo; nenhum provider cloud |
| Objection Guidance Engine v0 + Post-call Intelligence v0 (Value Sprint) | `src/closer_ai/ai/{objection_guidance,post_call}.py`, `src/closer_ai/demo/analyze_call.py`, `docs/knowledge/sales/guidance/`; [doc](../ai/OBJECTION_GUIDANCE_ENGINE_V0.md) | vertical slice sintético; retrieval = lookup por categoria; grounding lexical fail-closed; pilot runner + truncation guard + pilot summary prontos ([pilot](../product/REAL_CALL_PILOT.md)), bloqueado por autorização; graus da pesquisa preservados (nenhum movimento com taxa medida); **sem avaliação de qualidade** |
| Live Meet Copilot v0 (prioridade de produto) | `src/closer_ai/live/`, `extensions/google-meet/`; [doc](../product/LIVE_MEET_COPILOT_V0.md) | **validado ponta a ponta em Meet real de teste (2026-10-21)**: captions → speaker/role → classifier E1 @ 4k → normalização `price_override` → policy → knowledge por categoria exata → CommercialGuidance → grounding VALID → recomendação ACTIVE na sidebar (PRICE_BUDGET, move CLARIFY). Fila latest-wins, `active_analysis` vs `last_completed_analysis`, `--debug`. v1 (branch `feat/live-copilot-v1`, validado em Meet real de teste em 2026-10-22: PRICE_BUDGET e AUTHORITY_INTERNAL_BUY_IN GUIDED/VALID/ACTIVE, frase neutra sem recomendação; `authority_override` TIMING→AUTHORITY em dependência explícita de terceiro): card "Cliente disse + Sugestão" e latência caption→sidebar ~16–17 s → ~13,5–14,5 s de mediana no benchmark sintético (`python -m closer_ai.live.bench`), precisão no probe 4/8 → 7/8 sem falso positivo. Limites: latência real do v1 não registrada (só sintética); gargalo = geração de tokens com o modelo 30 % em CPU (GPU 6 GB); 2 categorias validadas ao vivo; precisão medida só em 14 frases sintéticas; calls longas reais não validadas; sem Playbook Compliance / Opportunity Detection / Manager Intelligence; backlog B1–B3 no [doc](../product/LIVE_MEET_COPILOT_V0.md#backlog-from-the-2026-10-21-meeting-not-implemented) |
| Experiment Runner v0.1 | `src/closer_ai/ai/experiment_runner.py`; [doc](../ai/EXPERIMENT_RUNNER_V0_1.md) | compliance operacional + proveniência; **sem métricas de qualidade**; artifacts privacy-first em `artifacts/` (gitignored) |
| Privacy boundary + OCI shared storage foundation | [ADR-004](../decisions/ADR_004-real-data-privacy-boundary.md); `docs/data/` | OCI provisionado e smoke-tested **só com dado sintético**; nenhum dado real enviado |
| Agent harness + CI | `.claude/agents/`, `docs/agents/`, `.github/workflows/ci.yml` | — |

Execução experimental já feita localmente, só com dado sintético (qwen3:8b via Ollama): 1 call ×
E0/E1/E2 e um experimento 12 × 3 (as 12 calls do Calibration Kit v0.1 × E0/E1/E2). Isso exercitou o
comportamento de orquestração e de compliance (statuses, proveniência, artifact). O artifact ficou
local e gitignored (`artifacts/`), portanto os números não são evidência versionada no repositório.
Isso **não** mede acurácia nem qualidade, **não** valida RAG nem taxonomia e **não** diz que um braço
é melhor.

## DRAFTED (docs, pré-pilot)

| Doc | Status |
|---|---|
| [Golden Set & Annotation Protocol v1](../evals/GOLDEN_SET_ANNOTATION_PROTOCOL_V1.md) | DRAFT; nenhum dado real anotado |
| [Objection Annotation Guideline v0.1](../evals/OBJECTION_ANNOTATION_GUIDELINE_V0_1.md) | ACTIVE draft; **CIT-O1 APPROVED** (8 labels provisórias + OTHER/UNKNOWN/AMBIGUOUS só em anotação/eval) |
| [Synthetic Calibration Kit v0.1](../evals/calibration/README_V0_1.md) | ACTIVE; 12 calls sintéticas; referências de calibração ≠ gold |
| [ObjectionEpisode v1](../domain/OBJECTION_EPISODE_V1_PROPOSAL.md) | PROPOSAL rev. 5; **não implementado** no domínio (D7) |
| [Call Intelligence Taxonomy v0.1](../domain/CALL_INTELLIGENCE_TAXONOMY_V0_1_PROPOSAL.md) | PROPOSAL; CIT-M3/CIT-O1 aprovados só como label set de anotação |
| [Sales Knowledge Retrieval & RAG v0.1](../ai/SALES_KNOWLEDGE_RETRIEVAL_RAG_V0_1_PROPOSAL.md) | PROPOSAL; E0/E1/E2 implementados, E3/E4 deferred |
| Guideline v0, Calibration Kit v0 | HISTORICAL, substituídos pelas v0.1 |

## NOT IMPLEMENTED / DEFERRED

- Calibration Dataset Loader (as 12 calls do kit como `Call`s verificadas por hash).
- Avaliação de qualidade contra gold. Não existe Golden Set real nem gold do pilot D3.
- E3 (seleção determinística de cards), E4 (semântico/híbrido), retrieval semântico, embeddings,
  vector DB.
- `ObjectionEpisode` v1 no domínio; migração do enum de objeção (D7).
- Policy comercial real do Outcome; adapters reais (Kommo/CRM, Zoom); ingestão Empreende.
- Provider de LLM cloud (e qualquer secret de LLM); remote Ollama.
- Storage/banco de produto, API/FastAPI, dashboard, analytics/Outcome Intelligence, experimentation
  engine de playbook, deployment/observability. O copilot ao vivo existe só como v0 local (acima).
- Playbook Compliance (B2), Opportunity Detection (B3) e Manager Intelligence. B2/B3 dependem do
  playbook comercial AgroTalento (Gabriel).

Os pacotes vazios `analytics/`, `api/`, `experiments/`, `integrations/` e `storage/` foram removidos
nesta reconciliação (YAGNI). Serão criados quando houver código real para eles.

## BLOCKED (decisão/acesso humano)

| Item | Blocked by |
|---|---|
| Qualquer processamento de dado real (Agro 108 calls, Empreende 35, Kommo) | autorização de uso + localização/acesso ([`HUMAN_DECISIONS.md`](HUMAN_DECISIONS.md)) |
| Upload de dado real no OCI | autorização + sign-off da política de storage + revisão de acesso |
| Pilot D3 (3–5 calls reais, dupla anotação) → gold | autorização + anotadores + dry run do kit v0.1 |
| Policy real de Outcome | D-G1, D-G2, D-G5, D-G6 (Gabriel) |
| ADR-002 Accepted | DI-M3: validação de Gabriel; DI-G1–G4 |
| Provider cloud | decisão de privacidade/autorização (ADR-004/005) |

## Open decisions

D3 (pilot), D6 (`resolution_status`), D7 (migração de contrato/enum), TAX (taxonomia final),
RAG-O1–O6 (inclui RAG-O4: exemplos positivos nos cards), D-G1–D-G8, DI-G1–DI-G4. As ADRs 002–005
aguardam aceite do texto por Matheus.

## Technical debt

Registro completo: [`TECH_DEBT.md`](TECH_DEBT.md). Destaques: TD-09 (CAS sem storage atômico),
TD-14 (lead não resolvido; mitigado, precisa validar com dado real), TD-04 (`MatchEvidence.detail`
sem enforcement de "sem PII"), TD-12 (branch protection não verificada).

## Next technical step

Live Copilot Dock UX + P0 Reliability + session recovery fechados na branch
`feat/live-copilot-dock-ux`, validados em Meet real de teste (dock escuro retrátil; delivery contract
com retry/idempotência/taxonomia de falhas; runtime exclusivo; `/health`; schema do classifier imposto
no live: soak de 30 min com 0 erros técnicos; recovery via `/rehydrate` sem reanálise). Follow-ups:
**latest-utterance anchoring / precision** (nova objeção ignorada com objeção antiga na janela) e
memória/latência do modelo (P1, Otávio). Detalhes no [doc do copilot](../product/LIVE_MEET_COPILOT_V0.md).
Latest-utterance anchoring mergeado (#43). **Commercial State v0** (branch `feat/commercial-state-v0`):
estado factual da call (dor, impacto, stakeholders, processo de decisão, buying signals, objeções do
engine, termos, próximos passos), cada fato com `segment_ids`, grounding determinístico e sem UX nova
(só no painel ••• → Avançado); fundação para B2/B3, que seguem não implementados. **Post-call Brief v0**
(branch `feat/post-call-brief-v0`): `POST /finalize` → brief JSON/Markdown determinístico a partir do
Commercial State (sem LLM, sem reclassificar; riscos determinísticos; idempotente).
**Latency P1** (branch `perf/live-latency-v1`): fast path determinístico para PRICE/AUTHORITY
inequívocos (pula só o classifier; displayed ~14,5 s → ~6 s nesses casos, precisão igual); classifier
menor (qwen3:4b) e contexto reduzido rejeitados; KV q8_0 opcional, não validado. Ver [doc](../product/LIVE_MEET_COPILOT_V0.md#latency-p1-perflive-latency-v1-2026-10-23).
**Playbook Compliance v1** (branch `feat/playbook-engine-v1`): playbook AgroTalento em JSON versionado
(61 regras E1–E12 + N/A, `business_status`) e engine determinístico sobre o Commercial State + sinais do closer:
E3-R1, E4-R1/R2, E6-R1/R2, E10-R1, E12-R1 e proibições lexicais (E4-R5, E1-R5); demais regras `not_evaluated`.
Só em ••• → Avançado e no Post-call Brief; sem score; Opportunity Detection não implementado.
Depois, a decidir
entre os itens do backlog no [doc do copilot](../product/LIVE_MEET_COPILOT_V0.md#backlog-from-the-2026-10-21-meeting-not-implemented):
B1 (UX "última fala do cliente + sugestão"), B2 Playbook Compliance e B3 Opportunity Detection. B2 e
B3 dependem do playbook comercial AgroTalento (Gabriel). Em paralelo: testar as outras 7 categorias
ao vivo e uma call longa de teste, ainda sem cliente. O Calibration Dataset Loader v0.1 continua
pendente.
