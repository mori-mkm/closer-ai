# Agro Ingestion Contract v0

Contrato do pipeline de ingestão Agro/Zoom — `src/closer_ai/ingestion/agro/`. Não é o
schema canônico (`docs/architecture/DATA_MODEL.md` / `src/closer_ai/normalization/models.py`,
que não é alterado por este módulo) — é a camada de fronteira entre o dado bruto da fonte
Agro/Zoom (formato ainda hipotético) e o `normalize_call()` já existente.

## Current assumptions

Tudo abaixo é hipótese própria, não confirmada contra dado real (não há corpus Agro/BeefPoint
disponível localmente — ver `docs/context/CURRENT_STATE.md`):

- Formato de origem (`AgroRawCall`) ainda não confirmado contra nenhum export real do Zoom/Agro.
- Unidade de `duration_seconds` assumida já em segundos — a API real do Zoom costuma retornar
  duração em minutos; não convertida aqui.
- Identidade de participante assumida via nome/label normalizado (`_slugify`), não via um id
  estável da fonte (Zoom participant UUID, e-mail) — ver "Known limitations".
- Formato exato do transcript (`speaker`/`start`/`end`/`text` por entrada) não confirmado —
  pode ser `.vtt`, `.srt`, JSON de API, ou outra coisa.
- Corpus real (108 calls Beefpoint/AgroTalento) ainda não processado por este pipeline.

## What this implementation DOES NOT claim

- Não representa o formato oficial da API do Zoom.
- Não processou nenhuma das 108 calls reais.
- Não foi validado em produção.
- Não resolve identidade comercial (CRM, lead, deal) — isso é `integrations/`/matching futuro,
  fora de escopo aqui.
- Não associa call a deal (`Call ↔ Deal` é uma fase futura do roadmap).

## Arquitetura

```
raw source (formato real ainda desconhecido)
    ↓
source adapter (a escrever quando o formato real for conhecido)
    ↓
AgroRawCall                    (boundary model — shape da fonte, não um segundo Call)
    ↓
parse_agro_call()
    ↓
AgroParseResult.raw_input      (dict compatível com normalize_call())
    ↓
normalize_call()               (não alterado por este módulo)
    ↓
Call                           (canônico, não alterado por este módulo)
```

`AgroRawCall` não compete com `Call`: tem campos soltos e opcionais (`participants`/`transcript`
como `list[dict[str, Any]]` não tipados, `closer` como label livre) e nenhum dos invariantes
fortes do canônico (frozen, IDs determinísticos, `segment_index` contíguo). Revisão de
arquitetura (Domain Agent, 2026-09-17): PASS com uma ressalva de severidade média, não
bloqueante — ver "Known limitations".

## Contrato de input (`AgroRawCall`)

| Campo | Tipo | Obrigatório? | Default | Validação | Recuperável? | Erro/flag gerada | Destino no Canonical Call | Hipótese não validada com dado real? |
|---|---|---|---|---|---|---|---|---|
| `meeting_id` | `str` | sim | — | não-branco (`.strip()`) | não | branco/ausente → `AgroParseError` | `Call.source_id` | SIM — shape do id real do Zoom |
| `topic` | `str \| None` | não | `None` | — | sim | ausente → `metadata_incomplete` | `AgroParseResult.metadata["topic"]` (fora do canônico) | SIM |
| `occurred_at` | `datetime \| None` | sim (não pode ser `None`) | `None` | deve ter `tzinfo` | não | ausente/naive → `AgroParseError` | `Call.occurred_at` | SIM — fonte real do timestamp/timezone |
| `duration_seconds` | `float \| None` | não | `None` | `> 0` quando presente | `None` → sim; `<=0` → não | `None` → `missing_duration` (estimado via `max(end_ts)`); `<=0` → `AgroParseError` | `Call.duration_seconds` | **SIM — unidade real não confirmada (segundos vs. minutos)** |
| `transcript_source` | `str \| None` | não | `None` | — | sim | ausente → `metadata_incomplete` | `AgroParseResult.metadata["transcript_source"]` (fora do canônico) | SIM |
| `zoom_summary` | `str \| None` | não | `None` | — | sim | ausente → `metadata_incomplete` | `AgroParseResult.metadata["zoom_summary"]` (fora do canônico) | SIM |
| `closer` | `str \| None` | não | `None` | deve resolver (por slug) a um participante com role `unknown`/`closer` | sim | ausente → nada; presente e não resolvido (ou resolvido a alguém com role conflitante) → `metadata_incomplete`, `closer_id=None` | `Call.closer_id` | SIM |
| `participants[].label\|name\|id` | `str` (dentro de `dict[str, Any]`) | não (lista toda opcional) | — | precisa ser string não-branca | sim | ausente/vazia/tipo errado → `missing_participants` (se a lista toda ficar vazia) | `Call.participants[].id/name` | SIM |
| `participants[].role` | `str` (dentro de `dict[str, Any]`) | não | `"unknown"` | validado só no `Call` (`Literal`), não aqui | parcialmente | valor fora do `Literal` → `AgroParseError` (via `normalize_call()`, rede de segurança) | `Participant.role` | SIM |
| `transcript[].speaker` | `str` (dentro de `dict[str, Any]`) | não | — | precisa ser string não-branca | sim | ausente/tipo errado → `unresolved_speaker`, atribuído a `unknown_speaker` | `TranscriptSegment.speaker_id` | SIM |
| `transcript[].start`/`.end` | `int \| float` | não | — | `end > start` | sim | ausente/tipo errado → `missing_timestamp`; `end<=start` → `transcript_parse_error` (entrada descartada) | `TranscriptSegment.start_ts/end_ts` | SIM |
| `transcript[].text` | `str` | não | — | não-branco | sim | ausente/vazio/tipo errado → `transcript_parse_error` (entrada descartada) | `TranscriptSegment.text` | SIM |
| `metadata` | `dict[str, Any] \| None` | não | `None` | passthrough, sem validação | sim | — | `AgroParseResult.metadata["raw_metadata"]` (fora do canônico) | SIM |
| campos top-level desconhecidos | — | — | — | ignorados (pydantic default) | sim | nenhuma flag — escolha deliberada, ver nota abaixo | descartados | N/A |

Nota sobre campos desconhecidos: `AgroRawCall` não usa `extra="forbid"` — de propósito. O
formato real do Zoom/Agro vai trazer campos que não modelamos ainda; rejeitar tudo que não
reconhecemos tornaria o parser frágil contra o primeiro export real, exatamente o oposto do
objetivo desta camada. `test_parse_agro_call_ignores_unknown_top_level_fields` trava esse
comportamento como intencional.

## Quality flags contract

| Flag | Condição exata | Recuperável? | Impacto no Canonical Call | Pode coexistir com | Exemplo sintético | Origem vs. interpretação |
|---|---|---|---|---|---|---|
| `missing_transcript` | `transcript` ausente (`None`) | não (força `AgroParseError` de "zero segmentos") | nenhum — call nunca chega a existir | não coexiste (função retorna cedo) | `agro_raw_call_missing_transcript()` | problema de origem |
| `empty_transcript` | `transcript` presente mas vazio, ou todas as entradas descartadas no parse | não (idem) | nenhum | `missing_timestamp`, `transcript_parse_error` (quando o motivo foi descarte total) | `agro_raw_call_empty_transcript()` | origem ou interpretação, depende do caso |
| `missing_participants` | `participants` ausente/vazio, OU nenhuma entrada tinha label utilizável | sim — reconstruído a partir dos `speaker` do transcript | nenhum direto; participantes acabam todos com role inicial `unknown` | `unresolved_speaker` (quase sempre junto) | `agro_raw_call_missing_participants()` | problema de origem |
| `unresolved_speaker` | um `speaker` de transcript não bate com nenhum participante conhecido (ausente, tipo errado, ou label novo) | sim — vira participante placeholder `role="unknown"` | segmento existe, mas `speaker_id` aponta a alguém sem role definido | `missing_participants`, `participant_id_collision` | `agro_raw_call_unresolved_speaker()` | ambos — depende se veio de dado ausente ou de fato um novo speaker |
| `missing_timestamp` | entrada de transcript sem `start`/`end` numérico | sim — entrada descartada (schema exige os dois; sem eles não há como representar sem fabricar) | segmento não existe no `Call` — texto é perdido, mas a flag documenta que a perda ocorreu | `transcript_parse_error`, `empty_transcript` | `agro_raw_call_inconsistent_timestamps()` | origem |
| `missing_duration` | `duration_seconds` ausente (`None`) | sim — estimado via `max(end_ts)` dos segmentos válidos | `Call.duration_seconds` é uma estimativa, não o valor real da fonte | `duration_mismatch` (do `normalize_call()`, se a estimativa por acaso não bater — improvável já que é o próprio máximo) | `agro_raw_call_inconsistent_timestamps()` | origem |
| `transcript_parse_error` | entrada de transcript não é mapping, `text` ausente/vazio/tipo errado, ou `end<=start` | sim — entrada descartada | idem `missing_timestamp` | `missing_timestamp`, `empty_transcript` | `agro_raw_call_inconsistent_timestamps()` | origem |
| `metadata_incomplete` | `topic`/`transcript_source`/`zoom_summary` ausente, OU `closer` informado mas não resolvido (ou resolvido a alguém com role conflitante) | sim — puramente informativo | nenhum | qualquer outra | `agro_raw_call_incomplete_metadata()` | origem |
| `participant_id_collision` | dois labels de origem diferentes (participants entre si, ou transcript vs. participants) normalizam para o mesmo `_slugify()` | sim — o primeiro registrado "vence", o resto é só sinalizado | um participante da fonte pode desaparecer/ter sua fala misatribuída ao vizinho — ver "Known limitations" | `unresolved_speaker` | ver teste `test_parse_agro_call_participant_slug_collision_is_flagged_not_silent` | interpretação (limitação do próprio esquema de id) |

Duas flags foram auditadas e achadas **não** escondendo dois estados semanticamente diferentes
sob o mesmo nome, apesar de suspeita inicial:
- `metadata_incomplete` cobre "descrição ausente" (topic/zoom_summary/transcript_source) e
  "closer não resolvido" — são heterogêneos, mas ambos têm o mesmo impacto operacional real
  (nenhum, são informativos) e a mesma ação de triagem (nenhuma ação automática possível,
  revisão manual se necessário). Não separados em duas flags para não inflar o contrato sem
  ganho prático.
- `closer` ausente (`None`) **não** dispara `metadata_incomplete` — só `closer` informado e não
  resolvido dispara. Ver `test_parse_agro_call_closer_none_does_not_flag_metadata_incomplete_on_its_own`.

## Known limitations

- **Colisão de id de participante** (`participant_id_collision`): a identidade de participante
  é derivada só do nome/label normalizado (`_slugify` — NFKD, minúsculas, ascii). Dois nomes
  que normalizam igual (ex. "João Silva" vs. "Joao Silva", ou diferença só de maiúsculas/
  espaços) colidem no mesmo id. A partir desta rodada de hardening, a colisão é **sinalizada**
  (flag), não mais silenciosa — mas ainda **funde** os dois participantes em um só (o primeiro
  registrado). Resolver isso de verdade (manter os dois como pessoas distintas) exigiria um id
  estável da fonte real (Zoom participant UUID, e-mail, ...) que não existe no formato
  hipotético atual — não inventado aqui de propósito, conforme instrução do Lead. Revisitar
  quando o formato real do Zoom for confirmado.
- **Invariantes duplicados entre `parser.py` e `normalization/models.py`** (achado do Domain
  Agent, severidade média, não bloqueante): `end>start`, texto não-vazio, `occurred_at`
  tz-aware, e `duration_seconds>0` são checados manualmente em `parser.py` *e* de novo pelos
  validators do `Call`/`TranscriptSegment`. Isso é intencional (o parser precisa decidir
  "descarta e sinaliza" vs. "erro fatal" *antes* de chegar em `normalize_call()`, não dá pra
  delegar 100%), mas cria duas fontes de verdade para a mesma regra — se `models.py` mudar uma
  dessas regras, nada aqui vai quebrar automaticamente em teste, só vai divergir em silêncio.
  Não vale extrair agora (uma única fonte, YAGNI); revisitar quando a segunda fonte de ingestão
  (Empreende Brazil) for construída.
- **`_slugify`/`_add_flag` são privados a este módulo** — quando a segunda fonte de ingestão
  precisar do mesmo comportamento, o caminho mais provável hoje é copiar/colar em vez de
  importar. Não é bloqueio agora (só existe uma fonte), só um ponteiro para quando isso mudar.
- **`AgroParseResult.quality_flags` duplica `raw_input["quality_flags"]`** dentro do mesmo
  objeto de retorno — redundância de baixo risco, não vale uma mudança de shape do dataclass
  agora só por estética.
- Texto de entradas de transcript descartadas (`missing_timestamp`/`transcript_parse_error`)
  **não é preservado** em lugar nenhum — a flag documenta que algo foi perdido, mas não o quê.
  Aceitável para o vertical slice sintético; para o corpus real, uma melhoria futura razoável
  seria preservar as entradas descartadas em `AgroParseResult.metadata` para triagem manual.

## Rastreabilidade

O que já é possível responder hoje, sem armazenar PII:

1. De qual source veio a call → `Call.source` (`"agro_zoom"` por padrão).
2. Qual meeting/source_id originou o `call_id` → `Call.source_id` = `meeting_id`, mais
   `AgroParseResult.metadata["meeting_id"]` (cópia redundante do lado do pipeline).
3. Quais warnings ocorreram durante o parse → `AgroParseResult.quality_flags` (== `Call.quality_flags`).
4. Qual input intermediário foi enviado a `normalize_call()` → `AgroParseResult.raw_input`.
5. Qual metadata foi preservada fora do canônico → `AgroParseResult.metadata` (topic,
   transcript_source, zoom_summary, `raw_metadata` passthrough).
6. Em caso de erro, qual call falhou, sem PII → toda mensagem de `AgroParseError` inclui só
   `meeting_id` (nunca conteúdo de transcript ou o payload bruto). A exceção de validação de
   shape (`AgroRawCall.model_validate()`) foi corrigida nesta rodada para citar só os campos
   que falharam (`exc.errors()[].loc`), nunca `str(exc)` — que ecoaria o valor rejeitado e uma
   URL de documentação do pydantic.

`meeting_id` é tratado como identificador operacional seguro para logs (não é nome/e-mail/
telefone) — mas é uma suposição sobre o formato real, não confirmada.
