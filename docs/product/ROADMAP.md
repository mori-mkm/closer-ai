# Roadmap

Sequência de fases do produto, reconciliada com o estado real do repositório em 2026-09-18.
Não é cronograma com datas — é ordem de dependência. Estado operacional completo:
[`docs/context/CURRENT_STATE.md`](../context/CURRENT_STATE.md).

## DONE

- Bootstrap do repositório: política de branches/PR, `.gitignore` defensivo, funil de
  contexto para agents.
- Canonical Call schema (`normalization/models.py`) — Participant, TranscriptSegment, IDs
  determinísticos.
- Agent harness (Domain Agent, AI Engineer, Evaluator, Reviewer) + workflow de worktree.
- Objection Intelligence v0 — contrato `ObjectionEvent`, extractor rule-based, eval harness
  contra golden set sintético.
- Agro normalization vertical slice — parser + boundary model (`AgroRawCall`), contra
  hipótese de formato, não dado real.
- Deal-level commercial model — `Lead`, `Deal`, `StageEvent`, `CallDealMatch`,
  `MatchEvidence`, `ExactExternalIdMatcher`.
- CI real no GitHub Actions (import sanity check + ruff + pytest em toda PR/push para main).

## NOW / BLOCKED ON DATA

Estes itens são o próximo passo lógico do roadmap, mas nenhum progride sem uma ação humana
(acesso a dado real, credencial, autorização):

- Obter o corpus Agro/BeefPoint (108 calls) e o corpus Empreende Brazil (35 calls).
- Obter export ou acesso de API Kommo.
- Validar as hipóteses de `AgroRawCall`/`docs/domain/AGRO_INGESTION_CONTRACT.md` contra uma
  amostra real pequena (formato do transcript, unidade de `duration_seconds`, id estável de
  participante).
- Confirmar autorização formal de uso dos dados das empresas parceiras
  (`docs/context/OPEN_QUESTIONS.md`).
- Ingestão CRM real (mapear campos Lead/Deal/Stage do Kommo para o contrato existente).
- Call↔Deal matching real (rodar `ExactExternalIdMatcher`, ou uma heurística nova, contra
  Calls e Deals reais).

## PARALLEL / CAN PROGRESS WITHOUT DATA

Só itens com valor real sem depender do corpus:

- Definir e documentar a taxonomia de anotação do Golden Set (regras, categorias, processo de
  adjudicação) — pode ser desenhada antes de ter calls reais para anotar.
- Recrutar/definir anotadores para o Golden Set real.
- Fechar decisões de produto hoje em aberto que não dependem de dado (ex.: definição exata de
  "outcome" para Outcome Intelligence — ver `docs/context/OPEN_QUESTIONS.md`).

Deliberadamente **não** incluído aqui: FastAPI, storage/banco, dashboard, cloud,
experimentation. Ver `docs/context/EXECUTION_GATES.md` e a revisão anti-overengineering no
relatório de reconciliação — nenhum destes tem consumidor real ainda.

## NEXT

Depende de dado real chegar (bloco acima):

- Golden Set real de objeções (20-30 calls, amostragem representativa, dupla anotação,
  adjudicação, cálculo de agreement).
- Avaliar `RuleBasedObjectionExtractor` v0 contra o Golden Set real; decidir se um extractor
  LLM-backed se justifica.
- Processar o corpus real em batch (108 + 35 calls) através do pipeline Agro/Empreende.
- Outcome Intelligence — join Deal↔Call↔Evento com outcome final real, amostra suficiente de
  won/lost.
- Primeira superfície de produto (API/dashboard) — só depois de Outcome Intelligence ter sinal
  real para mostrar.

## LATER

- Experimentation Engine — testar mudanças de playbook de forma controlada.
- Playbook Learning — atualizar playbook a partir de experimento.
- Cortex / Realtime Copilot — adiado até 6-8 (Outcome Intelligence, Manager Intelligence)
  estarem validados com dado real.
- Multi-tenant hardening.
- Productionization (storage definitivo, API pública, observability, cloud).
- ROI Proof — atribuição de resultado ao uso do sistema.

## Dependências explícitas

```
Dados reais (Agro + Kommo) — bloqueador transversal
  ├── Agro real → validação do parser → Golden Set real → Extractor v1 → Outcome Intelligence
  └── Kommo real → Lead/Deal/StageEvent reais → Call↔Deal real ─────────┘
```

Mapa completo de inputs/outputs/blockers por nó: `docs/context/DATA_DEPENDENCIES.md`.
Definition of done por camada: `docs/context/EXECUTION_GATES.md`.
