# MVP Scope

## Primeiro milestone relevante

```
conversa → eventos estruturados → oportunidade/deal → outcome
```

Não é frontend, não é dashboard, não é copiloto realtime.

## Dentro do escopo agora

- Segurança e política de dados (nenhum dado real no Git — ADR-004).
- Normalização de transcrições em um schema canônico.
- Golden Set + taxonomia inicial (objeções, momentos, sinais de compra).
- Call Intelligence: extração estruturada a partir da call normalizada.
- Matching Call ↔ Deal (CRM).
- Outcome Intelligence: ligar comportamento de call a outcome de CRM.

## Fora de escopo por ora

- Ingestão real do Google Drive.
- Processamento das 143 calls reais.
- Escolha de banco de dados / storage definitivo.
- RAG semântico de produto (embeddings, vector DB). O braço experimental E2 (full-context
  knowledge augmentation, sem retrieval) existe só como experimento de avaliação.
- Agentes de vendas automatizados.
- Dashboard, frontend, Chrome Extension.
- API pública.
- Realtime Copilot (Cortex) — adiado até validação analítica do que funciona offline.
- Provedor de LLM definitivo (abstração sim — `ClassificationProvider`, ADR-005 —; hoje só Ollama
  local para experimento; escolha definitiva e provider cloud não).

Essas decisões, quando chegarem, entram via ADR (`docs/decisions/`).

## Gap analysis (reconciliado em 2026-09-29)

Comparação entre este escopo e o estado real do código (`docs/context/CURRENT_STATE.md`).
Escopo não foi redefinido para aumentar percentual concluído — o gap abaixo é real.

| Capability | MVP required? | Current status | Blocker | Next action |
|---|---|---|---|---|
| Segurança / política de dados | Sim | IMPLEMENTED — `.gitignore` defensivo, `data/README.md`, ADR-004, OCI privado provisionado (só smoke sintético), provider LLM local-only, artifacts privacy-first | Autorização de dado real (humano) | Manter disciplina; sign-off da política de storage antes do primeiro dado real |
| Normalização de transcrições (schema canônico) | Sim | IMPLEMENTED — `Call`/`Participant`/`TranscriptSegment`, IDs determinísticos | Nenhum de código | Validar contra fonte real (`docs/data/REAL_CALL_VALIDATION_KIT.md`) |
| Ingestão Agro real | Sim (implícito — sem ela não há call real) | PARTIAL — pipeline existe, nunca rodou contra dado real | Acesso ao corpus Agro | `docs/data/REAL_CALL_VALIDATION_KIT.md` |
| Golden Set + taxonomia inicial | Sim | PARTIAL — enum v0 no domínio; label set de anotação v0.1 (CIT-O1), protocolo, guideline v0.1 e calibration kit sintético escritos; nenhum gold real | Corpus real + anotadores (pilot D3) | Dry run do kit v0.1 → pilot D3 |
| Call Intelligence (extração estruturada) | Sim | PARTIAL — `ObjectionEvent` v0 + extractor rule-based; classifier LLM experimental E0/E1/E2 com Ollama local (compliance medida em dado sintético, qualidade **não** medida); momentos/sinais de compra sem contrato | Gold real para medir qualidade; D7 para contrato | Calibration Dataset Loader → pilot D3 → avaliação |
| Matching Call ↔ Deal (CRM) | Sim | PARTIAL — candidatos (`CallDealMatch`), relação atual autoritativa (`MatchDecision`, ADR-003) e identidade card → Deal (ADR-002) implementados; nunca rodou contra CRM real | Acesso Kommo + DI-G1–G4 | Kommo discovery quando houver acesso |
| Outcome canônico | Sim (pré-requisito de Outcome Intelligence) | PARTIAL — núcleo estrutural (ADR-001) + composição Call → match atual → outcome; policy real não implementada | D-G1/D-G2/D-G5/D-G6 | Decisões de negócio (Gabriel) |
| Outcome Intelligence | Sim | NOT STARTED — nenhuma agregação liga comportamento de call a outcome | Matching real + outcome canônico real | Bloqueado até Cadeia 3 de `docs/context/DATA_DEPENDENCIES.md` destravar |

Resumo: nenhuma capability do MVP está validada com dado real. Segurança e normalização não têm
gap de código; Call Intelligence, matching e outcome canônico têm contratos/núcleo implementados e
dependem de dado real, gold e decisões de negócio; Outcome Intelligence — o ponto de chegada do
milestone — não foi iniciado.
