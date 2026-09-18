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

## Gap analysis (2026-09-18)

Comparação entre este escopo e o estado real do código (`docs/context/CURRENT_STATE.md`).
Escopo não foi redefinido para aumentar percentual concluído — o gap abaixo é real.

| Capability | MVP required? | Current status | Blocker | Next action |
|---|---|---|---|---|
| Segurança / política de dados | Sim | IMPLEMENTED — `.gitignore` defensivo, `data/README.md`, nenhum dado real versionado | Nenhum | Manter disciplina; revisitar se um novo tipo de dado sensível aparecer |
| Normalização de transcrições (schema canônico) | Sim | IMPLEMENTED — `Call`/`Participant`/`TranscriptSegment`, IDs determinísticos | Nenhum de código | Validar contra fonte real (ver TRACK A) |
| Ingestão Agro real | Sim (implícito — sem ela não há call real) | PARTIAL — pipeline existe, nunca rodou contra dado real | Acesso ao corpus Agro | `docs/context/NEXT_7_DAYS.md` A1, A5 |
| Golden Set + taxonomia inicial | Sim | PARTIAL — taxonomia v0 (4 categorias) implementada; Golden Set é 100% sintético (9 exemplos), não a amostra real do MVP | Corpus real + anotadores | `docs/context/NEXT_7_DAYS.md` B1, B2 |
| Call Intelligence (extração estruturada) | Sim | PARTIAL — só `ObjectionEvent` existe; momentos/sinais de compra do MVP scope não têm contrato ainda | Nenhum de dado — é trabalho de domínio ainda não feito | Desenhar contrato de Moment/Buying Signal quando houver sinal do Golden Set real sobre o que vale a pena extrair |
| Matching Call ↔ Deal (CRM) | Sim | PARTIAL — contrato + 1 matcher determinístico existem; nunca rodou contra CRM real | Acesso Kommo | `docs/context/NEXT_7_DAYS.md` A4 |
| Outcome Intelligence | Sim | NOT STARTED — nenhum código liga comportamento de call a outcome de CRM ainda | Depende de Matching real + `analytics/` (vazio) | Bloqueado até Cadeia 3 de `docs/context/DATA_DEPENDENCIES.md` destravar |

Resumo: das 7 capabilities de escopo do MVP, 2 estão implementadas e validadas
(sem dado real, mas sem gap de código), 4 estão parcialmente implementadas e bloqueadas por
dado real ou trabalho de domínio ainda não feito, e Outcome Intelligence — o ponto de chegada
do milestone — não foi iniciado porque depende de todas as anteriores.
