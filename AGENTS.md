# AGENTS.md

Contrato geral para qualquer coding agent (Claude, Codex, outros) trabalhando neste repo.
Regras invariantes — não é histórico do projeto, não é tutorial.

## Antes de começar

1. Leia `docs/context/CURRENT_STATE.md`.
2. Leia a task recebida (`docs/agents/TASK_TEMPLATE.md` define o formato).
3. Leia só a documentação de módulo referenciada pela task.
4. Leia só os arquivos de código listados em "Allowed files" da task.

Não leia o repositório inteiro. Não leia todas as ADRs. Não leia `docs/` recursivamente.
Detalhes do funil de contexto: `docs/agents/CONTEXT_STRATEGY.md`.

## Regras invariantes

- Respeite o escopo da task. Não edite arquivos fora de "Allowed files" sem justificar.
- Não tome decisão arquitetural relevante sozinho — proponha via ADR (`docs/decisions/`) e
  pare para revisão humana.
- Não altere schema, contrato de API ou modelo de dados silenciosamente.
- Execute os testes relacionados à mudança antes de reportar como pronta.
- Nunca acesse, leia ou versione dados reais de cliente (transcrições, exports de CRM, PII).
  Use apenas fixtures sintéticas (`tests/fixtures/`, `evals/datasets/`).
- Se travar (dado faltando, decisão ambígua, dependência não resolvida), reporte o blocker —
  não invente premissa silenciosamente.
- Atualize documentação apenas quando o estado real do sistema mudou, não como padrão.
- Nunca faça merge de PR.
- Nunca dê push direto na `main`, nunca force push.
- Uma task = um responsável = uma branch. Nunca dois agents na mesma branch ou worktree.
