# Team Orchestration

Como o Lead (Claude Code principal) coordena agentes especializados para desenvolver uma
feature real. Isto documenta o **processo multiagente**; regras gerais de agent, funil de
contexto e convenção de worktree já existem e não são repetidas aqui — ver
[`AGENTS.md`](../../AGENTS.md), [`WORKFLOW.md`](WORKFLOW.md),
[`CONTEXT_STRATEGY.md`](CONTEXT_STRATEGY.md), [`TASK_TEMPLATE.md`](TASK_TEMPLATE.md).

## Fluxo

```
Human
  ↓
Lead                    (entende a feature, decompõe, NÃO implementa)
  ↓
Task Graph              (dependências e paralelismo explícitos, ver task em docs/agents/tasks/)
  ↓
Specialized Agent        (.claude/agents/*.md — Domain Agent, AI Engineer, Evaluator)
  ↓
Worktree                 (1 task = 1 branch = 1 owner = 1 worktree — WORKFLOW.md)
  ↓
Tests / Evaluation        (Evaluator, independente de quem implementou)
  ↓
Reviewer                  (.claude/agents/reviewer.md — read-only, APPROVE/REJECT)
  ↓
Human approval             (merge é sempre decisão humana)
```

## Responsabilidades

Ver `.claude/agents/*.md` para o prompt completo de cada papel. Resumo:

| Agente | Decide | Não faz |
|---|---|---|
| Domain Agent | schema, invariantes, edge cases do contrato | pipeline de IA, testes |
| AI Engineer | implementação atrás de interface provider-agnóstica | alterar contrato sozinho |
| Evaluator | métricas, golden set, testes adversariais | corrigir a implementação |
| Reviewer | APPROVE/REJECT com evidência | implementar, corrigir, merge |

## Dependências e paralelismo

Domain Agent e Evaluator (fase de design) podem rodar em paralelo — nenhum dos dois escreve
no arquivo do outro nessa fase. AI Engineer depende do contrato do Domain Agent estar pronto.
Evaluator (fase de testes) depende da implementação do AI Engineer estar pronta. Reviewer
depende de tudo acima. O grafo de uma task concreta vive no arquivo da task
(`docs/agents/tasks/*.md`), não aqui — este documento descreve o padrão, não uma instância.

## File ownership

Cada task define sua própria tabela de ownership (campo obrigatório em
[`TASK_TEMPLATE.md`](TASK_TEMPLATE.md): "Allowed files"). Regra fixa: nenhum arquivo tem dois
donos simultâneos numa mesma task. Se dois agentes precisam do mesmo arquivo, eles rodam em
sequência, não em paralelo.

## Worktrees

Um agente = um worktree quando há execução paralela real (processos/terminais separados),
seguindo exatamente [`WORKFLOW.md`](WORKFLOW.md#worktrees-paralelismo-real). Cada worktree
roda `claude --agent <nome>` (ex.: `claude --agent domain-agent`) — uma sessão inteira com a
persona daquele `.claude/agents/*.md`. Isso funciona tanto para uma pessoa (Matheus/Otávio)
quanto para um agente — mesmo mecanismo, mesma garantia de isolamento.

**Por que não Agent Teams**: Claude Code tem uma feature experimental de "Agent Teams"
(teammates com lista de tarefas compartilhada), mas ela não isola automaticamente cada
teammate em seu próprio worktree — ainda exigiria partição manual de arquivos — e tem
limitações documentadas (sem resume, shutdown lento, gated por variável de ambiente). Para um
processo que precisa ser confiável e auditável, `.claude/agents/*.md` + `git worktree` (já
documentado e usado no repo) cobre o mesmo objetivo sem depender de uma feature instável.

## Comunicação

Assíncrona, via o resultado escrito de cada agente (contrato, PR, veredito do Reviewer) — não
via reunião. Um agente que trava reporta o blocker no lugar onde o Lead vai procurar (resposta
da task, não um canal separado).

## Blockers

Um agente que encontra ambiguidade de contrato, decisão de produto ou dependência não
resolvida **para e reporta ao Lead** — não assume premissa silenciosamente (regra já em
[`AGENTS.md`](../../AGENTS.md)). O Lead decide se resolve, escala ao humano, ou ajusta a task.

## Modo dado real (quando as primeiras amostras chegarem)

Mesmo grafo de responsabilidades de sempre (ver tabela acima), com uma regra adicional
específica para dado real — ver `docs/data/PRIVACY_BOUNDARY.md` e
`docs/context/HUMAN_DECISIONS.md` para o contexto completo:

- **Domain Agent** revisa o mapeamento source→domínio e a lineage (`docs/data/SOURCE_CONTRACT_DIFF_TEMPLATE.md`,
  `docs/context/DATA_DEPENDENCIES.md`), nunca implementa o adapter.
- **AI Engineer** avalia compatibilidade do dado recebido com a extração/eval existente
  (`docs/data/DATA_QUALITY_REPORT.md`), nunca decide se o dado está autorizado.
- **Evaluator** revisa amostragem e qualidade de dado para o Golden Set
  (`docs/evals/GOLDEN_SET_SAMPLING.md`), nunca anota o golden set sozinho.
- **Reviewer** audita privacidade, escopo e correção — nunca aprova uso de dado sem
  autorização confirmada em `docs/context/HUMAN_DECISIONS.md`.

**Regra fixa: agents nunca recebem um dataset bruto mais amplo do que o necessário para a
tarefa.** Preferir sempre uma amostra pequena (as 5/3-5/20-50 de
`docs/data/REAL_DATA_REQUEST.md`) a passar o corpus completo para um agent processar de uma
vez — mesmo depois que o corpus completo estiver disponível. Isso não é infraestrutura de
RBAC (não implementamos controle de acesso automatizado) — é só disciplina de processo: o Lead
decide o que cada agent recebe, task por task, do mesmo jeito que já decide "Allowed files" em
`docs/agents/TASK_TEMPLATE.md`.

## Review e human-in-the-loop

Reviewer nunca faz merge. Toda mudança produzida por agente passa por PR e review humano antes
de entrar em `main` — isso já é regra do repositório (`WORKFLOW.md`), o Reviewer é uma camada
adicional *antes* do humano, não um substituto dele.
