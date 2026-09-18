# AI Closer

Sales Intelligence para operações comerciais high-ticket: transforma conversa (call) em
eventos estruturados, liga isso a oportunidades de CRM, e mede outcome.

## Estágio atual

Fase de validação. Sem produto em produção ainda. Prioridade atual:

```
segurança → normalização das calls → golden set + taxonomia → call intelligence → CRM matching
```

Realtime copilot, dashboard e frontend estão fora de escopo por ora — ver
[`docs/product/MVP_SCOPE.md`](docs/product/MVP_SCOPE.md).

## Arquitetura (alto nível)

```
conversa → eventos estruturados → oportunidade/deal → outcome
```

Detalhes em [`docs/architecture/ARCHITECTURE.md`](docs/architecture/ARCHITECTURE.md).

## Ambiente

```bash
pip install -e ".[dev]"
cp .env.example .env   # preencher localmente, nunca commitar
pytest
ruff check .
```

## Documentação

- [`AGENTS.md`](AGENTS.md) — contrato para qualquer coding agent
- [`CLAUDE.md`](CLAUDE.md) — específico para Claude Code
- [`docs/context/CURRENT_STATE.md`](docs/context/CURRENT_STATE.md) — estado técnico atual
- [`docs/`](docs/) — produto, arquitetura, domínio, decisões, workflow de agents

## Privacidade

Este repositório é **público**. Nenhum dado real de cliente (transcrições, exports de CRM,
nomes, telefones, e-mails, gravações) pode ser versionado aqui — ver
[`data/README.md`](data/README.md) e `.gitignore`.

## Como contribuir

Push direto em `main` é proibido. Todo trabalho entra por Pull Request a partir de uma
branch própria. Toda PR roda CI (Ruff + pytest) automaticamente — ver
[`docs/agents/WORKFLOW.md`](docs/agents/WORKFLOW.md).
