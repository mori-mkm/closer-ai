# MVP Scope

## Primeiro milestone relevante

```
conversa → eventos estruturados → oportunidade/deal → outcome
```

Não é frontend, não é dashboard, não é copiloto realtime.

## Dentro do escopo agora

- Segurança e política de dados (nenhum dado real no repo público).
- Normalização de transcrições em um schema canônico.
- Golden Set + taxonomia inicial (objeções, momentos, sinais de compra).
- Call Intelligence: extração estruturada a partir da call normalizada.
- Matching Call ↔ Deal (CRM).
- Outcome Intelligence: ligar comportamento de call a outcome de CRM.

## Fora de escopo por ora

- Ingestão real do Google Drive.
- Processamento das 143 calls reais.
- Escolha de banco de dados / storage definitivo.
- RAG.
- Agentes de vendas automatizados.
- Dashboard, frontend, Chrome Extension.
- API pública.
- Realtime Copilot (Cortex) — adiado até validação analítica do que funciona offline.
- Provedor de LLM definitivo (abstração sim, escolha definitiva não).

Essas decisões, quando chegarem, entram via ADR (`docs/decisions/`).
