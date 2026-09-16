# Context Strategy

Princípio: **contexto mínimo suficiente > contexto máximo disponível.**

## Funil de leitura (nesta ordem, pare assim que tiver o suficiente)

```
AGENTS.md
    ↓
docs/context/CURRENT_STATE.md
    ↓
TASK (docs/agents/TASK_TEMPLATE.md)
    ↓
module docs (só o módulo referenciado pela task)
    ↓
código relevante (só "Allowed files" da task)
```

## Regras

- Use `rg`/busca seletiva antes de abrir arquivos grandes — nunca abra um arquivo só para
  "ver o que tem".
- Não leia `docs/` recursivamente. Não carregue todas as ADRs — só as referenciadas pela task.
- Não leia histórico completo do projeto para entender uma task pontual.
- Não abra datasets/transcrições completos para entender um schema — use uma amostra pequena
  ou fixture sintética (`tests/fixtures/`, `evals/datasets/`).
- Não duplique contexto em múltiplos documentos — linke (`ver docs/X.md`) em vez de copiar.
- Ao terminar, devolva um resumo curto ao orchestrator/humano — não o histórico bruto de
  ferramentas usadas.

## Por quê

Cada agent com contexto grande e difuso custa mais tokens, tem mais chance de tocar arquivo
fora de escopo, e é mais difícil de revisar. Task pequena + contexto hierárquico é o que
permite paralelismo real entre humanos e agents sem colisão.
