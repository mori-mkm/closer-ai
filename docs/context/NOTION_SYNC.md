# Notion Sync Handoff

Handoff operacional para atualizar o Project Hub no Notion manualmente — esta sessão não tem
acesso ao Notion e não o edita diretamente. Mapeamento feito a partir dos números de task
citados pelo usuário; não há referência a esses números dentro do repositório (nenhum arquivo
local cita "Task 17", "Task 33" etc.), então o mapeamento abaixo é inferido pelo conteúdo, não
confirmado contra o Notion em si. Confirmar o título exato de cada task no Notion antes de
aplicar o status sugerido.

| Task | Suggested status | Evidence | Remaining work | Should close? |
|---|---|---|---|---|
| Task 17 — Git workflow | DONE | `docs/agents/WORKFLOW.md`, branch policy ativa desde o bootstrap, PRs #1-#6 todos via branch+PR+squash merge | Nenhum item de código pendente. Confirmar apenas se branch protection está de fato ativada no GitHub (`docs/context/CURRENT_STATE.md` — UNKNOWN) | Sim, com a ressalva de branch protection a confirmar manualmente |
| Task 24 — storage/data protection | PARTIAL | `.gitignore` defensivo, `data/README.md`, nenhum dado real versionado — mas `src/closer_ai/storage/` é um pacote vazio, nenhuma persistência real existe | Camada de storage real não foi implementada (fora de escopo até haver decisão de banco) — se a task original incluía isso, ela é mais ampla do que "proteção de dado no Git" | Não — só a parte de proteção de dado no Git está pronta; se a task cobre storage layer, mantenha aberta |
| Task 29 — canonical schema | DONE | `src/closer_ai/normalization/models.py` + `ids.py`, 44 testes, `docs/architecture/DATA_MODEL.md`, `normalize_call()` prova o contrato raw→Call | Nenhum — só falta validar contra fonte real, o que é uma task diferente (ingestão), não parte do contrato canônico em si | Sim |
| Task 33 — CI | DONE | `.github/workflows/ci.yml` mergeado (PR #6, commit `52f8cfa`), 208 testes + ruff rodando em toda PR/push | Confirmar branch protection ativada (ver Task 17) | Sim, com a mesma ressalva de branch protection |
| Task 34 — Deal-level | DONE | `src/closer_ai/domain/{lead,deal,matching}.py`, 85 testes (lead 12 + deal 32 + matching 33 + matcher 8), `docs/domain/DEAL_MODEL.md`, PR #5 mergeado | Nenhum item de contrato pendente. Matching real contra CRM é trabalho futuro (não parte deste contrato) | Sim |
| Task 37 — Agro normalization pipeline | **PARTIAL / BLOCKED** | `src/closer_ai/ingestion/agro/` implementado, 50 testes (45 unit + 5 integração) — mas 100% contra formato hipotético, nunca processou uma call real | Bloqueado por acesso ao corpus real (108 calls) — "pipeline Agro real" no sentido de processar dado real não foi entregue | Não — se a task original pedia "pipeline Agro real", ela não está completa. Se pedia só o pipeline de código contra formato hipotético, está completa; verificar o escopo original da task no Notion |
| Task 47 — objection_episode / objection contract | **PARTIAL** | `src/closer_ai/domain/objection.py` implementa `ObjectionEvent` v0 — evidência de segmento único, 4 categorias fechadas + `other`, sem confidence, sem referência a Deal | `ObjectionEvent` v0 é deliberadamente mais restrito que um "objection_episode" completo (sem multi-segmento, sem resolução/estratégia, sem link a Deal) — ver `docs/domain/OBJECTION_MODEL.md`, seção "Fora de escopo" | Não — se a task original descrevia "objection_episode" como conceito mais amplo, isso não foi entregue; v0 é um subconjunto deliberado |
| Task 49 — canonical IDs | DONE | `src/closer_ai/normalization/ids.py` (call/segment) + mesma técnica reimplementada em `domain/objection.py`, `domain/lead.py`, `domain/deal.py`, `domain/matching.py` — sha256 sobre `json.dumps`, sem PII no hash, 24 hex chars, prefixo por tipo | Nenhum | Sim |

## Outras tasks que provavelmente precisam atualização

- Qualquer task Notion referente a "Objection Intelligence v0" ou "PR #3" — mapeia para o
  mesmo trabalho da Task 47 acima; mesma ressalva de escopo parcial.
- Qualquer task referente a "Agro vertical slice" ou "PR #4" — mapeia para Task 37.
- Qualquer task referente a "Deal-Foundation" ou "PR #5" — mapeia para Task 34.
- Se existir uma task Notion específica para "corpus real" ou "obter dados" (Agro/Kommo), ela
  deveria estar marcada como o item mais crítico em aberto — nada no roadmap progride além do
  já entregue sem ela (`docs/context/DATA_DEPENDENCIES.md`).
- Se existir uma task Notion para "Golden Set" separada da Task 47, ela deve ser marcada NOT
  STARTED no sentido real (o golden set existente é 100% sintético, não a amostra real do MVP
  — ver `docs/context/TECH_DEBT.md` TD-13).

## Como usar este handoff

1. Abrir cada task no Notion pelo número.
2. Comparar o título/descrição original da task com a "Evidence" acima.
3. Se a descrição original da task é mais ampla que a evidência (ex. Task 37 pedindo "processar
   as 108 calls reais"), manter a task aberta e criar/ligar uma sub-task ou comentário
   explicando o que falta — não fechar por otimismo.
4. Atualizar o status no Notion manualmente; esta sessão não escreve no Notion.
