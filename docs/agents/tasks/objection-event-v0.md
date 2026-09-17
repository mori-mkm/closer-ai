# Task — Objection Intelligence v0

## Goal

Definir e implementar o contrato inicial de `ObjectionEvent` e um harness mínimo para
avaliação da extração estruturada a partir de uma `Call` canônica.

## Why

Objeções são um dos eventos comerciais centrais do AI Closer (ver
`docs/architecture/DATA_MODEL.md` — `Objections` é um dos sub-itens de `Call` dentro de
`Deal`). Precisamos de um contrato estável e avaliável antes de conectar isso a CRM e a
outcomes — esse é o próximo passo natural depois do schema canônico de `Call`
(`docs/product/ROADMAP.md`, fase "Call Intelligence").

## Read first

- `AGENTS.md`
- `docs/context/CURRENT_STATE.md`
- `docs/architecture/DATA_MODEL.md`
- `docs/domain/SALES_MODEL.md`
- `src/closer_ai/normalization/models.py` (contrato de `Call`/`TranscriptSegment` já existente
  — `ObjectionEvent` deve referenciar isso, não duplicar)

## Allowed files

Ver tabela de ownership completa em `docs/agents/TEAM_ORCHESTRATION.md`. Resumo por agente:

| Agente | Allowed files |
|---|---|
| Domain Agent | `docs/domain/OBJECTION_MODEL.md`, `src/closer_ai/domain/objection.py`, `src/closer_ai/domain/__init__.py` |
| AI Engineer | `src/closer_ai/ai/objection_extraction.py`, `src/closer_ai/ai/__init__.py` |
| Evaluator | `evals/objection_v0/**`, `tests/unit/domain/test_objection.py`, `tests/unit/ai/test_objection_extraction.py`, `tests/fixtures/synthetic_objection_calls.py` |
| Reviewer | nenhum (read-only) |

## Do not modify

`src/closer_ai/normalization/**` (contrato existente, só leitura), `src/closer_ai/analytics/`,
`src/closer_ai/api/`, `src/closer_ai/storage/`, `src/closer_ai/integrations/`,
`src/closer_ai/experiments/`, qualquer doc fora da lista acima, `main`.

## Inputs

Fixtures sintéticas apenas — reusar `closer_ai.normalization.Call` e o padrão de
`tests/fixtures/synthetic_calls.py`. Nenhum dado real de cliente.

## Expected output

- `ObjectionEvent`: contrato Pydantic (frozen), com invariantes documentadas, referenciando
  `call_id` + `segment_id` de origem (evidence span) — não texto bruto duplicado.
- `ObjectionExtractor`: interface (Protocol/ABC) provider-agnóstica + uma implementação de
  referência determinística (regra/keyword, não chamada de LLM real).
- Golden set sintético + script de avaliação com métricas apropriadas ao estágio (schema
  validity, precision/recall de detecção, evidence grounding).
- Testes unitários adversariais para o contrato e para a extração.

## Acceptance criteria

- `ObjectionEvent` validado por Pydantic, imutável, com `call_id`/`segment_id` rastreáveis até
  a `Call`/`TranscriptSegment` de origem.
- `ObjectionExtractor` é uma interface limpa; a implementação de referência não faz chamada de
  rede.
- Golden set e fixtures 100% sintéticos.
- `pytest` passa (suite completa, incluindo os 44 testes já existentes de `normalization/`).
- `ruff check .` passa.
- Nenhum arquivo fora do "Allowed files" de cada agente foi tocado.
- Reviewer emite veredito (`APPROVE`/`REJECT`) com evidência antes de qualquer PR.

## Tests

`pytest` (suite completa) e o script de avaliação em `evals/objection_v0/run_eval.py`.

## Blockers / assumptions

- Assume-se que "objeção" nesta v0 cobre um conjunto pequeno e explícito de categorias
  (ex.: preço, tempo/prioridade, confiança/autoridade, sem necessidade) — taxonomia completa
  fica para uma task futura de Golden Set mais amplo (`docs/product/ROADMAP.md`, fase 3).
- Assume-se que `ObjectionEvent` não referencia `Deal`/`Outcome` ainda — isso é
  intencionalmente adiado (ver `docs/product/MVP_SCOPE.md`).
- Se o Domain Agent encontrar ambiguidade não coberta acima, ele reporta ao Lead em vez de
  decidir sozinho (regra de `AGENTS.md`).
