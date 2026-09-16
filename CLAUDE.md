# CLAUDE.md

Regras gerais de agent: ver [`AGENTS.md`](AGENTS.md) — leia esse arquivo primeiro, sempre.

Este arquivo é só o específico de Claude Code.

## Funil de contexto (obrigatório)

```
AGENTS.md → docs/context/CURRENT_STATE.md → task → docs do módulo → código relevante
```

Use `rg` para localizar antes de abrir arquivos. Não leia `docs/` inteiro, não leia datasets
completos, não abra transcrições. Detalhes: `docs/agents/CONTEXT_STRATEGY.md`.

## Comandos principais

```bash
pip install -e ".[dev]"
pytest                 # testes
pytest tests/unit      # só unitários
ruff check .            # lint
```

## Delegação para subagents

Um subagent = uma task pequena e verificável, com escopo de arquivos explícito
(`docs/agents/TASK_TEMPLATE.md`). Não delegue "melhore o pipeline" sem fronteira. Para
paralelismo real (Matheus, Otávio e agents ao mesmo tempo), use `git worktree` — um worktree
por tarefa, nunca compartilhado. Ver `docs/agents/WORKFLOW.md`.

## Git

Branch por task, PR obrigatório, squash merge. Nunca push direto em `main` (exceto o bootstrap
inicial do repositório, já feito). Conventional Commits — ver `docs/agents/WORKFLOW.md`.
