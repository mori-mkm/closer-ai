# ObjectionEpisode v1 — Proposal (AC-47)

Status: **PROPOSAL rev. 2 — não implementado.** Nenhum código muda com este documento.
Contrato vigente continua sendo `ObjectionEvent` v0 (`docs/domain/OBJECTION_MODEL.md`,
`src/closer_ai/domain/objection.py`).

Rev. 2 corrige os blockers do adversarial review externo: resolução por última evidência
**substantiva** (§9), episódio pertence ao **objetor** (§5.1), métricas com TP/FP/FN
convencionais (§12), e evidência separando **objeção** de **contexto pós-objeção** (§7).

Pergunta que este documento responde:

> Qual é o menor contrato `ObjectionEpisode` v1 capaz de suportar anotação humana, grounding,
> evals e futura Outcome Intelligence sem inflar o domínio prematuramente?

Resposta curta: **7 campos armazenados** (`schema_version`, `episode_id`, `call_id`,
`category`, `objection_segment_ids`, `context_segment_ids`, `resolution_status`). Objetor,
âncora, tempos, reabertura e "call terminou no meio" são **derivados**. Função conversacional
fina (pergunta de clarificação vs. argumento vs. citação) **não** é modelada em v1.

## 1. Problem

`ObjectionEvent` v0 responde "o lead expressou resistência da categoria X neste segmento?".
Isso é detecção pontual. Outcome Intelligence precisa de uma unidade maior:

```
objeção do lead → turnos do closer → reação do mesmo lead → estado ao fim do fio
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

1. **Menção ≠ episódio.** Lead repete "tá caro" no mesmo fio → 2 eventos; não distingue
   reiteração de reabertura.
2. **Sem turnos do closer, sem reação, sem estado final** (lacuna em
   `docs/context/OPEN_QUESTIONS.md`).
3. **Eval por id exato** é frágil para fronteiras multi-segmento.
4. **Objeção partida entre segmentos** ("Sobre o preço..." / "...ficou muito acima") não cabe
   em um segmento.
5. **Papel do speaker ≠ função conversacional.** Fala do lead pode ser continuação da objeção,
   reação, ou nova objeção; fala do closer pode ser clarificação, argumento, citação da
   objeção, ou outro assunto. Nenhum modelo baseado só em `role` distingue isso.

## 4. Episode definition

> Um **ObjectionEpisode** é o fio de conversa, **dentro de uma única Call**, em que **um
> participante** (o **objetor**, `role="lead"`) expressa resistência de **uma** categoria, mais
> o contexto pós-objeção que trata dessa resistência, até o fio se fechar ou a call acabar.

Invariantes de domínio:

- **Intra-call.** Nunca atravessa calls. Ligação entre calls é derivação Deal-level via
  `CallDealMatch`, nunca campo do episódio.
- **Uma categoria, um objetor.** O objetor é o speaker da âncora
  (`anchor → speaker_id`), derivado, não armazenado.
- **Objetor sempre `role="lead"`** na `Call` (TD-14: `unknown` nunca vira lead por inferência).
- **Resolução é in-call e do objetor.** `resolution_status` descreve o estado **da posição do
  objetor** ao fim do episódio. Não é outcome do Deal e não o prevê.

## 5. Boundary rules

| # | Pergunta | Regra |
|---|---|---|
| 1 | Quando começa? | No **primeiro segmento do objetor** que expressa a resistência (a **âncora**). Prompts do closer antes disso não entram. |
| 2 | Quando termina? | No último segmento (de qualquer speaker) que ainda trata dessa objeção. Sem campo de fim: é o maior `segment_index` do episódio. |
| 3 | Objeção repetida minutos depois | **Mesmo episódio** (reação/reiteração do objetor, em contexto) se o fio não fechou. **Novo episódio** se houve ≥ 1 segmento substantivo sobre outro assunto entre as duas menções. Tempo não é critério. Interjeições (§9.1) não contam como mudança de assunto. |
| 4 | Reopening | **Novo episódio**, mesma categoria e objetor, âncora posterior. Reabertura é derivada. O episódio anterior **não é reescrito**. |
| 5 | Duas objeções na mesma fala | Categorias diferentes → **dois episódios**, mesma âncora. Mesma categoria duas vezes → **um** episódio (igual dedup v0). |
| 6 | Turnos do closer | Segmentos do closer em `context_segment_ids`. |
| 7 | Handling multi-passo? | Sim: vários segmentos do closer no contexto. Função fina (clarificação vs. argumento vs. citação) não é modelada (§8). |
| 8 | Reação do lead | Segmentos **do objetor** em `context_segment_ids`. |
| 9 | Resolution | §9. |
| 10 | Call termina antes de resolução | Episódio fecha no último segmento com evidência; `unknown` se não há sinal substantivo do objetor. "Terminou no fim da call" é derivado. |

Desempate: **na dúvida entre mesmo/novo episódio, mesmo episódio.** Regra a validar no piloto
(D3).

### 5.1 Objetor e múltiplos participantes

**Regra:** um episódio pertence ao participante que ancora a objeção. Objetor =
`speaker_id` do segmento âncora. Não há campo `raised_by`: a âncora já o determina.

| Caso | Regra |
|---|---|
| Múltiplos leads | Cada participante `role="lead"` que expressa resistência própria ancora o **seu** episódio. |
| Mesma categoria, participantes diferentes | **Episódios separados**, mesmo que simultâneos e com contexto compartilhado. Ex. sintético: Financeiro: "Não conseguimos aprovar esse preço." / Técnico: "Pra mim o preço está ok." → 1 episódio `price` do Financeiro; a fala do Técnico é contexto (sem resistência própria, não gera episódio) e **não** resolve o episódio do Financeiro. |
| Concordância explícita de outro participante com a objeção ("Concordo, está caro.") | É resistência própria → **novo episódio** ancorado nesse participante. |
| Discordância explícita de outro participante ("Pra mim está ok.") | Contexto do episódio do objetor; nunca sinal de resolução dele. |
| Declaração coletiva do objetor ("A gente não consegue pagar.") | Atribuída ao speaker do segmento (o objetor). Não cria episódios para os demais. |
| Declaração coletiva de outro participante ("Pra nós está resolvido.") | Contexto; não resolve o episódio do objetor. |
| Todos os segmentos de `objection_segment_ids` | Devem ter o mesmo `speaker_id` da âncora (grounding §12). |
| O que fica **UNKNOWN** | Posição do objetor quando só outros participantes reagem (→ `unknown`); se um participante `other` é decisor comercialmente equivalente a lead (D5 — episódio não pode ser ancorado nele hoje: lacuna de cobertura aceita); speaker_id que funde duas pessoas por erro de diarização (fora do escopo do episódio, problema da Call). |

## 6. Field proposal

Legenda: Obs = diretamente observável; Inf = inferido; Ann = anotável; Gr = groundable;
Req = obrigatório; MVP = entra no v1.

| Field | Purpose | Obs? | Inf? | Ann? | Gr? | Req? | MVP? | Decisão |
|---|---|---|---|---|---|---|---|---|
| `schema_version` | versionar contrato | — | — | — | — | default | sim | **KEEP** |
| `episode_id` | identidade/idempotência | — | derivado | não | — | sim | sim | **KEEP** (§10) |
| `call_id` | rastrear até a Call | sim | — | sim | sim | sim | sim | **KEEP** |
| `category` | taxonomia (≈ `objection_family`) | não | sim | sim | via objeção | sim | sim | **KEEP**, enum v0, sem rename |
| `objection_segment_ids` | **evidência da objeção**: âncora + continuação do objetor | segmentos sim; seleção não | seleção | sim | sim | sim, ≥ 1 | sim | **KEEP** (§7) |
| `context_segment_ids` | **contexto pós-objeção**: turnos do closer, reações do objetor, falas de terceiros sobre a objeção | segmentos sim; seleção não | seleção | sim | sim | sim, pode ser `()` | sim | **KEEP** (§7) |
| `resolution_status` | posição do objetor ao fim do episódio | não | **sim** | sim | via contexto | sim, sem default | sim | **KEEP** (§9) |
| `raised_by` | objetor | sim | — | — | sim | — | não | **REJECT**: derivado da âncora |
| `anchor_segment_id` | âncora | sim | — | sim | sim | — | não | **REJECT como campo**: = 1º elemento de `objection_segment_ids` |
| `started_at` / `ended_at` | tempo | sim | — | — | sim | — | não | **REJECT**: derivados |
| `handling_steps[]` tipado | estratégia | parcial | sim | não confiável hoje | — | — | não | **DEFER** (Strategy) |
| `lead_reaction` | reação | não | sim | sim | — | — | não | **REJECT**: coberto por reações em contexto + `resolution_status` |
| per-segment phase | função por segmento | não | sim | a validar | sim | — | não | **REJECT em v1** (§7, opção B) |
| `next_step` | próximo passo | parcial | sim | sim | sim | — | não | **REJECT**: é `Commitment` |
| `objection_subtype` | taxonomia fina | não | sim | ainda não | — | — | não | **DEFER** |
| `confidence` | incerteza | — | — | não | — | — | não | **DEFER** |
| proveniência | quem/qual versão produziu | — | — | — | — | — | não | **REJECT por registro** — vive no run (D4 APPROVED) |

Contrato proposto (pseudocódigo, **não implementado**):

```python
ResolutionStatus = Literal["resolved", "partially_resolved", "unresolved", "unknown"]

class ObjectionEpisode(BaseModel):            # frozen
    schema_version: str = "1.0.0"
    episode_id: str                            # == derive_episode_id(call_id, objection_segment_ids[0], category)
    call_id: str                               # non-empty
    category: ObjectionCategory                # enum v0, inalterado
    objection_segment_ids: tuple[str, ...]     # >= 1; [0] é a âncora; ordem da call; sem duplicatas
    context_segment_ids: tuple[str, ...]       # pode ser (); ordem da call; sem duplicatas; disjunto de objection_segment_ids
    resolution_status: ResolutionStatus        # obrigatório, SEM default
```

Checagens intra-modelo (sem `Call`): strings não vazias, ≥ 1 objection segment, sem
duplicatas, listas disjuntas, id bate com a derivação. Ordem, speakers e pertencimento à call
são grounding (§12).

## 7. Evidence contract

### 7.1 Alternativas avaliadas

| Opção | Estrutura | Distingue continuação / closer / reação? | Custo | Decisão |
|---|---|---|---|---|
| A | `anchor_segment_id` + `objection_evidence_segment_ids` + `followup_segment_ids` | sim | 3 campos; âncora redundante com o 1º da evidência se esta incluir a âncora, ou invariante extra se não incluir | rejeitada — é C com um campo a mais |
| B | `anchor_segment_id` + `episode_segment_ids` + fase por segmento (`objection`/`clarification`/`handling`/`quote`/`reaction`/...) | sim, e mais fino | exige **taxonomia de fases** com estudo de concordância próprio; custo de anotação por segmento; fases amplas recuperáveis de C | rejeitada para v1; candidata a v2 junto com Strategy |
| **C** | `objection_segment_ids` (âncora = `[0]`) + `context_segment_ids` | **sim** (tabela 7.2) | 2 campos, 1 julgamento de fronteira por segmento (objeção vs contexto) | **escolhida** |

### 7.2 Função derivada (C + role + objetor)

Dado o episódio anotado e a `Call`, cada segmento do episódio recebe **uma** função ampla,
deterministicamente:

| Segmento | Função derivada |
|---|---|
| em `objection_segment_ids` | **objection evidence** (âncora ou continuação) — sempre do objetor |
| em `context_segment_ids`, speaker = objetor | **objector reaction** |
| em `context_segment_ids`, speaker `role="closer"` | **closer turn** |
| em `context_segment_ids`, outro speaker (outro lead, `other`, `unknown`) | **third-party context** — nunca reação do objetor |

A derivação é determinística **dado** o particionamento objeção/contexto, que é **julgamento
humano ou inferência**. O `role` sozinho não define função: é a combinação da lista (julgada)
com o speaker (observado).

**O que v1 não distingue:** dentro de "closer turn", clarificação vs. argumento vs. citação da
objeção; isso é Strategy (deferred). Por isso o nome é "closer turn", não "handling": o termo
"handling" só pode ser usado no sentido amplo de "closer engajou a objeção".

### 7.3 Regras de particionamento

- **Objection evidence** = segmentos do objetor que **enunciam ou elaboram** o conteúdo da
  objeção, inclusive após uma pergunta de clarificação do closer ("Como assim?" → "Ficou
  acima do que conseguimos pagar." é continuação).
- **Objector reaction** = segmentos do objetor que **respondem a um argumento** do closer
  (aceitar, rejeitar, reiterar, condicionar).
- **Reiteração após argumento** = reação (sinal `rejection`), não nova objeção, enquanto o fio
  não fechou.
- **Mudança de assunto substantiva e depois a mesma objeção** = novo episódio (§5 regra 3).
- **Fala do closer sobre outro assunto** não entra no contexto.
- **Closer citando a objeção** ("Você falou que está caro...") entra como closer turn; nunca
  como objection evidence (não é do objetor).

Exemplo sintético (split objection):

```
s10 Lead:   "Sobre o preço..."                                  → objection
s11 Closer: "Sim?"                                              → context (closer turn)
s12 Lead:   "...ficou muito acima do que conseguimos pagar."    → objection (continuação)
s13 Closer: "Temos parcelamento em 12x."                         → context (closer turn)
s14 Lead:   "Em 12x cabe."                                       → context (objector reaction)
```

`objection_segment_ids = (s10, s12)`, `context_segment_ids = (s11, s13, s14)`, âncora = s10.

### 7.4 Outras escolhas

- **Char spans:** não. Segmento inteiro continua a unidade; spans exigem estabilidade de
  texto/ASR que não temos.
- **Texto/quote:** não (duplicaria `TranscriptSegment.text`; risco de PII).
- **Timestamps:** não; ordem por `segment_index`, robusta a crosstalk.
- Um segmento pode aparecer em mais de um episódio (turno do closer respondendo a duas
  objeções; duas categorias na mesma fala; fala de terceiro relevante para dois episódios).

## 8. Handling model e Reaction model

- **Closer turns** (derivado, §7.2), em ordem. `has_closer_turn` = não vazio. Multi-passo =
  mais de um.
- **Objector reactions** (derivado, §7.2). Insumo de `resolution_status` (§9).
- **Sem taxonomia de estratégia em v1** (`Strategy`, entidade irmã em `DATA_MODEL.md`).

## 9. Resolution semantics

Julgado ao fim do episódio, **só com evidência do objetor** dentro do episódio (reações em
`context_segment_ids`; a própria objeção não conta como sinal).

### 9.1 Classificação de cada reação do objetor (mental, não armazenada)

| Sinal | Definição | Exemplos sintéticos |
|---|---|---|
| **ACCEPT** | aceitação explícita de que a preocupação foi atendida, ou próximo passo que pressupõe a objeção superada | "Esse desconto resolve completamente o problema de preço."; "Então pode mandar o contrato com esse valor." |
| **REJECT** | rejeição da resposta ou reiteração da objeção | "Continua caro pra mim."; "Mesmo parcelado não dá." |
| **MIXED** | na mesma fala, aceita parte e mantém parte | "O valor até vai, mas a entrada ainda pesa." |
| **NEUTRAL** | reconhecimento sem conteúdo sobre o ponto | "ok", "tá", "uhum", "sim", "certo" isolados |
| **OFF-CATEGORY** | fala do objetor sobre outro ponto | ignorada para esta categoria |

### 9.2 Precedência

1. Descartar NEUTRAL e OFF-CATEGORY. **Nunca sobrescrevem** um sinal substantivo anterior.
2. Nenhum sinal substantivo restante → **`unknown`**.
3. Caso contrário, usar o **último sinal substantivo e relevante para a categoria**:
   ACCEPT → `resolved`; REJECT → `unresolved`; MIXED → `partially_resolved`.
4. **Contradição** (sinais opostos em momentos diferentes do mesmo fio): vale o último
   substantivo — o objetor mudou de posição dentro do fio. ACCEPT depois REJECT → `unresolved`;
   REJECT depois ACCEPT → `resolved`.
5. **Último sinal substantivo ininterpretável** (ex.: trecho ilegível, ironia indecidível) →
   `unknown`; não recuar para um sinal anterior.
6. Sinais de **terceiros** (outro lead, closer) nunca entram.

Casos sintéticos:

| Sequência de reações do objetor | Status |
|---|---|
| "Esse desconto resolve completamente o problema de preço." → (closer: "Ótimo.") → "Uhum." | `resolved` (uhum é NEUTRAL, não sobrescreve) |
| "Uhum." → "Tá." | `unknown` (só NEUTRAL) |
| "Faz sentido." → "...mas continua caro pra mim." | `unresolved` (último substantivo = REJECT) |
| "Continua caro." → (closer argumenta) → "Com esse prazo resolve." | `resolved` |
| "O valor até vai, mas a entrada pesa." → "Ok." | `partially_resolved` |
| Nenhuma reação; closer muda de assunto | `unknown` |
| Técnico: "Pra mim está ok." (objetor = Financeiro, calado) | `unknown` |
| Call termina após o argumento do closer | `unknown` |

Regras adicionais:

- **Ausência de closer turn não implica `unresolved`.** O status depende do objetor.
- **Imutável e local:** reabertura posterior é novo episódio; este não muda.
- `RuleBasedObjectionExtractor` não tem sinal para julgar resolução → sempre `unknown`.
- Definições e utilidade comercial dos quatro valores: **D6 (aberta)**.

## 10. ID / dedup strategy

**Proposta:**

```
episode_id = "ep_" + sha256(json.dumps(["objection_episode", call_id, anchor_segment_id, category]))[:24]
anchor_segment_id = objection_segment_ids[0]
```

Mesma técnica de `closer_ai.normalization.ids` e do v0; validator re-checa a derivação.
**Contexto e resolução nunca entram no id.** UUID/run-dependent: rejeitado.

### 10.1 Recheck (após separar objeção de contexto)

| Pergunta | Resposta |
|---|---|
| 1. A âncora é estável o bastante? | Mais estável que qualquer alternativa: é o único ponto que dois anotadores/extractores precisam concordar para "é o mesmo episódio". Continuação, contexto e resolução variam sem mudar o id. **Não** é estável contra correção do início da objeção (item 2). |
| 2. Se a anotação descobre um segmento **anterior** da mesma objeção? | A âncora passa a ser esse segmento anterior → **id muda**. |
| 3. Corrigir a âncora muda o id intencionalmente? | Sim. Identidade = "onde e de quem começou a objeção desta categoria". Mudar o início é mudar a identidade. |
| 4. Isso é aceitável? | Sim, com limitação declarada: (a) não há storage nem referências persistidas a `episode_id` hoje; (b) o eval compara por **overlap**, não por id (§12), então correções de âncora não quebram métricas; (c) golden set é versionado como lote — uma revisão gera nova versão do lote, não patch de id. Quando existir storage, correção de âncora = delete + insert, nunca update in-place. |
| 5. Objetor entra no id? | **Implicitamente, via âncora**: um segmento tem exatamente um `speaker_id`. Não adicionar componente explícito (seria redundante e criaria segunda fonte de verdade). |
| 6. Dois episódios da mesma categoria podem compartilhar âncora? | Não. Mesmo segmento ⇒ mesmo objetor; mesma categoria no mesmo segmento colapsa num episódio (§5 regra 5). Categorias diferentes na mesma âncora têm ids diferentes. Limitação aceita: "duas objeções de preço distintas na mesma fala" viram uma. |

| Tema | Decisão |
|---|---|
| Split (1 → 2) | o primeiro mantém o id; o segundo ganha id novo. |
| Merge (2 → 1) | o merged mantém o id da âncora mais antiga. |
| Repeated / reopened | nova âncora → novo id. |
| Participante diferente, mesma categoria | âncora diferente → id diferente. |
| Namespace | `ep_` + tag `"objection_episode"`; nunca colide com `obj_`. |
| Call/Deal/Lead IDs | inalterados. |

## 11. Observability vs inference

| Classe | Itens |
|---|---|
| **DIRECT EVIDENCE** | `call_id`; existência dos segmentos referenciados; `speaker_id`, `role` e `text` desses segmentos (vivem na Call) |
| **DERIVED DETERMINISTICALLY** | `episode_id`; âncora (`objection_segment_ids[0]`); objetor (speaker da âncora); início/fim; função ampla por segmento (§7.2) **dado** o particionamento; reabertura/recorrência; "terminou no fim da call"; `deal_id` via `CallDealMatch` |
| **HUMAN JUDGMENT** (golden set) | que há objeção; `category`; quais segmentos são objeção vs. contexto; fronteira mesmo/novo episódio; classificação de sinais (§9.1); `resolution_status` |
| **MODEL INFERENCE** (extractor) | os mesmos itens de HUMAN JUDGMENT quando produzidos por extractor |

Correção explícita da rev. 1: a função dos segmentos **não** é derivada só do `role`. O `role`
é observado; a função depende do particionamento objeção/contexto, que é julgamento.

**Proveniência (D4 APPROVED):** pertence ao **extraction/eval run** — tipo (human /
rule-based / LLM), versão do extractor, modelo, prompt, versão do schema. Não é duplicada em
cada episódio. O mesmo episódio anotado e predito tem o mesmo `episode_id` justamente para
ser comparável.

## 12. Grounding requirements e evaluation

### 12.1 Grounding (cross-object, fora do modelo)

1. `call_id` == `Call.call_id`; todo segment id resolve para segmento dessa Call.
2. Âncora (`objection_segment_ids[0]`) falada por participante `role == "lead"`.
3. Todos os `objection_segment_ids` têm o mesmo `speaker_id` da âncora.
4. `objection_segment_ids` e `context_segment_ids` em ordem crescente de `segment_index`;
   todo segmento de contexto tem índice > índice da âncora.

### 12.2 Episode matching

Notação: `O(e)` = `objection_segment_ids`; `E(e)` = `O(e) ∪ context_segment_ids`;
`obj(e)` = objetor. Mesmo algoritmo para pred × gold e para humano A × humano B (A como
referência).

1. **Partição:** `(call_id, category, obj)`. Episódios de partições diferentes nunca casam.
2. **Candidato:** `(g, p)` só se `O(g) ∩ O(p) ≠ ∅` (concordam em **onde está a objeção**, não
   só no contexto).
3. **Score:** Jaccard(`E(g)`, `E(p)`).
4. **Atribuição 1-para-1, greedy determinístico:** ordenar candidatos por (score desc,
   Jaccard(`O(g)`, `O(p)`) desc, `segment_index` da âncora de g asc, `segment_index` da âncora
   de p asc); aceitar o par se nem g nem p já foram casados. (Greedy, não ótimo global:
   escolhido por reprodutibilidade; trocar por max-weight bipartite só se o piloto mostrar
   divergência relevante.)

### 12.3 TP / FP / FN

- **TP** = pares casados.
- **FP** = toda predição não casada. **Sem exceção** para fragmentos.
- **FN** = todo gold não casado. **Sem exceção** para absorvidos em merge.
- P = TP/(TP+FP); R = TP/(TP+FN); F1 convencional.

Sanidade (obrigatória no harness futuro):

| Cenário | TP | FP | FN | P | R | F1 |
|---|---|---|---|---|---|---|
| 10 gold, 1 pred gigante cobrindo todos | 1 | 0 | 9 | 1.0 | 0.1 | 0.18 |
| 1 gold, 10 preds fragmentadas | 1 | 9 | 0 | 0.1 | 1.0 | 0.18 |

### 12.4 Split / merge diagnostics (adicionais, não alteram TP/FP/FN)

Dentro da mesma partição:

- **split:** gold `g` com ≥ 2 predições `p` tais que `O(p) ∩ E(g) ≠ ∅`. As predições não
  casadas nesse conjunto recebem o rótulo **split_fragment** (continuam FP).
- **merge:** predição `p` com ≥ 2 golds `g` tais que `O(g) ∩ E(p) ≠ ∅`. Os golds não casados
  nesse conjunto recebem o rótulo **merge_absorbed** (continuam FN).
- Reportar: nº de golds split, nº de preds merge, e FP/FN decompostos em
  (fragment | absorbed | outros).

### 12.5 Qualidade nos TPs

- **Anchor exact agreement** (âncoras iguais).
- **Objection boundary:** Jaccard médio de `O` — justificado: separa "achou a objeção" de
  "delimitou a objeção" (caso split objection).
- **Episode extent:** Jaccard médio de `E`.
- **Resolution:** matriz de confusão 4×4 e kappa, **só nos TPs** (condicionado ao match;
  reportar junto quantos episódios ficaram fora por FP/FN).
- **Grounding rate:** % de episódios que passam §12.1 (sobre todas as predições).

Sem thresholds de aceitação neste documento (ver D3).

## 13. Confidence semantics

Sem campo `confidence` em v1. Incerteza expressa no domínio (`unknown`, não anotar objeção
duvidosa). Reintroduzir com semântica definida quando houver extractor probabilístico.

## 14. Edge cases

| Caso | Tratamento |
|---|---|
| No objection | zero episódios; dataset distingue "anotada sem episódios" de "não anotada". |
| `unresolved_lead` | nenhum `role="lead"` → nenhum episódio groundable; call fora do golden set de episódios até o role ser resolvido **na Call**. |
| Speaker unknown | não ancora; pode ser third-party context. |
| Closer quoting lead | closer turn em contexto; nunca objection evidence. |
| Multiple participants | §5.1: episódio por objetor; terceiros são contexto e não resolvem. |
| Repeated objection | mesmo fio → reação (REJECT) do mesmo episódio; após mudança de assunto → novo episódio. |
| Reopened objection | novo episódio; reabertura derivada; anterior inalterado. |
| Multiple objections in same utterance | um episódio por categoria, mesma âncora. |
| One closer turn addressing two objections | o segmento aparece no contexto de ambos. |
| Objection with no handling | sem closer turn; status pelo objetor, tipicamente `unknown`. |
| Poor transcript | objeção ininteligível → não anotar; último sinal ininterpretável → `unknown`. |
| Missing timestamp | Canonical Call exige timestamps; episódio usa `segment_index`. |
| Overlapping segments | ordem por `segment_index`. |
| Contradictory evidence | §9.2 regras 4–5. |
| Partial resolution | MIXED → `partially_resolved`. |
| Call ends during objection | `unknown` salvo sinal substantivo anterior; "terminou no fim" derivado. |
| Lead agrees, later reopens | ep1 `resolved`; ep2 novo; padrão "resolução não durável" derivável. |
| Split objection | continuação em `objection_segment_ids` (§7.3). |
| Neutral ack after acceptance | não sobrescreve (§9.2). |
| Same category, different participants | episódios separados (§5.1). |

## 15. Migration v0 → v1

- **Coexistência (D1 APPROVED).** `ObjectionEvent` v0, id, extractor e eval v0 intactos;
  `ObjectionEpisode` é tipo novo e aditivo.
- **Lifting determinístico** (a implementar junto do contrato):
  `episode_from_event(e) → ObjectionEpisode(call_id=e.call_id, category=e.category,
  objection_segment_ids=(e.segment_id,), context_segment_ids=(), resolution_status="unknown")`.
- **Limitação:** super-segmenta (sem threading). No eval isso aparece como **FP** com rótulo
  diagnóstico `split_fragment` — penaliza precisão, como deve. P/R do v1 não é comparável ao
  do v0 (unidade diferente).
- Golden set de episódios é anotado diretamente em v1.

## 16. Rejected fields

`raised_by`, `anchor_segment_id` como campo separado, `started_at`, `ended_at`,
`lead_reaction`, fase por segmento (v1), `next_step`, texto/quote, char spans,
`reopens_episode_id`, proveniência por registro.

## 17. Deferred fields

`objection_subtype`, tipo de estratégia/função fina do closer (Strategy), `confidence`,
`severity`, link direto a `Deal`/`Outcome`, ligação cross-call de episódios.

## 18. Impact analysis

| Área | Impacto |
|---|---|
| `ObjectionEvent` v0 | nenhum |
| `RuleBasedObjectionExtractor` | nenhum; episódios via lifting |
| Synthetic eval v0 | nenhum; harness novo `evals/objection_episode_v1/` quando implementar |
| Future taxonomy | `category` reusa enum v0; subtype aditivo |
| Annotation Guidelines | este documento define unidade, fronteiras, particionamento e sinais de resolução; conteúdo das guidelines é de Otávio |
| Future LLM extractor | saída = este contrato; precisa threading, particionamento objeção/contexto, objetor e resolução; proveniência no run |
| Deal / Outcome Intelligence | sem mudança de schema; via `call_id → CallDealMatch → deal_id` |
| IDs | novo `ep_`; demais inalterados |
| Serialization | Pydantic JSON; `tuple` → array |
| Tests | futuros: contrato, grounding helper, lifting, matcher com os 2 cenários de sanidade §12.3 |
| Canonical Call / Participant roles / Agro parser / CRM matching | **nenhum** |

## 19. Decisions

| # | Decisão | Estado |
|---|---|---|
| D1 | Episode coexiste com Event v0 | **APPROVED** (Matheus) |
| D2 | id determinístico, sem UUID, eval por overlap, split/merge diagnósticos | **Direção APPROVED**; fórmula final (§10) aguarda sign-off de Matheus após esta revisão |
| D3 | Piloto de dupla anotação | **OPEN** — ver abaixo |
| D4 | Proveniência no run, não no registro | **APPROVED** (Matheus) |
| D5 | Stakeholder/decisor do lado do lead: equivalente a lead para análise de objeção? | **OPEN** — ver abaixo |
| D6 | `resolved`/`partially_resolved`/`unresolved`/`unknown` anotáveis e comercialmente úteis? | **OPEN** — Otávio (anotabilidade) + Gabriel (utilidade comercial). Não implementar antes. |
| D7 | Implementar o contrato | **BLOCKED** até D3 + D6 |
| D8 | ADR | Sim, **no momento da implementação** (D7): registrar D1/D2/D4 em `docs/decisions/` como contrato entre módulos. Não agora — D2 ainda sem sign-off final. |

**D3 — piloto (sem thresholds).** O que medir: §12.3–12.5 humano A × humano B (detection
P/R/F1, split/merge, anchor agreement, Jaccard de `O` e `E`, matriz e kappa de resolução).
Como: 3–5 calls reais autorizadas, dois anotadores independentes, mesmo algoritmo §12.2.
Inspeção: listar todo par não casado e toda discordância de resolução; classificar cada uma
(fronteira mesmo/novo episódio, particionamento objeção/contexto, objetor, categoria, sinal
de resolução, erro de transcript); ajustar regras onde a causa for ambiguidade da regra, não
do anotador. **Thresholds de go/no-go só depois de ver esses resultados.**

**D5 — decisor.** Um stakeholder/decisor pode ser comercialmente equivalente a lead para
análise de objeção, mas identidade e papel de participante pertencem à Canonical Call /
taxonomia de participantes e **não** são alterados em AC-47. Enquanto aberto: só
`role="lead"` ancora; objeções de participantes `other` ficam sem episódio (lacuna de
cobertura documentada, não inferida).

## 20. Definition of Done (desta proposta)

- [x] Auditoria do v0 contra o código.
- [x] Definição de episódio, fronteiras e objetor.
- [x] Evidence model com alternativas comparadas (A/B/C).
- [x] Resolução por último sinal substantivo, com precedência e exemplos sintéticos.
- [x] Matching, TP/FP/FN convencionais, split/merge diagnósticos, cenários de sanidade.
- [x] Recheck de ID com limitações declaradas.
- [x] 17 edge cases obrigatórios + 3 adicionais.
- [x] Migração sem quebrar v0; impacto por área.
- [x] Review Domain / Evaluator / Architecture (rev. 2): APPROVE.
- [ ] Sign-off D2; D3, D5, D6 resolvidos.
- [ ] (Próxima task) Implementação + ADR, só após D3 + D6.
