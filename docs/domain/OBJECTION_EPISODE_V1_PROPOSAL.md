# ObjectionEpisode v1 — Proposal (AC-47)

Status: **PROPOSAL — não implementado.** Nenhum código muda com este documento. Contrato
vigente continua sendo `ObjectionEvent` v0 (`docs/domain/OBJECTION_MODEL.md`,
`src/closer_ai/domain/objection.py`).

Pergunta que este documento responde:

> Qual é o menor contrato `ObjectionEpisode` v1 capaz de suportar anotação humana, grounding,
> evals e futura Outcome Intelligence sem inflar o domínio prematuramente?

Resposta curta: **7 campos armazenados** (`schema_version`, `episode_id`, `call_id`,
`category`, `anchor_segment_id`, `followup_segment_ids`, `resolution_status`). Todo o resto
(quem levantou, tempos, handling, reação, reabertura, "call terminou no meio") é **derivado
deterministicamente** da `Call` + do conjunto de episódios, nunca armazenado.

## 1. Problem

`ObjectionEvent` v0 responde "o lead expressou resistência da categoria X neste segmento?".
Isso é detecção pontual. Outcome Intelligence precisa de uma unidade maior:

```
lead objection → closer handling → lead reaction → (follow-up) → estado ao fim do fio
```

Sem essa unidade, não dá para perguntar "objeções de preço que terminaram sem resolução na
última call se correlacionam com deal perdido?" — o v0 só sabe contar menções.

## 2. Current model (v0, código é a fonte da verdade)

| Item | Estado atual |
|---|---|
| Campos | `schema_version`, `objection_id`, `call_id`, `segment_id`, `category` |
| Taxonomia | `price`, `timing_priority`, `trust_authority`, `no_need`, `other` (fechada) |
| ID | `obj_` + sha256(`["objection", call_id, segment_id, category]`)[:24], re-checado no validator |
| Dedup | mesma categoria + mesmo segmento → mesmo id; outro segmento → novo evento |
| Evidência | 1 `segment_id` inteiro, sem char span, sem texto duplicado |
| Extractor | `RuleBasedObjectionExtractor`: keyword PT, só segmentos com speaker `role="lead"`, nunca emite `other` |
| Eval | `evals/objection_v0/`: 9 entradas sintéticas; match por `objection_id` exato |
| Grounding | fora do modelo (extractor/eval têm a `Call`) |

## 3. Observed limitations

1. **Menção ≠ episódio.** Lead repete "tá caro" duas vezes no mesmo fio de conversa → 2
   eventos. Não há como distinguir "repetiu dentro do mesmo embate" de "reabriu 10 min depois".
2. **Sem handling nem reação.** Nada liga a objeção ao que o closer respondeu ou ao que o lead
   respondeu depois.
3. **Sem estado final.** Nenhum campo de resolução (lacuna registrada em
   `docs/context/OPEN_QUESTIONS.md`).
4. **Eval por id exato é frágil para episódios.** Com fronteira multi-segmento, dois
   anotadores escolhendo âncoras vizinhas falhariam match exato mesmo concordando no
   episódio.
5. **Evidência de segmento único** não cobre objeção partida entre segmentos (caso
   `objection_split_across_segments` do golden set sintético, hoje documentado como gap).

## 4. Episode definition

> Um **ObjectionEpisode** é o fio de conversa, **dentro de uma única Call**, que começa quando
> um participante com `role="lead"` expressa resistência de uma categoria da taxonomia e
> termina quando esse fio se fecha (a conversa segue para outro assunto) ou a call acaba.

Invariantes de domínio:

- **Intra-call.** Um episódio nunca atravessa calls. A mesma objeção em outra call do mesmo
  deal é outro episódio; ligação entre calls é derivação no nível de Deal (via
  `CallDealMatch`), nunca campo do episódio.
- **Uma categoria por episódio.**
- **Âncora sempre do lead.** O segmento âncora é falado por participante `role="lead"` na
  `Call` (TD-14: `unknown` nunca vira lead por inferência).
- **Resolução é in-call.** `resolution_status` descreve o estado ao fim do episódio dentro da
  call. **Não** é outcome do Deal e não o prevê (Call outcome ≠ Deal outcome).

## 5. Boundary rules

Respostas às perguntas da AC-47:

| # | Pergunta | Regra |
|---|---|---|
| 1 | Quando começa? | No **primeiro segmento do lead** que expressa a resistência. Prompts do closer antes disso ("e o preço, o que achou?") não entram. Esse segmento é a **âncora**. |
| 2 | Quando termina? | No **último segmento que ainda trata dessa objeção** (handling do closer ou reação do lead). Não há campo de fim: é o maior `segment_index` entre âncora e follow-ups. |
| 3 | Objeção repetida minutos depois | **Mesmo episódio** se o fio ainda não fechou (nenhum segmento substantivo sobre outro assunto entre as duas menções). **Novo episódio** se houve pelo menos um segmento substantivo sobre outro assunto no meio. Tempo em minutos não é critério — segmentos são. Interjeições ("uhum", "sim", "tá") não contam como mudança de assunto. |
| 4 | Reopening | **Novo episódio**, mesma categoria, âncora posterior. Reabertura é **derivada** (existe episódio anterior da mesma categoria na mesma call), sem campo. O episódio anterior **não é reescrito** — seu `resolution_status` continua o estado observado ao fim dele. |
| 5 | Duas objeções na mesma fala | **Dois episódios** (categorias diferentes), mesma âncora. Mesma categoria duas vezes na mesma fala → **um** episódio (igual ao dedup v0). |
| 6 | Handling do closer | Segmentos do closer listados em `followup_segment_ids`. Classificação como "handling" é derivada do `role` do speaker. |
| 7 | Handling multi-passo? | Sim: vários segmentos do closer no mesmo episódio, na ordem da call. Sem tipo de estratégia em v1 (ver Deferred). |
| 8 | Reação do lead | Segmentos do lead **após a âncora** em `followup_segment_ids`. Classificação derivada do `role`. O efeito da reação é resumido em `resolution_status`. |
| 9 | resolved / partially / unresolved / unknown | Ver §9 Resolution semantics. |
| 10 | Call termina antes de resolução | Episódio fecha no último segmento com evidência; `resolution_status="unknown"` se não há reação do lead que sustente outro valor. "Terminou no fim da call" é derivado (nenhum segmento substantivo após o episódio), não campo. |

Regra de desempate geral: **na dúvida entre mesmo/novo episódio, anotar como o mesmo** (menos
episódios, fronteira mais larga). Isso é uma escolha a validar por Otávio em calls reais
(Open decision D3).

## 6. Field proposal

Legenda: Obs = diretamente observável; Inf = inferido; Ann = anotável por humano; Gr =
groundable na `Call`; Req = obrigatório; MVP = entra no v1.

| Field | Purpose | Obs? | Inf? | Ann? | Gr? | Req? | MVP? | Decisão |
|---|---|---|---|---|---|---|---|---|
| `schema_version` | versionar contrato | — | — | — | — | default | sim | **KEEP** (`"1.0.0"` do novo tipo) |
| `episode_id` | identidade/idempotência | — | derivado | não | — | sim | sim | **KEEP** (§10) |
| `call_id` | rastrear até a Call | sim | — | sim | sim | sim | sim | **KEEP** |
| `category` (≈ `objection_family`) | taxonomia | não (julgamento) | sim | sim | via âncora | sim | sim | **KEEP**, mesmo enum v0, mesmo nome (sem rename por churn) |
| `objection_subtype` | taxonomia fina | não | sim | ainda não | — | — | não | **DEFER** até taxonomia v1 existir |
| `raised_by` | quem levantou | sim | — | — | sim | — | não | **REJECT**: derivado de `anchor.speaker_id → participant.role` |
| `anchor_segment_id` (= primary evidence) | onde a objeção foi expressa | sim | — | sim | sim | sim | sim | **KEEP** |
| `followup_segment_ids` (≈ `evidence_segment_ids` − âncora) | handling + reação | sim | seleção é julgamento | sim | sim | sim (pode ser vazio) | sim | **KEEP** |
| `started_at` / `ended_at` | posição temporal | sim | — | — | sim | — | não | **REJECT**: derivado de `start_ts`/`end_ts` dos segmentos |
| `handling_steps[]` | handling estruturado | parcial | tipo de estratégia é inferido | tipo: não confiável hoje | segmentos: sim | — | não | **REJECT como lista tipada**; handling = segmentos do closer em `followup_segment_ids`; tipo de estratégia DEFER |
| `lead_reaction` | reação do lead | não (julgamento) | sim | sim | via segmentos | — | não | **REJECT**: redundante com `resolution_status` + segmentos do lead em follow-ups |
| `resolution_status` | estado in-call ao fim do episódio | não | **sim** | sim | via segmentos | sim | sim | **KEEP** (§9) |
| `next_step` | próximo passo | parcial | sim | sim | sim | — | não | **REJECT** aqui: é `Commitment` (entidade irmã, `GLOSSARY.md`), não atributo de objeção |
| `confidence` | incerteza do extractor | — | — | não | — | — | não | **DEFER** até existir extractor probabilístico (mesmo motivo do v0) |

Contrato proposto (pseudocódigo, **não implementado**):

```python
ResolutionStatus = Literal["resolved", "partially_resolved", "unresolved", "unknown"]

class ObjectionEpisode(BaseModel):          # frozen
    schema_version: str = "1.0.0"
    episode_id: str                          # == derive_episode_id(call_id, anchor_segment_id, category)
    call_id: str                             # non-empty
    category: ObjectionCategory              # enum v0, inalterado
    anchor_segment_id: str                   # non-empty
    followup_segment_ids: tuple[str, ...]    # pode ser (); sem duplicatas; sem a âncora; ordem da call
    resolution_status: ResolutionStatus      # obrigatório, SEM default
```

`resolution_status` sem default: força quem constrói (humano, rule-based, LLM) a declarar
explicitamente — inclusive `"unknown"` — em vez de herdar um valor silencioso.

## 7. Evidence contract

| Opção | Decisão | Por quê |
|---|---|---|
| Múltiplos segment IDs | **SIM** | episódio é multi-turno por definição |
| Primary evidence | **SIM** = `anchor_segment_id` | grounding mínimo idêntico ao v0; base do id |
| Objection vs handling vs reaction em listas separadas | **NÃO** | papel é derivável do `speaker_id → role` do segmento; listas separadas seriam segunda fonte de verdade que pode divergir da `Call` |
| Reaction evidence explícita | **NÃO** como campo; derivada (segmentos `role="lead"` em follow-ups) | idem |
| Character spans | **NÃO** | segmento inteiro continua a unidade; spans exigem estabilidade de texto/ASR que não temos |
| Texto/quote no episódio | **NÃO** | duplicaria `TranscriptSegment.text`; risco de PII fora da Call |
| Timestamps no episódio | **NÃO** | derivados; ordem usa `segment_index`, robusta a crosstalk |

Follow-ups podem ter qualquer `role` (`closer`, `lead`, `other`, `unknown`): segmentos de
`other`/`unknown` são evidência do fio mas não são classificados como handling nem reação —
e podem ser o último segmento (fronteira final) do episódio.
Um mesmo segmento pode aparecer em mais de um episódio (ex.: um handling que responde a duas
objeções; duas objeções na mesma fala).

## 8. Handling model e Reaction model

- **Handling** (derivado) = `[s for s in followups if role(s) == "closer"]`, na ordem da call.
  `has_handling` = lista não vazia. Multi-passo = mais de um elemento.
- **Reaction** (derivado) = `[s for s in followups if role(s) == "lead"]`. A última reação do
  lead é o principal insumo de `resolution_status`.
- **Sem taxonomia de estratégia em v1.** "Como o closer lidou" (reframe, desconto, prova
  social...) é `Strategy`, entidade irmã em `DATA_MODEL.md`, e depende de uma taxonomia que
  ainda não existe e não seria anotável com concordância hoje.

## 9. Resolution semantics

Julgado **ao fim do episódio**, **só com evidência dentro do episódio**, com base principal na
**última reação do lead**:

| Valor | Critério (precisa de evidência em segmento do lead) |
|---|---|
| `resolved` | lead sinaliza explicitamente que a preocupação foi atendida ("faz sentido", "então tá ok") ou avança sem reservas sobre aquele ponto. |
| `partially_resolved` | lead aceita parte, suaviza, ou condiciona ("o preço até vai, mas preciso ver o parcelamento"); sinais mistos no fechamento do fio. |
| `unresolved` | lead reitera ou rejeita a resposta ("continua caro pra mim") como última reação, ou declara que a questão fica em aberto. |
| `unknown` | sem reação do lead após o handling; transcrição ilegível no trecho; call acaba; evidência contraditória sem desfecho claro. **Default honesto** — correctness > coverage. |

Regras:

- **Interjeição isolada não resolve.** "tá", "ok", "uhum", "sim" sozinhos (sem cláusula
  adicional, assentimento explícito sobre o ponto, ou próximo passo observável) nunca
  justificam `resolved` nem `partially_resolved` → `unknown`. Mesma classe de interjeição que
  §5 regra 3 não conta como mudança de assunto.
- **Silêncio não é resolução.** Closer mudar de assunto e lead não reagir → `unknown`, não
  `resolved`.
- **Ausência de handling não implica `unresolved`.** O status depende do sinal do lead, não
  do closer.
- **Contradição:** vale a última reação do lead no episódio; contradição na última reação →
  `partially_resolved`; se não dá para decidir → `unknown`.
- **Imutável e local:** reabertura posterior gera novo episódio, não altera este.
- `RuleBasedObjectionExtractor` não tem sinal para julgar resolução → sempre `"unknown"`.

## 10. ID / dedup strategy

**Decisão proposta:**

```
episode_id = "ep_" + sha256(json.dumps(["objection_episode", call_id, anchor_segment_id, category]))[:24]
```

Mesma técnica de `closer_ai.normalization.ids` e do v0; validator re-checa a derivação (como
o v0 faz).

| Tema | Decisão |
|---|---|
| Identidade | (call, âncora, categoria). Follow-ups e resolução **não** entram: são julgamentos que mudam em re-anotação sem mudar "qual episódio é". |
| Estabilidade entre reexecuções | determinística; mesmo input → mesmo id. |
| Run-dependent (UUID) | **rejeitado**: quebra idempotência e join com golden set. |
| Split (1 episódio vira 2) | o primeiro mantém id (mesma âncora); o segundo ganha id novo (nova âncora). |
| Merge (2 viram 1) | o merged mantém o id da âncora mais antiga; o id posterior deixa de existir. |
| Repeated/reopened | âncora diferente → id diferente, por construção. |
| Mesma categoria, mesma âncora, "duas objeções" | colapsa em um episódio (igual v0). Aceito conscientemente. |
| Namespace | prefixo `ep_` + tag `"objection_episode"`: nunca colide com `obj_` do v0. Entidades diferentes, ids diferentes. |
| Call/Deal/Lead IDs | **inalterados**. |

**ID ≠ critério de match em eval.** O id serve para identidade/idempotência. Comparação
predição × gold (e humano × humano) usa **match por sobreposição** (§12), porque âncora exata
é exigente demais para fronteiras multi-segmento.

## 11. Observability vs inference

| Classe | Itens |
|---|---|
| **DIRECT EVIDENCE** | `call_id`; existência dos segmentos referenciados; `speaker_id` e `text` desses segmentos (vivem na Call) |
| **DERIVED DETERMINISTICALLY** | `episode_id`; `raised_by` (role da âncora); início/fim (`start_ts`/`end_ts`/`segment_index`); handling/reaction (role dos follow-ups); `has_handling`; reabertura/recorrência (ordem de episódios da mesma categoria na call); "terminou no fim da call"; `deal_id` via `CallDealMatch` |
| **HUMAN JUDGMENT** (golden set) | que a âncora expressa objeção; `category`; quais segmentos pertencem ao fio (`followup_segment_ids`); fronteira mesmo/novo episódio; `resolution_status` |
| **MODEL INFERENCE** (extractor) | os mesmos quatro itens acima quando produzidos por extractor |

`category`, `followup_segment_ids` e `resolution_status` são **sempre** julgamento/inferência,
nunca fato observado — mesmo quando apontam para segmentos reais. Proveniência (humano vs
rule-based vs LLM, qual versão) é propriedade do **lote/run** que contém os episódios, não de
cada registro: o mesmo episódio anotado por humano e predito por modelo tem o mesmo
`episode_id` justamente para poder ser comparado. Ver Open decision D4.

## 12. Grounding requirements

Checagem cross-object (fora do modelo, igual v0 — quem tem a `Call` valida):

1. `call_id` == `Call.call_id`.
2. `anchor_segment_id` e todos os follow-ups resolvem para segmentos dessa Call.
3. Speaker da âncora resolve para participante com `role == "lead"`. `unknown`/`other`/
   `closer` → inválido (TD-14; closer citando lead nunca é âncora).
4. Todo follow-up tem `segment_index` > índice da âncora; lista em ordem crescente de
   `segment_index`; sem duplicatas; sem a âncora.

Métricas de eval sugeridas (Evaluator valida):

**Algoritmo de match** (determinístico; o mesmo para pred × gold e humano A × humano B).
Seja `S(e) = {anchor} ∪ followups` (conjunto inclui a âncora):

1. Particionar por `(call_id, category)`. Episódios de categorias diferentes nunca casam.
2. Par candidato `(g, p)` se `g.anchor ∈ S(p)` **ou** `p.anchor ∈ S(g)` (qualquer direção).
3. Peso = Jaccard(`S(g)`, `S(p)`).
4. Greedy 1-para-1: ordenar candidatos por (peso desc, `segment_index` da âncora de g asc,
   `segment_index` da âncora de p asc); aceitar o par se nem g nem p já foram casados.
5. Classificar os não casados:
   - pred não casado com candidato em algum gold casado → **split fragment** (limitação de
     threading, não alucinação);
   - pred não casado sem nenhum candidato → **unsupported** (falso positivo real);
   - gold não casado com candidato em algum pred casado → **merge miss**;
   - gold não casado sem candidato → **missed** (falso negativo real).

Métricas:

- **Episode detection P/R**: P = casados / (casados + unsupported); R = casados /
  (casados + missed). Split fragments e merge misses reportados **à parte**, não somados a
  FP/FN — senão o baseline sem threading (§15) apareceria como alucinação.
- **Split/merge counts** por call.
- **Anchor exact agreement** nos pares casados.
- **Boundary agreement**: Jaccard médio de `S(g)`, `S(p)` nos pares casados.
- **Resolution**: matriz de confusão + kappa nos pares casados, `unknown` como classe própria.
- **Grounding rate**: % de episódios que passam 1–4.
- Humano × humano usa exatamente as mesmas métricas (agreement) antes de medir extractor.

## 13. Confidence semantics

Sem campo `confidence` em v1. Extractor determinístico não tem distribuição; humano não
produz score calibrado. Incerteza é expressa **no domínio**: `resolution_status="unknown"` e a
regra de não anotar objeção duvidosa. Reintroduzir quando existir extractor probabilístico, com
semântica definida (probabilidade calibrada de quê?), não um número solto.

## 14. Edge cases

| Caso | Tratamento |
|---|---|
| No objection | zero episódios. O dataset precisa distinguir "anotada, sem episódios" de "não anotada" — responsabilidade do golden set, não do episódio. |
| `unresolved_lead` (quality flag) | nenhum participante `role="lead"` → nenhum episódio groundable. Call fica fora do golden set de episódios até o role ser resolvido **na Call** (nunca no episódio). |
| Speaker unknown | segmento `unknown` não pode ser âncora; pode ser follow-up (evidência não classificada). |
| Closer quoting lead | nunca âncora; pode ser handling ("você falou que tá caro, mas..."). |
| Multiple participants | vários `role="lead"` podem ancorar; `other` não ancora (D5: definir se sócio/decisor do lado do lead é `lead`). |
| Repeated objection | mesmo fio → follow-up do mesmo episódio; após mudança de assunto → novo episódio. |
| Reopened objection | novo episódio; reabertura derivada; anterior inalterado. |
| Multiple objections in same utterance | um episódio por categoria, mesma âncora. |
| One handling addressing two objections | mesmo segmento em `followup_segment_ids` de ambos. |
| Objection with no handling | `followup_segment_ids` sem closer; status pelo sinal do lead, tipicamente `unknown`. |
| Poor transcript | objeção não inteligível → não anotar. Objeção clara mas reação ilegível → `unknown`. |
| Missing timestamp | Canonical Call exige timestamps; episódio não depende deles (usa `segment_index`). Timestamps ruins afetam só derivados de tempo. |
| Overlapping segments | ordem por `segment_index`, não por `start_ts`. |
| Contradictory evidence | última reação do lead; contradição final → `partially_resolved`; indecidível → `unknown`. |
| Partial resolution | `partially_resolved` (§9). |
| Call ends during objection | episódio fecha no último segmento; `unknown` salvo reação clara; "terminou no fim" é derivado. |
| Lead agrees, later reopens | ep1 `resolved`, ep2 novo (mesma categoria); padrão "resolução não durável" é derivável. |
| Objection split across segments | âncora = primeiro segmento do lead com a objeção; continuação do lead entra como follow-up. Resolve o gap do v0. |

## 15. Migration v0 → v1

- **Sem migração destrutiva.** `ObjectionEvent` v0, seu id, o extractor e o eval v0 continuam
  intactos. `ObjectionEpisode` seria um tipo **novo e aditivo** (D1).
- **Lifting determinístico** (função pura, a implementar junto do contrato):
  `episode_from_event(e) → ObjectionEpisode(call_id=e.call_id, category=e.category,
  anchor_segment_id=e.segment_id, followup_segment_ids=(), resolution_status="unknown")`.
- **Limitação conhecida do lifting:** super-segmenta — duas menções do mesmo fio viram dois
  episódios, porque o rule-based não faz threading. Aceitável como baseline; aparece como
  **split fragments** (§12), separado de unsupported. P/R do baseline v1 **não é comparável**
  diretamente com P/R do eval v0 (unidade diferente).
- Episódios de dataset (golden set) são anotados diretamente em v1, não convertidos do v0.

## 16. Rejected fields

`raised_by`, `started_at`, `ended_at`, `handling_steps[]` tipado, `lead_reaction`,
`next_step`, texto/quote, char spans, listas separadas de evidência por papel,
`reopens_episode_id` (derivável), campo de proveniência por registro (ver D4). Motivo de cada
um nas §§6–11.

## 17. Deferred fields

`objection_subtype` (taxonomia v1), tipo de estratégia do handling (`Strategy`), `confidence`
(extractor probabilístico), `severity`, link direto a `Deal`/`Outcome` (continua via
`CallDealMatch`), ligação cross-call de episódios (derivação Deal-level em Outcome
Intelligence).

## 18. Impact analysis

| Área | Impacto |
|---|---|
| `ObjectionEvent` v0 | nenhum; continua válido e em uso |
| `RuleBasedObjectionExtractor` | nenhum agora; episódios dele viriam do lifting (`unknown`, sem follow-ups) |
| Synthetic eval v0 | nenhum; eval de episódio seria harness novo (`evals/objection_episode_v1/`) com match por sobreposição |
| Future taxonomy | desacoplada: `category` reusa o enum v0; subtype é aditivo |
| Annotation Guidelines | este documento define **unidade e fronteiras**; conteúdo das guidelines é de Otávio |
| Future LLM extractor | alvo de saída = este contrato; precisa threading + resolução; proveniência no run |
| Deal / Outcome Intelligence | sem mudança de schema; consome episódios via `call_id → CallDealMatch → deal_id` |
| IDs | novo `ep_`; Call/Segment/Deal/Lead/Objection ids inalterados |
| Serialization | Pydantic JSON; `tuple` serializa como array |
| Tests | futuros: unit do contrato (id, invariantes, sem default), grounding helper, lifting |
| Canonical Call / Agro parser / CRM matching | **nenhum** |

## 19. Open decisions

| # | Decisão | Recomendação | Dono |
|---|---|---|---|
| D1 | Episode coexiste com Event v0 (aditivo) ou o substitui? | coexistir até eval real mostrar que Event é redundante | Matheus |
| D2 | Aprovar id = (call, âncora, categoria) e match de eval por sobreposição | aprovar | Matheus + Evaluator |
| D3 | Regra "mudança de assunto substantiva ⇒ novo episódio" e desempate "na dúvida, mesmo episódio" são anotáveis com concordância? | piloto de dupla anotação em 3–5 calls reais antes de implementar; go/no-go sugerido: detection F1 humano×humano ≥ 0.8 e κ de `resolution_status` ≥ 0.6 (limiares a confirmar) | Otávio |
| D4 | Proveniência (humano/rule-based/LLM + versão) no lote/run, não no registro | aprovar; formalizar quando existir storage/run model | Matheus |
| D5 | Participante do lado do lead (sócio, cônjuge, decisor) é `role="lead"` ou `other`? | é regra da Call, não do episódio; decidir junto com guidelines | Otávio + Matheus |
| D6 | Definições de `resolved`/`partially_resolved`/`unresolved` fazem sentido comercial e são as que Outcome Intelligence precisa? | validar | Gabriel (sentido comercial) + Otávio (anotabilidade) |
| D7 | Implementar o contrato em código agora ou após D3/D6? | após D3/D6 | Matheus |
| D8 | Registrar D1/D2/D4 como ADR em `docs/decisions/` (contrato entre módulos, ver `docs/decisions/README.md`) | abrir ADR curto referenciando este doc no momento em que D1/D2 forem decididos | Matheus |

## 20. Definition of Done (desta proposta)

- [x] Auditoria do v0 contra o código.
- [x] Definição de episódio + regras de fronteira para as 10 perguntas.
- [x] Tabela de campos com KEEP/REJECT/DEFER justificados.
- [x] Evidence contract, handling, reaction, resolution, ID/dedup, grounding, confidence.
- [x] Classificação observável vs derivado vs julgamento vs inferência.
- [x] 17 edge cases obrigatórios cobertos (+1: objeção partida entre segmentos).
- [x] Migração sem quebrar v0; impacto por área.
- [x] Review Domain / Evaluator / Architecture: APPROVE (Evaluator após correções em §9/§12/§15).
- [ ] D1–D7 decididos por humanos.
- [ ] (Próxima task) Implementação do contrato + grounding helper + testes, só após D3/D6/D7.
