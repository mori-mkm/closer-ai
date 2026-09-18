# Next 7 Days — Execution Plan

Gerado em 2026-09-18 a partir do estado real do repositório
(`docs/context/CURRENT_STATE.md`). Não presume que dados reais chegarão amanhã — os itens de
Track A são sobre destravar acesso, não sobre processar dado que ainda não existe localmente.

## TRACK A — DATA ACCESS / VALIDATION

### A1 — Localizar e confirmar acesso ao corpus Agro/BeefPoint (108 calls) [P0]
- Goal: saber onde as 108 calls estão e confirmar que há acesso de leitura.
- Input: nenhum (é uma pergunta, não uma tarefa de engenharia).
- Output: local/credencial de acesso documentado (fora do repo público).
- Owner role: Data/Analytics Lead.
- Dependency: nenhuma.
- Definition of Done: pelo menos 1 call real acessível localmente (fora do Git).
- Can agent implement? Não.
- Human decision required? Sim — é decisão/ação humana pura.

### A2 — Localizar e confirmar acesso ao corpus Empreende Brazil (35 calls) [P1]
- Goal / Output / Owner: mesmo padrão de A1, para o segundo corpus.
- Dependency: nenhuma.
- Definition of Done: pelo menos 1 call real acessível localmente.
- Can agent implement? Não.
- Human decision required? Sim.

### A3 — Confirmar autorização formal de uso dos dados dos parceiros [P0]
- Goal: fechar a pergunta aberta desde o bootstrap (`docs/context/OPEN_QUESTIONS.md`).
- Input: nenhum.
- Output: confirmação documentada (formato/prazo).
- Owner role: Product/RevOps.
- Dependency: nenhuma.
- Definition of Done: resposta registrada em `docs/context/OPEN_QUESTIONS.md` (removida da
  lista de abertas) ou em ADR se envolver decisão de arquitetura de dados.
- Can agent implement? Não.
- Human decision required? Sim.

### A4 — Obter export ou acesso de API do Kommo [P0]
- Goal: destravar toda a Cadeia 2 de `docs/context/DATA_DEPENDENCIES.md`.
- Input: credencial/API key ou export manual.
- Output: amostra real de payload Kommo disponível localmente (fora do repo).
- Owner role: Data/Analytics Lead / Product/RevOps.
- Dependency: A3 (autorização) idealmente resolvida antes.
- Definition of Done: pelo menos 1 export/response real de deal/lead/stage acessível.
- Can agent implement? Não.
- Human decision required? Sim.

### A5 — Validar `AgroRawCall` contra 5 calls reais [P1]
- Goal: primeiro checkpoint do gate AGRO REAL READY (`docs/context/EXECUTION_GATES.md`).
- Input: acesso do item A1 (5 calls reais, fora do repo).
- Output: relatório de quality flags reais + lista de divergências entre hipótese e formato
  real, atualizando `docs/domain/AGRO_INGESTION_CONTRACT.md`.
- Owner role: AI/Backend Lead, executável por agent uma vez que A1 esteja resolvido.
- Dependency: A1.
- Definition of Done: 5 calls processadas com sucesso (ou falhas documentadas com causa raiz),
  premissas do parser reconciliadas ou corrigidas.
- Can agent implement? Sim, uma vez que o dado exista localmente e fora do repo (agent nunca
  commita o dado bruto).
- Human decision required? Só se a divergência exigir mudança de contrato do `Call` canônico
  (não deveria — `AgroRawCall` é a camada de fronteira feita exatamente para absorver isso).

## TRACK B — AI / GOLDEN SET

### B1 — Fechar regras de anotação do Golden Set v1 [P1]
- Goal: ter um processo de anotação definido antes de qualquer call real chegar, para não
  perder tempo quando o corpus estiver disponível.
- Input: taxonomia atual (`docs/domain/OBJECTION_MODEL.md`), `docs/context/OPEN_QUESTIONS.md`.
- Output: documento de regras de anotação + critério de amostragem representativa.
- Owner role: Product/RevOps + AI/Backend Lead.
- Dependency: nenhuma (não depende do corpus).
- Definition of Done: regras escritas, revisadas, prontas para uso assim que houver calls
  reais para anotar.
- Can agent implement? Parcialmente — um agent pode redigir um primeiro rascunho a partir da
  taxonomia v0 existente, mas a decisão de critério final é humana.
- Human decision required? Sim, para aprovação final.

### B2 — Definir anotadores do Golden Set [P2]
- Goal: ter pessoas designadas antes do corpus chegar.
- Input: nenhum.
- Output: lista de anotadores + processo de adjudicação.
- Owner role: Product/RevOps.
- Dependency: nenhuma.
- Definition of Done: pelo menos 2 anotadores confirmados.
- Can agent implement? Não.
- Human decision required? Sim.

## TRACK C — ENGINEERING INDEPENDENT OF REAL DATA

Incluído só onde há valor real sem o corpus — ver revisão anti-overengineering no relatório
de reconciliação para o que foi deliberadamente excluído (FastAPI, storage, dashboard, cloud).

### C1 — Verificar branch protection / required checks no GitHub [P0]
- Goal: confirmar que o CI está de fato bloqueando merge direto em `main` (hoje marcado
  UNKNOWN em `docs/context/CURRENT_STATE.md`).
- Input: acesso autenticado ao GitHub (`gh auth login` ou UI).
- Output: confirmação documentada em `docs/context/CURRENT_STATE.md`.
- Owner role: quem tem admin no repositório (Matheus).
- Dependency: nenhuma.
- Definition of Done: status confirmado (configurado ou não) e documentado.
- Can agent implement? Não (requer autenticação humana), mas um agent pode atualizar o doc
  assim que a resposta existir.
- Human decision required? Sim, para autenticar e checar.

### C2 — Avaliar heuristicamente se `MatchEvidence.detail` precisa de enforcement de PII (TD-04) [P2]
- Goal: decidir, antes do CRM READY gate, se vale um detector heurístico simples ou se
  continua sendo convenção documentada.
- Input: `docs/context/TECH_DEBT.md` (TD-04).
- Output: decisão registrada (ADR se mudar o contrato de `MatchEvidence`).
- Owner role: AI/Backend Lead.
- Dependency: nenhuma.
- Definition of Done: decisão tomada e documentada (mesmo que a decisão seja "não agora").
- Can agent implement? Sim, para levantar as opções; decisão final é humana (mexe em
  contrato de domínio).
- Human decision required? Sim, para a decisão final (contrato de domínio não muda
  silenciosamente — regra de `AGENTS.md`).

## Priorização resumida

- **P0**: A1, A3, A4, C1 — todos bloqueadores transversais, nenhum é trabalho de código.
- **P1**: A2, A5, B1 — progridem assim que P0 destravar, ou já podem começar (B1).
- **P2**: B2, C2 — importantes, não urgentes.

Nenhum item de Track C entra em NOW no roadmap principal — são checagens/decisões pontuais,
não features. Ver `docs/product/ROADMAP.md` para a visão de fases completa.
