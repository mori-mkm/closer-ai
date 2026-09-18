# Agent Workflow

## Princípio

```
1 tarefa = 1 responsável = 1 branch = 1 worktree quando houver execução paralela
```

Nunca dois agents na mesma branch. Nunca dois agents editando os mesmos arquivos ao mesmo
tempo. Tasks devem ter fronteira de arquivos explícita (ver `TASK_TEMPLATE.md`).

Correto:
```
Agent A → parser AgroTalento (src/closer_ai/normalization/agrotalento.py)
Agent B → parser Empreende  (src/closer_ai/normalization/empreende.py)
Agent C → testes de normalização (tests/unit/normalization/)
```

Incorreto:
```
Agent A → "melhorar o pipeline"
Agent B → "melhorar o pipeline"
```
(sem fronteira de arquivo ou responsabilidade — conflito garantido)

## Branches

- Nunca push direto em `main` (exceto o commit de bootstrap inicial do repositório).
- Uma branch por task: `feat/call-parser`, `fix/crm-owner-id`, `chore/bootstrap-repository`.
- PR obrigatório para tudo. Squash merge é a estratégia padrão.
- Review humano obrigatório quando a mudança envolve arquitetura, schema, contratos,
  integrações, segurança, dado real, matching Call↔Deal, Outcome Intelligence, ou blast
  radius grande. Código de agent sempre passa por review humano.

## Worktrees (paralelismo real)

Um worktree por agent/tarefa em paralelo. Nunca dois agents no mesmo worktree.

PowerShell, a partir do diretório principal:

```powershell
cd C:\Users\mathe\Documents\projects\closer-ai

git fetch origin

git worktree add ..\closer-ai-call-parser `
  -b feat/call-parser main

git worktree add ..\closer-ai-crm-matching `
  -b feat/crm-matching main
```

Layout resultante:

```
closer-ai/                  → Matheus / integração
closer-ai-call-parser/      → Agent A
closer-ai-crm-matching/     → Agent B
```

Depois do merge do PR:

```powershell
git worktree remove ..\closer-ai-call-parser
git branch -d feat/call-parser
```

## CI

```
PR → CI (Ruff → pytest) → review humano → merge
```

`.github/workflows/ci.yml` roda em toda PR contra `main` (e em push em `main`, como
confirmação pós-merge): instala o package (`pip install -e ".[dev]"`, mesmo comando de
`README.md`), roda `ruff check .`, depois `pytest -q`. Sem secrets, sem dado real, sem rede
externa além de checkout/instalação de pacotes — os testes são hoje 100% herméticos.

**Merge só é permitido quando:**
- CI verde (`CI / test`);
- Ruff verde;
- pytest verde;
- review humano quando a mudança exigir (ver "Branches" acima);
- nenhum dado sensível no diff.

CI verde é necessário, não suficiente — não substitui o review humano nos casos já listados em
"Branches".

## Commits

Conventional Commits.

Tipos: `feat fix refactor test docs chore perf ci`
Scopes: `calls crm data domain ai analytics experiments integrations api infra docs`

```
feat(calls): add canonical transcript model
fix(crm): handle missing owner id
docs(domain): define opportunity lifecycle
chore(repo): bootstrap project structure
```

Evitar: `update`, `changes`, `fix stuff`, `wip final`.
