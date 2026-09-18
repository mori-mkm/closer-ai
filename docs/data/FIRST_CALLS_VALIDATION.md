# First 5 Calls Validation Protocol

Protocolo passo a passo para validar as primeiras 5 calls reais do Agro contra
`AgroRawCall`/`parse_agro_call()` (`src/closer_ai/ingestion/agro/`). Esta task **não**
implementa adapter — o protocolo abaixo é manual/exploratório, produz um relatório e uma
proposta de mapeamento, não código.

Pré-requisito: as 5 calls já estão em `data/raw/agro/` (nunca no Git — ver
`docs/data/PRIVACY_BOUNDARY.md`), obtidas via `docs/data/REAL_DATA_REQUEST.md` Package A.

## Etapas

1. **Inventory raw files** — listar os arquivos recebidos por call (um transcript? metadata
   separada? tudo num JSON só?).
2. **Identify file formats** — `.vtt`, `.srt`, `.txt`, JSON de API, outro. Anotar por call
   (podem vir formatos diferentes entre as 5).
3. **Inspect encoding** — UTF-8 confirmado? Caracteres acentuados (português) preservados
   corretamente?
4. **Inspect metadata** — o que existe fora do transcript: meeting id, data, duração, tópico,
   link de gravação?
5. **Inspect transcript representation** — é uma lista de entradas (speaker + texto +
   timestamps), um bloco de texto corrido, ou outra estrutura?
6. **Identify meeting id** — qual campo/valor serve como `source_id` estável para
   `derive_call_id()` (`src/closer_ai/normalization/ids.py`)?
7. **Identify datetime/timezone** — a data/hora da call vem com timezone explícito?
   `Call.occurred_at` exige tz-aware (`src/closer_ai/normalization/models.py`).
8. **Identify duration unit** — segundos ou minutos? (`AgroRawCall.duration_seconds` assume
   segundos, não confirmado — `docs/domain/AGRO_INGESTION_CONTRACT.md`.)
9. **Identify participants** — existe uma lista de participantes separada do transcript, ou só
   labels de speaker dentro do transcript?
10. **Identify speaker labels** — como cada fala é atribuída (nome, "Speaker 1", email, id)?
11. **Identify stable participant identifiers** — existe algo além do nome (Zoom participant
    UUID, email)? Esta é a pergunta mais importante para resolver TD-01/TD-02
    (`docs/context/TECH_DEBT.md`) — identidade hoje é só nome normalizado.
12. **Identify closer** — como saber quem, entre os participantes, é o closer? Campo
    explícito, ou inferência (quem fala mais, quem está na lista de usuários do CRM)?
13. **CRÍTICO — confirmar resolução de `role="lead"` ponta a ponta.** `RuleBasedObjectionExtractor`
    (`src/closer_ai/ai/objection_extraction.py`) só escaneia segmentos cujo `speaker_id`
    resolve a um participante com `role="lead"` — qualquer outro role (incluindo `"unknown"`)
    é ignorado silenciosamente. O parser atual (`src/closer_ai/ingestion/agro/parser.py`) tem
    resolução de `closer` (`_resolve_closer`), mas **nenhuma resolução equivalente para
    `"lead"`** — todo participante que não é o closer fica `role="unknown"` a menos que o
    `role` já venha explicitamente como `"lead"` no `participants[]` bruto da fonte (hipótese
    não confirmada). Sem essa confirmação, a call inteira produz `Call` válido mas **zero
    objeções**, sempre, mesmo que o transcript tenha objeções óbvias — falha silenciosa, sem
    nenhum erro ou flag. Verificar explicitamente, para cada uma das 5 calls: o participante
    não-closer chega a `role="lead"` depois do parser rodar? Se não, isso é bloqueador para
    qualquer avaliação do extractor contra dado real — não é um ajuste cosmético.
14. **Determine whether transcript timestamps are absolute or relative** — `start`/`end` de
    cada entrada são segundos desde o início da call, ou timestamps absolutos (data+hora)?
    `TranscriptSegment.start_ts`/`end_ts` (`normalization/models.py`) assume relativo ao início
    da call.
15. **Identify missing fields** — o que `AgroRawCall` espera e não está presente em nenhuma das
    5 calls?
16. **Compare against `AgroRawCall` assumptions** — usar
    `docs/data/SOURCE_CONTRACT_DIFF_TEMPLATE.md`, um diff por campo relevante.
17. **Create adapter mapping proposal** — documento (não código) propondo como cada campo real
    mapeia para `AgroRawCall`, incluindo qualquer transformação necessária (ex.: conversão de
    minutos para segundos, se confirmado no passo 8).
18. **Run manually on 1 call** — simular `parse_agro_call()` mentalmente/manualmente contra a
    proposta de mapeamento em 1 call; confirmar que produziria um `Call` válido **e** que o
    participante não-closer chegaria a `role="lead"` (passo 13) — ou identificar onde quebraria.
19. **Run on 5** — repetir para as 5 calls.
20. **Produce quality report** — usar `docs/data/DATA_QUALITY_REPORT.md` (seção Agro): quantas
    das 5 produziriam `Call` válido, quais `quality_flags` apareceriam, quais falhariam e por
    quê. Incluir explicitamente quantas produziriam pelo menos um participante `role="lead"`.
21. **Review before batch** — antes de processar as 108, revisar o relatório de qualidade e o
    mapeamento proposto com Product/RevOps + AI/Backend Lead; só então abrir a branch de
    implementação real (ver "Exact next engineering trigger" no relatório de reconciliação).

## Known limitation a considerar na leitura das 5 calls

`RuleBasedObjectionExtractor` usa uma lista fixa de palavras/frases em português formal
(`_KEYWORDS` em `src/closer_ai/ai/objection_extraction.py`) — não tem tolerância a erro de
transcrição automática (ASR), variação regional, ou gíria específica do agronegócio para
objeções de preço/tempo. Ao ler as 5 calls reais, anotar informalmente se a linguagem real se
afasta muito do português formal assumido — isso não é um bug a corrigir aqui, é um limite
conhecido do extractor v0 a levar para `docs/evals/GOLDEN_SET_SAMPLING.md` quando a avaliação
real acontecer.

## O que este protocolo NÃO faz

Não implementa `agro_adapter.py`, não altera `AgroRawCall`/`parse_agro_call()`, não roda código
real de ingestão. É exploração manual — planilha, notas, ou um notebook local (fora do Git,
`data/interim/agro/` se algum output intermediário for gerado) até o passo 20 produzir um
relatório documentável.
