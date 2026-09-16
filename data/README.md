# data/

Este repositório é **público**. Nenhum dado real de cliente entra aqui — nunca.

Proibido versionar: transcrições, exports de CRM, nomes/telefone/e-mail de lead, gravações,
tokens, API keys, IDs identificáveis, ou output de LLM que contenha informação identificável.

`data/raw/`, `data/interim/` e `data/processed/private/` estão no `.gitignore` — use-os
localmente para dado real, eles nunca serão commitados.

Se um teste ou eval precisa de exemplo de call/CRM, use dado **sintético ou anonimizado**
apenas em `tests/fixtures/` ou `evals/datasets/` — nunca uma amostra real, mesmo pequena.
