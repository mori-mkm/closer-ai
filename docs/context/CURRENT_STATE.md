# Current State

_Atualizar somente quando o estado real do sistema mudar. Não é diário, não registra commits._

## Snapshot

- Data do snapshot: 2026-09-18
- Main commit: `52f8cfa` (merge de PR #6, `chore/ci` → `main`), `origin/main` == `main`, working tree clean
- Tests: 208 passed, 0 failed, 0 skipped (`pytest -q`)
- Lint: `ruff check .` limpo
- CI: ativo em `.github/workflows/ci.yml` (workflow `CI`, job `test`) — roda em `pull_request`→`main` e `push`→`main`; passos: checkout, setup Python 3.11, `pip install -e ".[dev]"`, `python -c "import closer_ai"`, `ruff check .`, `pytest -q`
- Branch protection / required status checks no GitHub: **UNKNOWN / MANUAL CHECK REQUIRED** — não verificável localmente (sem `gh auth login` nesta sessão); confirmar manualmente em Settings → Branches
- Repository health: sem TODO/FIXME/HACK/XXX no código (`src/`, `tests/`, `evals/`); nenhum dado real ou PII detectado em `data/`, fixtures ou docs versionados

## Product thesis

```
Calls / transcripts
  → structured commercial events (ObjectionEvent, futuros Moment/Signal/Risk/Commitment)
  → Deal (via CallDealMatch, nunca nesting)
  → Outcome (só no Deal, nunca na Call)
  → intelligence (agregados, padrões)
  → recommendations / experiments
  → learning (playbook)
```

Call outcome != Deal outcome. Esta distinção já está implementada como invariante de schema
(`Call` não tem campo de outcome; `Deal.outcome` é obrigatório e sem default) — ver
`docs/architecture/DATA_MODEL.md` e `docs/domain/DEAL_MODEL.md`.

## Implemented

| Component | Status | Evidence |
|---|---|---|
| Canonical Call schema | IMPLEMENTED | `src/closer_ai/normalization/models.py`; 44 testes em `tests/unit/normalization/` |
| Canonical IDs (call/segment) | IMPLEMENTED | `src/closer_ai/normalization/ids.py` (sha256 determinístico, sem PII no hash) |
| Participants / TranscriptSegment | IMPLEMENTED | mesmo arquivo acima; invariantes: frozen, `segment_index` contíguo, `speaker_id` referencial |
| `normalize_call()` (raw dict sintético → Call) | IMPLEMENTED | `src/closer_ai/normalization/normalize.py` — entry point só para dado sintético, não um adapter de fonte real |
| Agro ingestion boundary (`AgroRawCall`/`AgroParseResult`) | IMPLEMENTED (contra hipótese, não dado real) | `src/closer_ai/ingestion/agro/models.py`, `parser.py`; 45 testes unit + 5 integração; `docs/domain/AGRO_INGESTION_CONTRACT.md` documenta cada campo como hipótese não confirmada |
| ObjectionEvent contract | IMPLEMENTED | `src/closer_ai/domain/objection.py`; 17 testes; `docs/domain/OBJECTION_MODEL.md` |
| ObjectionExtractor (rule-based v0) | IMPLEMENTED | `src/closer_ai/ai/objection_extraction.py`; keyword matcher em português, 4 categorias + `other` (inatingível pela implementação v0) |
| Objection eval harness | IMPLEMENTED (golden set 100% sintético) | `evals/objection_v0/` — 9 entradas sintéticas, métricas: schema validity, evidence grounding, precision/recall, unsupported rate |
| Lead contract | IMPLEMENTED | `src/closer_ai/domain/lead.py`; 12 testes |
| Deal + StageEvent contract | IMPLEMENTED | `src/closer_ai/domain/deal.py`; 32 testes |
| CallDealMatch + MatchEvidence contract | IMPLEMENTED | `src/closer_ai/domain/matching.py`; 33 testes |
| `CallDealMatcher` protocol + `ExactExternalIdMatcher` | IMPLEMENTED (baseline único, 1 sinal) | mesmo arquivo; `test_matcher.py`; resolve `call.source_id` como registro do CRM via Deal Identity (`resolve_deal_for_source_record`); só `linked` gera candidato; sem fallback para `deal.external_id` |
| Agent harness (Domain Agent / AI Engineer / Evaluator / Reviewer) | IMPLEMENTED | `.claude/agents/*.md`, `docs/agents/*.md` |
| CI (GitHub Actions) | IMPLEMENTED | `.github/workflows/ci.yml`, `docs/agents/WORKFLOW.md` (seção merge gate) |
| Data boundary (`.gitignore`, `data/README.md`) | IMPLEMENTED | ver Fase 12 — nenhum dado real versionado, docs de negócio ignorados |

## Partial

| Component | Status | Limitation |
|---|---|---|
| Agro normalization pipeline | PARTIAL / BLOCKED ON DATA | Passa 100% dos testes sintéticos, mas nunca processou uma call real. Formato de origem (shape do Zoom, unidade de `duration_seconds`, id estável de participante) é hipótese, não confirmado. |
| Call↔Deal matching | PARTIAL / BLOCKED ON DATA | Contrato + 1 matcher determinístico existem; nunca rodou contra Lead/Deal reais do Kommo. Sem heurística de nome/email/telefone (Participant não carrega email/telefone). |
| Objection Golden Set | PARTIAL (sintético apenas) | 9 exemplos sintéticos, um único autor, sem double-annotation, sem cálculo de agreement. Não é o "Golden Set real" do roadmap (20-30 calls reais anotadas). |
| Golden Set Annotation Protocol v1 | DRAFTED (doc, pré-pilot) | `docs/evals/GOLDEN_SET_ANNOTATION_PROTOCOL_V1.md`; nenhum dado real anotado; bloqueado por autorização de dados reais, pilot D3 (3–5 calls, dupla anotação) e D6 (`resolution_status`); taxonomia final pendente |
| Objection Annotation Guideline v0 | SUPERSEDED para o pilot (registro histórico) | `docs/evals/OBJECTION_ANNOTATION_GUIDELINE_V0.md`; categorias = enum v0; substituída pela v0.1 |
| Objection Annotation Guideline v0.1 | DRAFTED (doc, pré-pilot) | `docs/evals/OBJECTION_ANNOTATION_GUIDELINE_V0_1.md`; **CIT-O1 APPROVED**: D3 e Golden Set v1 usam o label set provisório de 8 categorias + OTHER/UNKNOWN/AMBIGUOUS só em anotação/eval; enum do domínio inalterado; não usada em dado real; TAX, D3, D6 e D7 abertos; calibration kit ainda no enum v0 (revisão pendente) |
| Synthetic Annotation Calibration Kit v0 | DRAFTED (pronto para dry run) | `docs/evals/calibration/` — 3 calls sintéticas, templates manuais, referência de calibração (não é gold); nenhum dry run executado; anotadores não calibrados; D3, D6 e TAX abertos |
| Synthetic Annotation Calibration Kit v0.1 | DRAFTED (pronto para dry run) | `docs/evals/calibration/*_V0_1.md` — 12 calls sintéticas alinhadas à guideline v0.1 / CIT-O1 (label set de anotação, enum do domínio inalterado), modos solo e dupla anotação, referências de calibração (não são gold); kit v0 preservado; nenhum dry run executado; D3, TAX, D6 e D7 abertos |
| Call Intelligence Taxonomy v0.1 | PROPOSAL (doc, research-integrated, pré-pilot) | `docs/domain/CALL_INTELLIGENCE_TAXONOMY_V0_1_PROPOSAL.md` — integra pesquisa externa ao contrato `ObjectionEpisode`; sem mudança de contrato, enum, schema ou guideline; 8 categorias aprovadas só como candidatas provisórias v0.1 (CIT-M3), enum do domínio inalterado, contrato gated por pilot/D7; nenhum RAG/Knowledge Base implementado; TAX, D3 e D6 abertos |
| Sales Knowledge Base v0.1 | DRAFTED (doc, pré-pilot) | `docs/knowledge/sales/` — 8 knowledge units provisórias de categorias de objeção candidatas + source registry (`SOURCES.md`); conhecimento define/explica, nunca prova ocorrência numa call; nenhum RAG/retrieval/embedding implementado; enum do domínio inalterado; TAX, D3 e D6 abertos |
| Sales Knowledge Retrieval & RAG v0.1 | PROPOSAL (doc, pré-implementação) | `docs/ai/SALES_KNOWLEDGE_RETRIEVAL_RAG_V0_1_PROPOSAL.md` — propõe injeção determinística dos 8 cartões da KB (full context) e um experimento pareado (E0–E4) antes de qualquer retrieval seletivo; nenhum RAG, retrieval, embedding, vector DB, classificador ou eval implementado; bloqueado por gold real (D3), D6/D7 e CIT-O1 |
| Knowledge Context Builder v0.1 | IMPLEMENTED (full-context knowledge assembly only) | `src/closer_ai/ai/knowledge_context.py`; 35 testes em `tests/unit/ai/test_knowledge_context.py`; `docs/ai/KNOWLEDGE_CONTEXT_BUILDER_V0_1.md`. Lê os 8 knowledge units, valida (fail explicit, conhecimento negativo obrigatório), renderiza cards determinísticos, monta o bloco EXTERNAL KNOWLEDGE e calcula sha256; subset só explícito pelo caller. **Sem** retriever, LLM, embeddings, vector DB, classificador ou RAG eval; RAG-O4 aberta |
| Objection taxonomy | PARTIAL (v0, 4 categorias fechadas) | `price`, `timing_priority`, `trust_authority`, `no_need`, `other` (inatingível pela extração v0). Taxonomia completa é fase futura. |

## Blocked

| Component | Status | Blocked by |
|---|---|---|
| Validação de `AgroRawCall` contra fonte real | BLOCKED | acesso às 108 calls Agro/BeefPoint |
| Processamento do corpus real (108 + 35 calls) | BLOCKED | acesso aos dados reais + autorização de uso |
| Ingestão Kommo real | BLOCKED | export/API Kommo não disponível localmente |
| Call↔Deal matching real | BLOCKED | depende de Lead/Deal reais (Kommo) + Calls reais (Agro) |
| Outcome Intelligence empírico | BLOCKED | depende de Deal↔Call real com outcome final |
| Empreende Brazil ingestion | NOT STARTED | nenhum pipeline específico existe; bloqueado pelas mesmas 35 calls reais |

## Not started

CRM/Kommo adapter, Zoom real adapter, LLM extraction, Analytics module (`analytics/` vazio),
Experimentation Engine (`experiments/` vazio), Storage layer (`storage/` vazio), API/FastAPI
(`api/` vazio), Dashboard, Cloud/deployment, Observability. Todos os pacotes acima existem só
como diretórios com `__init__.py` vazio — nenhuma linha de implementação.

## Current critical path

```
Acesso real aos dados (Agro + Kommo)
  → validar hipóteses do parser Agro contra formato real
  → processar amostra pequena (5 calls reais) para calibrar quality flags
  → construir Golden Set real (20-30 calls, dupla anotação)
  → avaliar extractor v0 contra Golden Set real
  → obter export/acesso Kommo
  → mapear campos Lead/Deal/Stage reais
  → rodar matching real
  → Outcome Intelligence
```

Nenhum destes passos é código-only — todos dependem de uma decisão ou acesso humano
(autorização de dado, credencial Kommo, anotadores do golden set).

## Real-data blockers

Lista objetiva do que só progride com dado real — ver `docs/context/DATA_DEPENDENCIES.md` para
o mapa completo de inputs/outputs/owner por nó:

1. 108 calls Agro/BeefPoint — localização e acesso não confirmados nesta sessão.
2. 35 calls Empreende Brazil — idem.
3. Export ou acesso de API Kommo — não disponível.
4. Autorização formal de uso dos dados das empresas parceiras — status não confirmado
   (`docs/context/OPEN_QUESTIONS.md`).

## Technical debt

Registro completo: `docs/context/TECH_DEBT.md`. Itens P0/P1 mais relevantes hoje:
- **TD-14 (P0, achado nesta rodada de onboarding):** o parser Agro nunca resolve
  `role="lead"` para nenhum participante (só `closer`/`unknown`) — sem isso,
  `RuleBasedObjectionExtractor` produz zero objeções silenciosamente em qualquer call real.
  Bloqueador antes de avaliar o extractor v0 contra dado real.
- Identidade de participante Agro baseada em nome/label normalizado (`_slugify`), não em id
  estável da fonte — colisões fundem participantes distintos (P1).
- `MatchEvidence.detail` é convenção não-enforced de "sem PII" — nada no schema impede um
  caller descuidado (P1).
- `Deal.current_stage` vs. histórico de `StageEvent` não tem cross-check automático — depende
  do write path futuro (P2, sem storage layer ainda não é urgente).
- `value`/`currency` do Deal usam `float`, não `Decimal` (P2, aceito para v0).
- GitHub Actions pinado por major tag (`@v4`/`@v5`), não por SHA (P3).

## Decisions already made

- Sem banco de dados, storage, provedor de LLM ou arquitetura de matching definitivos — adiado
  de propósito.
- Stage e Outcome são eixos ortogonais no Deal (nunca "won"/"lost" como Stage).
- Deal não embute Call/Objection — associação só via `CallDealMatch`, nunca nesting/lista.
- IDs determinísticos (sha256 sobre `json.dumps`) em toda entidade nova, nunca derivados de
  PII.
- `ObjectionEvent` evidência é um `segment_id` inteiro, não span de caracteres (v0).
- Ambiguidade de matching é representada como múltiplas linhas `CallDealMatch`, nunca um
  vencedor escolhido silenciosamente.
- Push direto em `main` proibido desde o bootstrap; todo trabalho via PR + squash merge.
- CI real (GitHub Actions) é o merge gate desde PR #6.

## Next milestones

1. Obter acesso aos dados reais (Agro + Kommo) — bloqueador crítico, não-código.
2. Validar hipóteses do `AgroRawCall` contra uma amostra pequena real (5 calls).
3. Construir Golden Set real de objeções (20-30 calls, dupla anotação, cálculo de agreement).
4. Avaliar `RuleBasedObjectionExtractor` contra o Golden Set real; decidir se justifica um
   extractor LLM-backed.
5. Obter export/acesso Kommo e mapear Lead/Deal/Stage reais.
6. Rodar `ExactExternalIdMatcher` (ou heurística nova) contra Call↔Deal reais.

Ver `docs/context/NEXT_7_DAYS.md` para execução tática e `docs/product/ROADMAP.md` para
sequência de fases completa.
