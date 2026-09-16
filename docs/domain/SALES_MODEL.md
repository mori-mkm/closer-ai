# Sales Model

Como o domínio de vendas high-ticket é modelado no produto — a base para `domain/` e para o
schema de extração de `ai/`.

## Premissa

O produto não avalia closers isoladamente. Com poucos closers por operação (n pequeno), o
sinal estatístico não vem de ranquear pessoas — vem de comparar **calls e momentos** entre
si. Ranking de vendedor com n baixo é uma conclusão não suportada pelo dado.

## Ciclo de vida de uma oportunidade

```
Lead entra → Stage inicial → 1+ Calls → Objections/Signals/Risks por call → Stage avança/regride → Outcome
```

## O que qualifica como Outcome

Resultado final do Deal (ganho/perdido) + métricas de processo (ciclo, número de calls até
fechar). Definição exata do outcome é decisão de produto, não deve ser assumida
silenciosamente pelo código — ver `docs/context/OPEN_QUESTIONS.md` se ainda em aberto.

## Relação com Data Model

Este documento descreve o domínio; `docs/architecture/DATA_MODEL.md` descreve como isso vira
estrutura de dados conceitual.
