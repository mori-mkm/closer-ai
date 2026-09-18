# Raw → Canonical Field Mapping Template

Template para mapear os campos de uma fonte real observada (Agro ou Empreende) para o schema
canônico, campo a campo. Diferente de
[`SOURCE_CONTRACT_DIFF_TEMPLATE.md`](SOURCE_CONTRACT_DIFF_TEMPLATE.md) — que compara um campo
já conhecido de `AgroRawCall` contra o que a fonte real mostrou — este template parte do lado
oposto: **de um campo bruto observado na fonte real (via structural profiler ou inspeção
manual) para o conceito canônico correspondente**, útil especialmente para uma fonte nova
(Empreende) onde ainda não existe nenhuma hipótese de `*RawCall` para comparar.

Não preencher baseado em hipótese — só depois de observar a amostra real
(`docs/data/REAL_CALL_VALIDATION_KIT.md`).

## Template

| Raw field | Meaning | Evidence | Canonical field | Transform | Confidence | Decision |
|---|---|---|---|---|---|---|

- **Raw field**: nome exato do campo na fonte observada (ex.: `meeting.uuid`, `host_email`).
- **Meaning**: o que o campo parece representar, com base em evidência, não suposição.
- **Evidence**: por que você acha que é isso — nome do campo, valor de exemplo estrutural (via
  `closer_ai.ingestion.profiling`, nunca o valor real em si), documentação do vendor, se houver.
- **Canonical field**: para onde isso mapeia em `Call`/`Participant`/`TranscriptSegment`
  (`src/closer_ai/normalization/models.py`), ou "N/A" se não há equivalente canônico hoje.
- **Transform**: conversão necessária (ex.: minutos → segundos, string ISO → `datetime`
  tz-aware), ou "nenhuma".
- **Confidence**: `high` (confirmado por múltiplas amostras/documentação), `medium` (plausível,
  1 amostra), `low` (suposição a validar).
- **Decision**: `map as-is`, `map with transform`, `defer — insufficient evidence`, ou `out of
  scope for Call` (ex.: um campo comercial que pertence a `Deal`, não a `Call`).

## Campos canônicos relevantes (referência, não preencher aqui)

`source`, `source_call_id` (→ `Call.source_id`), `started_at`/`occurred_at`, `ended_at` ou
`duration`, `participants` (lista), `participant external identity` (se existir — ver TD-01/
TD-02), `participant role`, `transcript segments`, `speaker mapping` (speaker label → participant
id), `segment timestamps` (`start_ts`/`end_ts`), `text`.

## Regra

Um mapeamento `high confidence` + `map as-is`/`map with transform` é o único tipo de linha que
justifica uma mudança real em `src/closer_ai/ingestion/agro/parser.py` (ou um novo adapter para
Empreende). Linhas `low confidence`/`defer` alimentam
[`docs/context/OPEN_QUESTIONS.md`](../context/OPEN_QUESTIONS.md), não o código.
