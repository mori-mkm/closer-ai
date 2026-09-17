# Objection Model v0

Contrato de `ObjectionEvent` — o primeiro sub-item de `Call` (ver `docs/architecture/DATA_MODEL.md`)
a virar schema. Implementação: `src/closer_ai/domain/objection.py`.

## O que é

Um `ObjectionEvent` é evidência estruturada de que o lead expressou resistência (ver
`docs/domain/GLOSSARY.md` — "Objection") em um ponto específico de uma `Call` já normalizada.
Ele não duplica texto de transcrição: aponta para o segmento de origem via `call_id` +
`segment_id` (`closer_ai.normalization.Call` / `TranscriptSegment`). Essa referência é o
"evidence span" desta v0 — o segmento inteiro, não um trecho de caracteres dentro dele (ver
"Edge cases" abaixo).

## Campos

| Campo | Tipo | Por quê |
|---|---|---|
| `schema_version` | `str` (default `"1.0.0"`) | mesma prática de `Call.schema_version` — o contrato vai evoluir (taxonomia mais ampla, Deal/Outcome) e versão explícita evita quebra silenciosa de leitores futuros. |
| `objection_id` | `str` | id determinístico — ver "IDs e dedup" abaixo. Permite idempotência (re-rodar extração não duplica linha) e é a chave de dedup entre execuções. |
| `call_id` | `str` | rastreia até a `Call` de origem (`closer_ai.normalization.Call.call_id`). Não validado contra uma `Call` real aqui — isso é responsabilidade de quem constrói o evento (extractor/eval), que tem a `Call` completa em mãos; um `ObjectionEvent` isolado não consegue fazer lookup cruzado. |
| `segment_id` | `str` | rastreia até o `TranscriptSegment` de origem dentro dessa call. Mesma observação: integridade referencial cross-object é responsabilidade de quem constrói/valida o evento, não do modelo isolado. |
| `category` | `Literal["price", "timing_priority", "trust_authority", "no_need", "other"]` | taxonomia pequena e explícita, conforme os blockers da task (`docs/agents/tasks/objection-event-v0.md`). `other` é a válvula de escape para não forçar um registro inválido quando a objeção real não cabe nas quatro categorias nomeadas; taxonomia completa é uma task futura (`docs/product/ROADMAP.md`, fase 3). |

Campos deliberadamente **fora** desta v0 (ver "Edge cases" para o porquê de cada um):
`raised_by`/`speaker_role`, `confidence`, texto/quote bruto, `severity`, referência a
`Deal`/`Outcome`, resolução/estratégia.

## IDs e dedup

`objection_id` é derivado de `(call_id, segment_id, category)` com a mesma técnica de
`closer_ai.normalization.ids` (sha256 sobre `json.dumps` de uma lista — delimitação
inequívoca de elementos, sem PII na entrada). `derive_objection_id()` está em
`src/closer_ai/domain/objection.py`; o `model_validator` do `ObjectionEvent` recusa um id que
não bata com essa derivação.

Essa derivação também define a regra de deduplicação:

- Mesma categoria detectada de novo **no mesmo segmento** → mesmo `objection_id` (idempotente:
  re-rodar a extração não cria linha duplicada para a mesma menção).
- Mesma categoria detectada **em outro segmento** → `objection_id` diferente, é um evento
  novo. Isso é intencional: o lead repetir a mesma objeção mais tarde na call é sinal (ela não
  foi resolvida), e o modelo precisa conseguir representar isso.
- Categorias diferentes no mesmo segmento (ex.: "tá caro e eu não tenho tempo agora") →
  dois eventos, ids diferentes (o componente `category` difere).

## Invariantes

- Imutável (`ConfigDict(frozen=True)`), como `Call`/`TranscriptSegment`.
- `call_id` e `segment_id` não podem ser strings vazias.
- `category` restrito ao enum fechado acima (Pydantic recusa qualquer outro valor).
- `objection_id` deve bater com `derive_objection_id(call_id, segment_id, category)` — ver
  acima.

## Edge cases considerados e rejeitados

- **Evidência multi-segmento (lista de `segment_id`, ou span com offsets de caractere).**
  Rejeitado para v0. Um único `segment_id` obrigatório mantém o "evidence grounding" como um
  lookup mecânico único (`(call_id, segment_id)` resolve para um segmento real?), que é o que
  a métrica de grounding do harness de avaliação precisa. A maioria das objeções explícitas
  cabe em um turno só; span multi-turno fica para quando o golden set mostrar que um segmento
  não basta.
- **`raised_by`/`speaker_role` no evento.** Rejeitado. Quem falou já é resolvível via
  `Call.segments[i].speaker_id -> Call.participants` para o segmento referenciado — duplicar
  isso aqui criaria uma segunda fonte de verdade que pode divergir da `Call` que o evento
  aponta. Além disso, por definição de domínio (`GLOSSARY.md`) uma objeção é expressa pelo
  lead; não há variação a capturar em v0.
- **`confidence`.** Rejeitado por agora. A implementação de referência do extractor (fora do
  escopo deste agente) é determinística por regra/keyword — teria confiança constante, sem
  sinal real. Reintroduzir quando um extractor probabilístico/LLM existir.
- **Texto bruto / quote da objeção no evento.** Rejeitado por design: duplicaria a
  transcrição (que já vive em `TranscriptSegment.text`) e criaria risco de inconsistência se o
  segmento de origem mudar de representação. A referência `(call_id, segment_id)` já é
  suficiente para qualquer consumidor buscar o texto na `Call`.
- **`severity`/intensidade da objeção.** Rejeitado: especulativo para v0, sem uso imediato
  definido nem no golden set nem no eval harness desta fase.
- **Objeções repetidas no mesmo segmento (mesma categoria).** Não é um caso rejeitado, é um
  comportamento definido: colapsa para o mesmo `objection_id` (ver "IDs e dedup"). Não há
  necessidade de um campo de contagem/ocorrência em v0.
- **Validar que `segment_id` pertence de fato a `call_id`, ou que o `speaker_id` do segmento
  é `role="lead"`.** Rejeitado no nível do modelo: `ObjectionEvent` não carrega a `Call`
  inteira, só os ids — checagem cruzada exigiria passar o objeto `Call` para o validador, o
  que acoplaria este contrato a `normalization` de um jeito que a task explicitamente evita
  ("não duplicar, referenciar"). Essa integridade fica com quem constrói/avalia o evento
  (extractor e eval harness), que têm a `Call` completa disponível.

## Fora de escopo (deferred)

`ObjectionEvent` **não** referencia `Deal` nem `Outcome` nesta v0 — decisão intencional, ver
`docs/product/MVP_SCOPE.md` ("Matching Call ↔ Deal" e "Outcome Intelligence" são fases
futuras) e os blockers de `docs/agents/tasks/objection-event-v0.md`. Também não modela
`Strategy` (como o closer reagiu à objeção) — isso é um sub-item irmão de `Call`
(`docs/architecture/DATA_MODEL.md`), não parte deste contrato.

## Relação com outros documentos

`docs/architecture/DATA_MODEL.md` descreve `Objections` como sub-item conceitual de `Call`
dentro de `Deal`; este documento é a especificação concreta desse sub-item para a v0. Domínio
geral de vendas: `docs/domain/SALES_MODEL.md`. Contrato de origem (`Call`,
`TranscriptSegment`, ids determinísticos): `src/closer_ai/normalization/models.py` e
`src/closer_ai/normalization/ids.py`.
