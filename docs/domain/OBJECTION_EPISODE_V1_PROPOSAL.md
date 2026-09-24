# ObjectionEpisode v1 — Proposal (AC-47)

Status: **PROPOSAL rev. 4 — não implementado.** Nenhum código muda com este documento.
Contrato vigente continua sendo `ObjectionEvent` v0 (`docs/domain/OBJECTION_MODEL.md`,
`src/closer_ai/domain/objection.py`).

Histórico de revisões:

- rev. 2: resolução por evidência substantiva, episódio do objetor, TP/FP/FN convencionais,
  evidência objeção vs. contexto.
- rev. 3: listas de evidência **não** são função exclusiva (§7); recorrência ≠ reabertura
  (§5.2); resposta substantiva independente de segmentação (§9); regra de âncora para
  objeção partida (§5.3); condição de closure explícita (§5.1); matching
  maximum-cardinality-first (§12.2); `closer_segment_count` (§8); métricas com conjunto vazio
  (§12.6).
- rev. 4: "aspecto" operacional para MIXED vs REJECT (§9.1); mesma categoria em fio aberto
  (§4, §5.1); pinning da segmentação da Call de origem no run (§11, §12.0); parked threads,
  on-topic funcional, logística e apartes de terceiros na closure (§5.1); ordem/invalidade
  (§12.1); "terminou no fim da call" como julgamento (§11); `deal_id` só com MATCHED (§11);
  métricas com gold vazio (§12.6); pendência como pergunta D6 (§9.1, §19). Schema continua
  com 7 campos.

Pergunta que este documento responde:

> Qual é o menor contrato `ObjectionEpisode` v1 capaz de suportar anotação humana, grounding,
> evals e futura Outcome Intelligence sem inflar o domínio prematuramente?

Resposta curta: **7 campos armazenados** (`schema_version`, `episode_id`, `call_id`,
`category`, `objection_segment_ids`, `context_segment_ids`, `resolution_status`). Objetor,
âncora, tempos, recorrência e contagens estruturais são **derivados**. Função semântica das
falas (reação, autocorreção, clarificação, argumento) é **julgamento**, não derivação.

## 1. Problem

`ObjectionEvent` v0 responde "o lead expressou resistência da categoria X neste segmento?".
Isso é detecção pontual. Outcome Intelligence precisa de uma unidade maior:

```
objeção do lead → turnos do closer → respostas do mesmo lead → estado ao fim do fio
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

1. **Menção ≠ episódio.** Lead repete "tá caro" no mesmo fio → 2 eventos.
2. **Sem turnos do closer, sem resposta do lead, sem estado final** (lacuna em
   `docs/context/OPEN_QUESTIONS.md`).
3. **Eval por id exato** é frágil para fronteiras multi-segmento.
4. **Objeção partida entre segmentos** não cabe em um segmento.
5. **Speaker role e segmentação ≠ função conversacional.** Uma mesma fala pode conter
   objeção e autocorreção; uma resposta pode ocupar vários segmentos; fala do closer pode ser
   clarificação, argumento ou citação. Nenhuma regra estrutural (role, lista, fronteira de
   segmento) determina função sozinha.

## 4. Episode definition

> Um **ObjectionEpisode** é o fio de conversa, **dentro de uma única Call**, em que **um
> participante** (o **objetor**, `role="lead"`) expressa resistência de **uma** categoria, mais
> o que é dito sobre essa resistência, **até a closure** (§5.1) ou o fim da call.

Invariantes de domínio:

- **Intra-call.** Nunca atravessa calls. Ligação entre calls é derivação Deal-level via
  `CallDealMatch`, nunca campo do episódio.
- **Uma categoria, um objetor.** Objetor = `speaker_id` da âncora; derivado.
- **Objetor sempre `role="lead"`** na `Call` (TD-14: `unknown` nunca vira lead por inferência).
- **Episódio = fio por (objetor, categoria), não por "preocupação".** Enquanto o fio está
  aberto ou parked (§5.1):
  - nova **categoria** → novo episódio;
  - novo **objetor** → novo episódio;
  - mesma categoria + mesmo objetor → **continua no mesmo episódio**, mesmo que seja uma
    manifestação específica nova da categoria.

  Exemplo sintético (fio `price` aberto):

  ```
  s50 Lead:   "A mensalidade está ok."
  s51 Closer: "Ótimo, e sobre a implantação..."
  s52 Lead:   "Mas a taxa de implantação está alta."
  ```

  s52 entra em `context_segment_ids` do episódio `price` aberto; é uma resposta REJECT (a
  preocupação da categoria continua ativa) → `unresolved`. **Não** é reabertura nem novo
  episódio. Se o fio já tivesse fechado, s52 ancoraria um novo episódio (recorrência, §5.2).
  Separar preocupações da mesma categoria exige subtipo/relação semântica — deferred (§17).
- **Resolução é in-call e do objetor.** Não é outcome do Deal e não o prevê.

## 5. Boundary rules

| # | Pergunta | Regra |
|---|---|---|
| 1 | Quando começa? | Na **âncora** (§5.3). |
| 2 | Quando termina? | Na **closure** (§5.1) ou no fim da call. O último segmento do episódio é o maior `segment_index` entre objeção e contexto. |
| 3 | Mesma objeção de novo, mesmo objetor | **Antes da closure** → mesmo episódio (nova resposta do objetor). **Depois da closure** → novo episódio. Tempo não é critério. |
| 4 | Recorrência / reabertura | §5.2. |
| 5 | Duas objeções na mesma fala | Categorias diferentes → **dois episódios**, mesma âncora. Mesma categoria → **um** episódio. |
| 6 | Turnos do closer | Segmentos do closer em `context_segment_ids`. |
| 7 | Handling multi-passo? | **Não medido em v1.** Só `closer_segment_count` (estrutural). Segmento de transcript ≠ passo conversacional; handling steps/Strategy deferred (§8). |
| 8 | Resposta do lead | Respostas substantivas do objetor (§9.1), em qualquer segmento do objetor no episódio. |
| 9 | Resolution | §9. |
| 10 | Call termina antes de resolução | Fim da call fecha todos os fios; status pelo §9 (tipicamente `unknown`). |

Desempate geral: **na dúvida entre mesmo/novo episódio, mesmo episódio.**

### 5.1 Closure condition

Estados conceituais de um fio (anotação mental, **nenhum campo armazenado**):

```
OPEN ──(deferral explícito)──► PARKED ──(retomada)──► OPEN
OPEN ──(closure)──► CLOSED
PARKED ──(abandono explícito | fim da call)──► CLOSED
```

Mantém-se mentalmente o conjunto de fios OPEN e PARKED da call.

**Closure de fios OPEN:** um segmento **closure-relevant** (definição abaixo) cujo assunto
**não é nenhum dos fios OPEN/PARKED** e que **não expressa nova objeção** fecha **todos** os
fios OPEN naquele ponto. Fios PARKED **não** são fechados por isso. O fim da call fecha todos.

**Closure é julgada em retrospecto** (mesmo princípio da âncora, §5.3): o assunto de um
segmento é decidido olhando o que vem depois, não só a ordem de fala. Um segmento cujo
assunto é, na sequência imediata (antes de qualquer outro segmento closure-relevant),
retomado pelo objetor como preocupação da **mesma categoria** de um fio OPEN/PARKED faz parte
desse fio — é contexto, não closure. Ex.: §4, s51 ("e sobre a implantação...") seguido de s52
("Mas a taxa de implantação está alta.") → s51 é contexto do fio `price`, o fio não fechou.
Se o que vem depois não retoma o fio, o segmento é closure-relevant.

**Não são closure-relevant** (nunca fecham nada):

1. **Não substantivos:** interjeições e backchannels ("ok", "tá", "uhum", "sim", "certo",
   "sim?"), cumprimentos, ruído.
2. **Logística da call:** "está me ouvindo?", "vou compartilhar a tela", "só um minuto",
   "caiu o áudio", mesmo tendo conteúdo proposicional.
3. **Apartes de terceiros que não mudam o fio comercial:** ex. "Preciso sair às 15h." de
   outro participante, quando a conversa principal segue no mesmo assunto.
4. **Segmentos que servem diretamente à resolução de um fio aberto** — são **on-topic** desse
   fio, mesmo que superficialmente sobre outro assunto: perguntar volume para calcular ROI
   diante de objeção de preço; mostrar tabela de preços; perguntar tamanho da implantação
   para justificar o preço. Entram em `context_segment_ids` do fio que servem.

**PARKED:** um **deferral explícito** sobre o fio — "vamos voltar nisso", "depois retomamos",
"deixa eu responder isso depois", "vamos ver X primeiro e depois voltamos ao preço" — não
fecha o fio; ele fica PARKED. Um fio PARKED continua sendo o mesmo episódio até ser:

- **retomado** (qualquer participante volta ao assunto: volta a OPEN, mesmo episódio);
- **explicitamente abandonado** ("esquece o preço, não é problema") → CLOSED;
- ou **fim da call** → CLOSED.

Deferral precisa ser explícito. Mudar de assunto sem anunciar retorno não é deferral.

Outras regras:

- Um segmento que expressa **nova objeção** (nova **categoria** ou novo **objetor**, §4)
  abre um fio novo e **não** fecha os outros. Mesma categoria + mesmo objetor com fio
  OPEN/PARKED **não** é nova objeção: é contexto desse fio (§4).
- Alternar entre fios OPEN (preço ↔ prazo) **não** fecha nenhum deles.

Counterexample resolvido (parked):

```
s60 Lead:   "Preço está alto."                                     → âncora price
s61 Closer: "Vamos olhar implantação primeiro e depois volto no preço." → PARKED
s62..s70    (discussão de implantação)                             → não fecha price
s71 Closer: "Voltando ao preço, podemos parcelar."                 → retomada, contexto
s72 Lead:   "Com esse parcelamento dá."                            → ACCEPT
```

Um episódio `price`: `objection_segment_ids = (s60)`, `context_segment_ids = (s61, s71, s72)`,
`resolved`. s62..s70 não entram (não servem à resolução do preço).

Por que "fecha todos os OPEN" e não "só o abandonado": decidir qual fio foi abandonado exige
julgar intenção por fio; "mudou para assunto fora de todos os fios, sem deferral" é um único
julgamento por segmento. Os casos em que isso fecha cedo demais são exatamente os que o D3
inspeciona como `premature_closure` (§19).

**Reversão imediata** (sem closure no meio) fica **no mesmo episódio**:

```
s20 Lead:   "Esse desconto resolve."
s21 Lead:   "Na verdade, incluindo imposto ainda fica caro."
```

Mesmo episódio. Sem turno substantivo de outro entre s20 e s21, é **uma** resposta (§9.1)
com reafirmação da preocupação geral ("ainda fica caro"; imposto é nova causa, não aspecto,
§9.1) → REJECT → `unresolved`. Se o closer tivesse falado algo
substantivo entre elas, seriam duas respostas (ACCEPT, REJECT) e a última venceria (§9.2) —
mesmo resultado. Não existe "episódio resolvido + novo episódio" sem closure entre as falas.

### 5.2 Recorrência ≠ reabertura

- **Derivável em v1:** **same-category recurrence by same objector** — existe episódio
  anterior, na mesma call, com mesmo objetor e mesma categoria.
- **Não derivável em v1:** **reopening** (a *mesma preocupação* voltou) e **non-durable
  resolution**. Exigem relação semântica explícita entre as duas preocupações.

Exemplo sintético:

```
Ep1 Lead: "A mensalidade está alta demais."  → ... → resolved
(closure: conversa vai para implantação)
Ep2 Lead: "A taxa de implantação está alta demais."
```

Ep1 e Ep2 são `price` do mesmo objetor → **recurrence**. **Não** é reabertura: são
preocupações diferentes. v1 não afirma reabertura nem resolução não durável. Vínculo
semântico entre episódios: deferred (§17), sem campo novo agora. O episódio anterior nunca
é reescrito.

### 5.3 Anchor rule

> `anchor_segment_id` (= `objection_segment_ids[0]`) é o **primeiro segmento do objetor que
> pertence a uma expressão de objeção conjuntamente suficiente**.

- O primeiro segmento sozinho **pode ser incompleto**; a categoria é groundada no **conjunto**
  `objection_segment_ids`, não na âncora isolada.
- A âncora é o **início da sequência de evidência**, não necessariamente o primeiro segmento
  que sozinho permite classificar a objeção.
- **Introdução aparentemente neutra pertence à sequência** quando: (a) é do objetor; (b) é
  sintaticamente incompleta (lead-in sem predicado: "Sobre o preço...", "Então, o valor...");
  (c) é completada pela fala seguinte do objetor que expressa a resistência; e (d) entre elas
  só há segmentos não substantivos de outros (§5.1).
- **Não pertence** quando é completa em si ("Tenho uma dúvida sobre o preço.", "Quanto fica
  o parcelamento?") — pergunta ou comentário neutro completo não é objeção. Nesse caso a
  âncora é a fala que expressa a resistência.

Exemplo obrigatório:

```
s10 Lead:   "Sobre o preço..."
s11 Closer: "Sim?"
s12 Lead:   "...ficou acima do nosso orçamento."
```

| Item | Valor | Por quê |
|---|---|---|
| anchor | `s10` | lead-in incompleto do objetor, completado por s12, só um backchannel no meio |
| `objection_segment_ids` | `(s10, s12)` | juntos formam a expressão suficiente |
| `context_segment_ids` | `(s11)` | prompt do closer que elicita a continuação faz parte do fio |
| category grounding | `price`, groundado em s10+s12 conjuntamente | s10 dá o tópico, s12 dá a resistência; nenhum sozinho basta |
| id | `hash(call_id, s10, "price")` | D2 |

Corrigir a âncora (ex.: anotador inclui/remove s10) muda `episode_id` — limitação aceita em D2.

### 5.4 Objetor e múltiplos participantes

**Regra:** um episódio pertence ao participante que ancora a objeção. Sem campo `raised_by`.

| Caso | Regra |
|---|---|
| Múltiplos leads | cada participante `role="lead"` com resistência própria ancora o **seu** episódio |
| Mesma categoria, participantes diferentes | episódios separados. Ex. sintético: Financeiro: "Não conseguimos aprovar esse preço." / Técnico: "Pra mim o preço está ok." → 1 episódio `price` do Financeiro; o Técnico é contexto e **não** o resolve |
| Concordância de outro participante com a objeção ("Concordo, está caro.") | resistência própria → novo episódio ancorado nele |
| Discordância de outro participante | contexto; nunca sinal de resolução do objetor |
| Declaração coletiva do objetor ("A gente não consegue pagar.") | atribuída ao speaker do segmento |
| Declaração coletiva de terceiro ("Pra nós está resolvido.") | contexto; não resolve |
| `objection_segment_ids` | todos com o mesmo `speaker_id` da âncora |
| Fica **UNKNOWN** | posição do objetor quando só terceiros reagem (→ `unknown`); decisor com `role="other"` (D5 — não ancora hoje; lacuna aceita); speaker_id que funde pessoas por erro de diarização (problema da Call) |

## 6. Field proposal

Legenda: Obs = diretamente observável; Inf = inferido; Ann = anotável; Gr = groundable;
Req = obrigatório; MVP = entra no v1.

| Field | Purpose | Obs? | Inf? | Ann? | Gr? | Req? | MVP? | Decisão |
|---|---|---|---|---|---|---|---|---|
| `schema_version` | versionar contrato | — | — | — | — | default | sim | **KEEP** |
| `episode_id` | identidade/idempotência | — | derivado | não | — | sim | sim | **KEEP** (§10) |
| `call_id` | rastrear até a Call | sim | — | sim | sim | sim | sim | **KEEP** |
| `category` | taxonomia (≈ `objection_family`) | não | sim | sim | via objeção | sim | sim | **KEEP**, enum v0 |
| `objection_segment_ids` | segmentos necessários para groundar a expressão da objeção | segmentos sim; seleção não | seleção | sim | sim | sim, ≥ 1 | sim | **KEEP** (§7) |
| `context_segment_ids` | segmentos adicionais necessários para entender o episódio | segmentos sim; seleção não | seleção | sim | sim | sim, pode ser `()` | sim | **KEEP** (§7) |
| `resolution_status` | posição do objetor ao fim do episódio | não | **sim** | sim | via segmentos do objetor | sim, sem default | sim | **KEEP** (§9) |
| `raised_by` | objetor | sim | — | — | sim | — | não | **REJECT**: derivado da âncora |
| `anchor_segment_id` | âncora | sim | — | sim | sim | — | não | **REJECT como campo**: = `objection_segment_ids[0]` |
| `started_at` / `ended_at` | tempo | sim | — | — | sim | — | não | **REJECT**: derivados |
| `handling_steps[]` / multi-step | estratégia | não | sim | não confiável hoje | — | — | não | **DEFER** (Strategy); só `closer_segment_count` derivado |
| `lead_reaction` / `resolution_evidence_segment_ids` | evidência de resolução | não | sim | sim | — | — | não | **REJECT**: qualquer segmento do objetor no episódio pode ser evidência (§7, §9) |
| per-segment phase | função por segmento | não | sim | a validar | sim | — | não | **REJECT em v1** (§7.1 B) |
| `reopens_episode_id` | vínculo semântico entre episódios | não | sim | a validar | — | — | não | **DEFER** (§5.2) |
| `next_step` | próximo passo | parcial | sim | sim | sim | — | não | **REJECT**: é `Commitment` |
| `objection_subtype` | taxonomia fina | não | sim | ainda não | — | — | não | **DEFER** |
| `confidence` | incerteza | — | — | não | — | — | não | **DEFER** |
| proveniência | quem/qual versão produziu | — | — | — | — | — | não | **REJECT por registro** — no run (D4) |

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
são grounding (§12.1).

## 7. Evidence contract

### 7.1 Alternativas avaliadas

| Opção | Estrutura | Decisão |
|---|---|---|
| A | `anchor_segment_id` + `objection_evidence_segment_ids` + `followup_segment_ids` | rejeitada — é C com um campo redundante |
| B | `episode_segment_ids` + fase por segmento | rejeitada para v1 — exige taxonomia de fases com estudo de concordância próprio, e mesmo assim um segmento pode ter mais de uma fase (P0-1); candidata a v2 com Strategy |
| **C** | `objection_segment_ids` (âncora = `[0]`) + `context_segment_ids` | **escolhida** |

### 7.2 Semântica das listas (grounding, não função)

- **`objection_segment_ids`** = segmentos **necessários para groundar a expressão da
  objeção** (âncora + continuação, §5.3). Todos do objetor.
- **`context_segment_ids`** = segmentos **adicionais necessários para entender o episódio**
  depois ou ao lado da evidência da objeção: turnos do closer sobre o fio, respostas do
  objetor, falas de terceiros sobre o fio, prompts como "Sim?" que elicitam continuação.
- Cada segmento aparece **no máximo uma vez** por episódio: se é necessário para groundar a
  objeção, vai para `objection_segment_ids`, **mesmo que também contenha outra coisa**.
- Um segmento pode aparecer em mais de um episódio (turno do closer respondendo a duas
  objeções; duas categorias na mesma fala).

**Membership em lista + speaker role NÃO determinam sozinhos a função semântica da fala.**
Um segmento em `objection_segment_ids` pode também conter autocorreção ou aceitação; um
segmento do objetor em contexto pode ser resposta, reiteração ou elaboração; um segmento do
closer pode ser clarificação, argumento ou citação. Função semântica é julgamento (§11).

**Evidência de resolução** pode vir de **qualquer segmento do objetor incluído no episódio**,
inclusive de um segmento de `objection_segment_ids`. Nenhum campo extra.

Exemplo sintético (P0-1, objeção + resolução na mesma fala):

```
s30 Lead: "Esse preço mensal está muito alto — espera, calculei para uma licença.
           Para dez licenças cabe no orçamento; então o preço está resolvido."
```

`objection_segment_ids = (s30)`, `context_segment_ids = ()`, âncora = s30, `price`.
Resposta substantiva (§9.1): a parte após a expressão de resistência, dentro de s30 → ACCEPT
→ `resolved`.

### 7.3 Fatos estruturais deriváveis (não semânticos)

Dado o episódio e a `Call`: objetor; âncora; segmentos do objetor no episódio; segmentos do
closer no contexto; segmentos de terceiros no contexto; `closer_segment_count`; início/fim.
São contagens e partições por speaker — **não** afirmam função ("handling", "reação").

### 7.4 Outras escolhas

- **Char spans:** não. P0-1 mostra que uma fala pode ter duas funções, mas a função é
  julgada sobre o segmento inteiro; spans exigiriam estabilidade de texto/ASR que não temos.
- **Texto/quote:** não (duplicaria `TranscriptSegment.text`; risco de PII).
- **Timestamps:** não; ordem por `segment_index`, robusta a crosstalk.

## 8. Handling model

- **Derivado estrutural:** `closer_segment_count` = nº de segmentos do closer em
  `context_segment_ids`; `has_closer_segment` = count > 0.
- **Não medido em v1:** número de passos de handling, tipo de estratégia, clarificação vs.
  argumento. Segmento de transcript ≠ passo conversacional. Strategy deferred.

## 9. Resolution semantics

Julgado ao fim do episódio, **só com falas do objetor** dentro do episódio.

### 9.1 Resposta substantiva (unidade de julgamento)

1. A **expressão inicial da resistência** (o conteúdo que torna a fala uma objeção) **não** é
   resposta.
2. Uma **resposta** é todo o conteúdo do objetor sobre o fio **depois** da expressão inicial
   — inclusive o restante do mesmo segmento (autocorreção, P0-1).
3. Uma resposta termina quando **outro participante faz um turno substantivo** (§5.1). Assim,
   uma resposta pode ocupar **vários segmentos consecutivos do objetor**, intercalados só por
   backchannels de outros. **Fronteira de segmento não é fronteira de resposta.**
4. Cada resposta recebe **um** rótulo:

| Rótulo | Definição | Exemplos sintéticos |
|---|---|---|
| **ACCEPT** | a preocupação é dada como atendida, ou próximo passo que pressupõe a objeção superada | "Esse desconto resolve completamente o problema de preço."; "Então pode mandar o contrato com esse valor." |
| **REJECT** | a preocupação **persiste ou fica explicitamente em aberto**: rejeição da resposta, reiteração, ou pendência declarada | "Continua caro pra mim."; "Ainda preciso verificar se consigo pagar." |
| **MIXED** | **dentro da mesma resposta**, um aspecto claramente aceito **e** outro aspecto (definição operacional abaixo) pendente | "O preço total está ok, mas a entrada ainda não cabe." |
| **NEUTRAL** | só reconhecimento, sem conteúdo sobre o ponto | "ok", "tá", "uhum", "sim", "certo" |
| **OFF_CATEGORY** | só conteúdo sobre outro assunto | — |
| **UNKNOWN** | há conteúdo sobre o ponto, mas não é interpretável (ilegível, ironia indecidível) | — |

**Independência de segmentação** (P1-3):

```
A) s40 Lead: "O preço total está ok, mas a entrada ainda não cabe."
B) s40 Lead: "O preço total está ok."
   s41 Lead: "Mas a entrada ainda não cabe."
```

Em B, não há turno substantivo de outro participante entre s40 e s41 → **uma** resposta.
A e B → MIXED → `partially_resolved`.

**Aspecto (definição operacional):**

> Um **aspecto** é um subcomponente da preocupação comercial que pode ser satisfeito
> **independentemente** de outro subcomponente.

Exemplos de pares de aspectos distintos: mensalidade vs. taxa de implantação; preço total
vs. entrada; prazo de contrato vs. cláusula de cancelamento.

**Não** são aspectos distintos: uma **nova causa** para a mesma preocupação geral (desconto
vs. imposto, quando o que o lead reafirma é "o preço continua caro"); o mesmo valor visto de
outro ângulo ("por mês" vs. "no ano").

**Regra de reafirmação:** se o objetor **reafirma a preocupação geral** — "continua caro",
"ainda fica caro", "não cabe no orçamento" — é **REJECT** (revogação), **mesmo que mencione
uma nova causa**.

**MIXED só existe quando todas valem:**

1. um aspecto foi **claramente aceito**;
2. **outro aspecto diferente** (pela definição acima) continua pendente;
3. ambos pertencem à preocupação da **mesma categoria** do episódio;
4. estão na **mesma resposta** (§9.1 item 3).

| Resposta do objetor | Rótulo | Por quê |
|---|---|---|
| "O preço total está ok, mas a entrada ainda não cabe." | **MIXED** | total aceito; entrada é outro aspecto, pendente |
| "A mensalidade está ok; a taxa de implantação ainda está alta." (mesma resposta) | **MIXED** | aspectos independentes |
| "O prazo de 24 meses está ok, mas a multa de cancelamento me preocupa." (categoria do episódio cobre os dois) | **MIXED** | aspectos independentes |
| "Esse desconto resolve. Na verdade, incluindo imposto ainda fica caro." | **REJECT** | reafirma a preocupação geral ("ainda fica caro"); imposto é nova causa, não aspecto |
| "O desconto ajuda, mas continua não cabendo no orçamento." | **REJECT** | reafirmação geral |
| "Com desconto fica ok por mês, mas no ano ainda é caro." | **REJECT** | mesmo valor, outro ângulo; reafirma "caro" |

**Residual vs. revocation:**

- **Residual** = MIXED como definido acima.
- **Revogação dentro da mesma resposta** = aceitação seguida de reafirmação geral → REJECT.
- **Revogação posterior** = uma resposta posterior contradiz uma anterior → não é MIXED;
  aplica-se a precedência temporal (§9.2).

**"Ainda preciso verificar se consigo pagar."** — regra **provisória** v1: declaração de que
a preocupação **ainda está pendente** é tratada como persistência → **REJECT** →
`unresolved` quando sozinha; **MIXED** quando na mesma resposta após aceitar outro aspecto.
Nunca UNKNOWN (o conteúdo é interpretável). **Pergunta explícita para D6 (§19):** a semântica
comercial/de anotação quer isso como `unresolved`/REJECT, `partially_resolved`, `unknown` ou
um estado futuro distinto ("pending")? Sem resposta final antes de Gabriel + Otávio; sem
mudança de schema agora.

### 9.2 Precedência temporal entre respostas

1. Descartar respostas NEUTRAL e OFF_CATEGORY. **Nunca sobrescrevem** uma resposta
   substantiva anterior.
2. Nenhuma resposta restante → **`unknown`**.
3. Caso contrário, vale a **última** resposta restante: ACCEPT → `resolved`; REJECT →
   `unresolved`; MIXED → `partially_resolved`; UNKNOWN → `unknown` (sem recuar para uma
   anterior).
4. Reversão (ACCEPT → REJECT ou REJECT → ACCEPT) sem closure no meio: mesmo episódio
   (§5.1), vale a última.
5. Falas de **terceiros** (outro lead, closer) nunca entram.

| Respostas do objetor (em ordem) | Status |
|---|---|
| "Esse desconto resolve completamente o problema de preço." / (closer: "Ótimo.") / "Uhum." | `resolved` |
| "Uhum." / "Tá." | `unknown` |
| "Esse desconto resolve." / "Na verdade, incluindo imposto ainda fica caro." (sem turno de outro no meio) | uma resposta, reafirmação geral → REJECT → `unresolved` |
| "A mensalidade está ok; a taxa de implantação ainda está alta." | uma resposta MIXED → `partially_resolved` |
| "A mensalidade está ok." / (closer: "e sobre a implantação...") / "Mas a taxa de implantação está alta." | ACCEPT, depois REJECT (§4) → `unresolved` |
| "Preço está alto." / closer parqueia / ... / closer retoma / "Com esse parcelamento dá." | `resolved` (§5.1) |
| "Esse desconto resolve." / (closer argumenta sobre imposto) / "Ainda fica caro." | ACCEPT, depois REJECT → `unresolved` |
| "Continua caro." / (closer argumenta) / "Com esse prazo resolve." | `resolved` |
| "O preço total está ok." / "Mas a entrada ainda não cabe." | uma resposta MIXED → `partially_resolved` |
| "Ainda preciso verificar se consigo pagar." | REJECT → `unresolved` |
| Objeção + autocorreção na mesma fala (s30, §7.2) | ACCEPT → `resolved` |
| Nenhuma resposta; closer muda de assunto | `unknown` |
| Técnico: "Pra mim está ok." (objetor = Financeiro, calado) | `unknown` |

Regras adicionais:

- **Ausência de turno do closer não implica `unresolved`.**
- **Imutável e local:** recorrência posterior é novo episódio; este não muda.
- `RuleBasedObjectionExtractor` não tem sinal para julgar resolução → sempre `unknown`.
- Definições e utilidade comercial dos quatro valores: **D6 (aberta)**.

## 10. ID / dedup strategy (D2 APPROVED)

```
episode_id = "ep_" + sha256(json.dumps(["objection_episode", call_id, anchor_segment_id, category]))[:24]
anchor_segment_id = objection_segment_ids[0]
```

Mesma técnica de `closer_ai.normalization.ids` e do v0; validator re-checa a derivação.
UUID/run-dependent: rejeitado.

**Limitações aceitas por Matheus (D2):**

- correção da âncora muda o id;
- objeção repetida com nova âncora (recorrência) gera novo id;
- categorias diferentes na mesma âncora têm ids diferentes;
- mesma categoria na mesma âncora colapsa num episódio;
- contexto e resolução não entram no id;
- versões diferentes de extractor só compartilham id quando concordam em âncora e categoria.

Notas:

- Objetor entra **implicitamente** via âncora (um segmento tem um `speaker_id`).
- Dois episódios da mesma categoria não compartilham âncora (colapsam).
- Eval compara por **overlap** (§12), não por id — correções de âncora não quebram métricas.
- Quando existir storage: correção de âncora = delete + insert, nunca update in-place.
  Golden set é versionado como lote.
- Namespace `ep_` nunca colide com `obj_`. Call/Deal/Lead IDs inalterados.

## 11. Observability vs inference

| Classe | Itens |
|---|---|
| **DIRECT EVIDENCE** | `call_id`; existência dos segmentos referenciados; `speaker_id`, `role`, `text` desses segmentos (vivem na Call) |
| **DERIVED DETERMINISTICALLY** | `episode_id`; âncora; objetor; primeiro/último segmento e tempos (dados as listas); partição estrutural por speaker (§7.3); `closer_segment_count`; same-category recurrence by same objector (dado o conjunto de episódios); `deal_id` **somente** quando o match corrente da call é `matched` (convenção de `matching.py`, ver abaixo) |
| **HUMAN JUDGMENT** (golden set) | que há objeção; `category`; quais segmentos entram e em qual lista; âncora (§5.3); closure, deferral/parked, on-topic funcional (§5.1); "fio ainda aberto/parked quando a call terminou"; fronteira de resposta, aspecto e rótulo de cada resposta (§9.1); `resolution_status`; função semântica de qualquer fala |
| **MODEL INFERENCE** (extractor) | os mesmos itens de HUMAN JUDGMENT quando produzidos por extractor |
| **NÃO REPRESENTADO em v1** | reopening; non-durable resolution; estado parked; "terminou no fim da call"; handling steps; estratégia |

**"Terminou no fim da call"** não é derivável: o ponto de closure não é armazenado, e o
último segmento do episódio não é o ponto em que o fio fechou. É julgamento ("o fio estava
OPEN/PARKED quando a call acabou?") e **não é armazenado em v1**.

**Deal linkage:** `deal_id` canônico derivado só existe quando o **match corrente** da
call é `matched`, pela consulta já definida em `src/closer_ai/domain/matching.py` ("latest row by created_at with status='matched'"); este documento não redefine essa regra. Linhas `ambiguous`
(várias linhas candidatas), `unmatched` (sem `deal_id`), `rejected` ou `manual_review` **nunca
produzem** `deal_id` canônico derivado; sem linha `matched`, os episódios dessa call não têm
deal. Nenhuma mudança em `Deal`
ou `CallDealMatch`.

**Proveniência (D4 APPROVED):** pertence ao **extraction/eval run**, não ao episódio:

- tipo do produtor (human / rule-based / LLM), versão do extractor, modelo, prompt;
- versão do schema de `ObjectionEpisode`;
- **identidade da Call de origem, por call** (P1-C):
  - `normalizer_version` — versão do parser/normalizer que materializou a Call;
  - `canonical_call_schema_version` — `Call.schema_version`;
  - `segment_sequence_hash` — sha256 sobre `json.dumps` da lista ordenada de
    `[segment_id, segment_index, speaker_id, role do speaker, sha256(text)]`.

Por que essa escolha (e não só `source_call_manifest_id`): o manifest identifica o **dado
bruto**, não o **resultado da normalização** — um parser novo sobre o mesmo manifest mudaria
a segmentação sem mudar o manifest. `segment_id = hash(call_id, segment_index)`
(`normalization/ids.py`) é posição, não conteúdo; só um hash do conteúdo segmentado detecta
que o mesmo id passou a apontar para outra fala. `normalizer_version` é diagnóstico (por que
mudou); o hash é a verificação (se mudou). `role` entra porque a validade da âncora depende
dele (TD-14 pode mudar a resolução de roles). Timestamps ficam fora: o episódio não depende
deles. O texto entra só como hash — nenhuma cópia de transcrição na proveniência. Tudo é
calculável a partir da `Call` existente: **nenhuma mudança na Canonical Call**.

## 12. Grounding requirements e evaluation

### 12.0 Evaluation preconditions (source Call)

> Dois runs de anotação/extração **NÃO PODEM** ser comparados se foram produzidos contra
> segmentações diferentes da Call de origem.

- Para cada call, o evaluator compara o `segment_sequence_hash` (§11) dos dois runs, e ambos
  contra a `Call` atualmente materializada.
- Divergência → o evaluator **recusa** a comparação daquela call (erro explícito, nunca
  métrica parcial silenciosa) e reporta quais calls foram recusadas.
- Remédio: rematerializar a extração e/ou reanotar contra a segmentação atual. Episódios
  nunca são "migrados" entre segmentações por índice.
- Run sem a proveniência de origem → mesma recusa.

### 12.1 Grounding (cross-object, fora do modelo)

1. `call_id` == `Call.call_id`; todo segment id resolve para segmento dessa Call.
2. Âncora falada por participante `role == "lead"`.
3. Todos os `objection_segment_ids` têm o mesmo `speaker_id` da âncora.
4. **Ordem é semântica:** `objection_segment_ids[0]` é a âncora e deriva o `episode_id`;
   ambas as listas devem estar na ordem de `segment_index` da Canonical Call; todo segmento
   de contexto tem índice > índice da âncora. O modelo isolado não consegue checar isso
   (ids são hashes), por isso é grounding obrigatório.

**Episódio inválido:** falhar qualquer regra desta seção (ou §12.0) torna o episódio
**INVALID**. Episódio inválido **não é persistido, não é avaliado e não é re-derivado**
(nenhuma reordenação ou correção automática de âncora/id); é reportado como erro do run
(conta na grounding rate, §12.5).
5. Dentro de um run, `episode_id` é único (nenhum par de episódios com mesma call, âncora e
   categoria). Duplicata = saída inválida do run, reportada, não deduplicada em silêncio.
   Isso garante que, por partição, âncoras são únicas e o desempate de §12.2 é uma ordem
   total.

### 12.2 Episode matching (contrato do evaluator)

Notação: `O(e)` = `objection_segment_ids`; `E(e)` = `O(e) ∪ context_segment_ids`;
`obj(e)` = objetor. Mesmo algoritmo para pred × gold e humano A × humano B (A como
referência).

1. **Partição:** `(call_id, category, obj)`. Partições diferentes nunca casam.
2. **Candidato:** `(g, p)` só se `O(g) ∩ O(p) ≠ ∅`.
3. **Score:** Jaccard(`E(g)`, `E(p)`), comparado como **fração exata** (não float).
4. **Atribuição 1-para-1, por partição, em ordem lexicográfica de objetivos:**
   1. **maximizar o número de pares** (maximum cardinality matching);
   2. entre essas, **maximizar a soma dos scores**;
   3. entre essas, **maximizar a soma de Jaccard(`O(g)`, `O(p)`)**;
   4. desempate final: a atribuição cuja lista de pares
      `(índice da âncora de g, índice da âncora de p)`, ordenada, é **lexicograficamente
      menor**.

   Implementável como assignment problem padrão (ex.: max-weight bipartite com peso
   dominado pela cardinalidade); algoritmo concreto fica para a implementação.

**Por que não greedy** (counterexample):

| Par | Score |
|---|---|
| g1–p1 | 0.9 |
| g1–p2 | 0.8 |
| g2–p1 | 0.7 |
| g2–p2 | não candidato |

Greedy aceita g1–p1 e não sobra par válido para g2/p2 → TP=1, FP=1, FN=1. Maximum
cardinality aceita g1–p2 e g2–p1 → TP=2. Greedy subestimaria TP artificialmente.

### 12.3 TP / FP / FN

- **TP** = pares casados. **FP** = toda predição não casada. **FN** = todo gold não casado.
  Sem exceção para fragmentos ou absorvidos.
- P = TP/(TP+FP); R = TP/(TP+FN); F1 convencional.

Sanidade (obrigatória no harness futuro):

| Cenário | TP | FP | FN | P | R | F1 |
|---|---|---|---|---|---|---|
| 10 gold, 1 pred gigante cobrindo todos | 1 | 0 | 9 | 1.0 | 0.1 | 0.18 |
| 1 gold, 10 preds fragmentadas | 1 | 9 | 0 | 0.1 | 1.0 | 0.18 |
| counterexample greedy acima | 2 | 0 | 0 | 1.0 | 1.0 | 1.0 |

### 12.4 Split / merge diagnostics (adicionais, não alteram TP/FP/FN)

Na mesma partição:

- **split:** gold `g` com ≥ 2 predições `p` tais que `O(p) ∩ E(g) ≠ ∅`; predições não casadas
  nesse conjunto recebem rótulo **split_fragment** (continuam FP).
- **merge:** predição `p` com ≥ 2 golds `g` tais que `O(g) ∩ E(p) ≠ ∅`; golds não casados
  nesse conjunto recebem rótulo **merge_absorbed** (continuam FN).
- Reportar nº de golds split, nº de preds merge, e FP/FN decompostos em
  (fragment | absorbed | outros).

### 12.5 Qualidade nos TPs

- **Anchor exact agreement.**
- **Objection boundary:** Jaccard médio de `O`.
- **Episode extent:** Jaccard médio de `E`.
- **Resolution:** matriz de confusão 4×4 e kappa, **só nos TPs**; reportar junto quantos
  episódios ficaram fora por FP/FN.
- **Grounding rate:** % das predições que passam §12.1.

### 12.6 Conjuntos vazios e agregação

- Por call: P = N/A se TP+FP = 0; R = N/A se TP+FN = 0; F1 = N/A se P ou R for N/A.
  - TP = FP = FN = 0 (sem gold e sem predição): P/R/F1 = N/A na call — é acerto, não erro.
  - gold = 0 e predições > 0: **P = 0**, R = N/A, F1 = N/A na call. Os FPs **continuam
    visíveis** no agregado micro (entram em FP).
- **Agregado primário: micro** (somar TP/FP/FN de todas as calls, depois calcular). N/A só
  se o denominador agregado for 0.
- Macro por call (secundário): média só sobre calls com valor definido; reportar quantas
  calls ficaram N/A.
- Kappa indefinido (ex.: zero TPs, ou concordância esperada = 1) → **N/A**, nunca 0.
- Médias de Jaccard/anchor agreement sobre zero TPs → N/A.

Sem thresholds de aceitação neste documento (D3).

## 13. Confidence semantics

Sem campo `confidence` em v1. Incerteza expressa no domínio (`unknown`, não anotar objeção
duvidosa). Reintroduzir com semântica definida quando houver extractor probabilístico.

## 14. Edge cases

| Caso | Tratamento |
|---|---|
| No objection | zero episódios; dataset distingue "anotada sem episódios" de "não anotada"; métricas N/A por call (§12.6). |
| `unresolved_lead` | nenhum `role="lead"` → nenhum episódio groundable; call fora do golden set de episódios até o role ser resolvido **na Call**. |
| Speaker unknown | não ancora; pode ser contexto de terceiro. |
| Closer quoting lead | contexto; nunca objection evidence. |
| Multiple participants | §5.4. |
| Repeated objection | antes da closure → nova resposta no mesmo episódio; depois → novo episódio (recorrência). |
| Reopened objection | v1 só deriva **recorrência** (§5.2); reabertura não é afirmada. |
| Multiple objections in same utterance | um episódio por categoria, mesma âncora. |
| One closer segment addressing two objections | o segmento aparece no contexto de ambos. |
| Objection with no handling | `closer_segment_count = 0`; status pelo objetor. |
| Poor transcript | objeção ininteligível → não anotar; última resposta ininterpretável → UNKNOWN → `unknown`. |
| Missing timestamp | Canonical Call exige timestamps; episódio usa `segment_index`. |
| Overlapping segments | ordem por `segment_index`. |
| Contradictory evidence | §9.1 (mesma resposta) e §9.2 (respostas diferentes). |
| Partial resolution | MIXED → `partially_resolved`. |
| Call ends during objection | fim da call fecha; status pelo §9. |
| Lead agrees, later raises same category | ep1 inalterado; ep2 novo; só recorrência. |
| Split objection | §5.3. |
| Objection + resolution in same segment | §7.2 (s30). |
| Response split across segments | §9.1 (A = B). |
| Immediate reversal | §5.1: mesmo episódio, `unresolved`. |
| Two concurrent threads | alternar entre eles não fecha nenhum; assunto closure-relevant fora de todos fecha os OPEN (§5.1). |
| Same category, different participants | episódios separados (§5.4). |
| Same category concern while thread open/parked | mesmo episódio, contexto, resposta REJECT (§4). |
| Same category concern after closure | novo episódio; recorrência, não reabertura (§5.2). |
| Discount accepted → overall price still high | REJECT (reafirmação geral, §9.1). |
| Monthly fee accepted, setup fee pending (same response) | MIXED (§9.1). |
| Explicitly parked objection | PARKED, mesmo episódio até retomada/abandono/fim (§5.1). |
| ROI / volume question during price objection | on-topic funcional, contexto (§5.1). |
| Call logistics ("vou compartilhar a tela") | não fecha (§5.1). |
| Third-party aside | não fecha se não muda o fio comercial (§5.1). |
| Parser/normalizer resegmentation between runs | comparação recusada; rematerializar/reanotar (§12.0). |
| Ambiguous / unmatched CallDealMatch | sem `deal_id` canônico derivado (§11). |
| Episode failing grounding/order | INVALID: não persistido, avaliado nem re-derivado (§12.1). |

## 15. Migration v0 → v1

- **Coexistência (D1 APPROVED).** `ObjectionEvent` v0, id, extractor e eval v0 intactos;
  `ObjectionEpisode` é tipo novo e aditivo.
- **Lifting determinístico** (a implementar junto do contrato):
  `episode_from_event(e) → ObjectionEpisode(call_id=e.call_id, category=e.category,
  objection_segment_ids=(e.segment_id,), context_segment_ids=(), resolution_status="unknown")`.
- **Limitação:** super-segmenta (sem threading/closure). No eval aparece como **FP** com
  rótulo `split_fragment`. P/R do v1 não é comparável ao do v0.
- Golden set de episódios é anotado diretamente em v1.

## 16. Rejected fields

`raised_by`, `anchor_segment_id` como campo, `started_at`, `ended_at`, `lead_reaction`,
`resolution_evidence_segment_ids`, fase por segmento (v1), `next_step`, texto/quote, char
spans, proveniência por registro.

## 17. Deferred fields

`objection_subtype`; vínculo semântico entre episódios (`reopens_episode_id` / reopening /
non-durable resolution); handling steps e estratégia (Strategy); `confidence`; `severity`;
link direto a `Deal`/`Outcome`; ligação cross-call de episódios.

## 18. Impact analysis

| Área | Impacto |
|---|---|
| `ObjectionEvent` v0 | nenhum |
| `RuleBasedObjectionExtractor` | nenhum; episódios via lifting |
| Synthetic eval v0 | nenhum; harness novo `evals/objection_episode_v1/` quando implementar |
| Future taxonomy | `category` reusa enum v0; subtype aditivo; subtype é o caminho para separar preocupações da mesma categoria |
| Annotation Guidelines | este documento define unidade, closure, âncora, listas e respostas; conteúdo das guidelines é de Otávio |
| Future LLM extractor | saída = este contrato; precisa threading/closure, âncora, objetor e resolução; proveniência no run |
| Deal / Outcome Intelligence | sem mudança de schema; via `call_id → CallDealMatch → deal_id` só com status `matched`; não pode assumir reabertura a partir de recorrência |
| Run provenance / eval harness | proveniência inclui identidade da Call de origem (§11); evaluator recusa comparar segmentações diferentes (§12.0); calculado a partir da `Call` existente |
| IDs | novo `ep_`; demais inalterados |
| Serialization | Pydantic JSON; `tuple` → array |
| Tests | futuros: contrato, grounding helper, lifting, matcher com os 3 cenários de sanidade §12.3, N/A §12.6 |
| Canonical Call / Participant / Deal / CRM matching / Agro ingestion | **nenhum** |

## 19. Decisions

| # | Decisão | Estado |
|---|---|---|
| D1 | Episode coexiste com Event v0 | **APPROVED** (Matheus) |
| D2 | `episode_id` = hash(call_id, anchor_segment_id, category), com as limitações de §10 | **APPROVED** (Matheus) |
| D3 | Piloto de dupla anotação | **OPEN** |
| D4 | Proveniência no run (inclui identidade da Call de origem, §11) | **APPROVED** (Matheus) |
| D5 | Decisor do lado do lead equivale a lead? | **OPEN** |
| D6 | Os quatro status são anotáveis e comercialmente úteis? Inclui: pendência declarada ("ainda preciso verificar se consigo pagar") deve ser `unresolved`/REJECT, `partially_resolved`, `unknown` ou um estado futuro? | **OPEN** — Otávio + Gabriel |
| D7 | Implementar o contrato | **BLOCKED** até D3 + D6 |
| D8 | ADR | Sim, como **primeiro passo de D7**: registrar D1/D2/D4 em `docs/decisions/` antes de qualquer código. |

**D3 — piloto (sem thresholds).** O que medir: §12.3–12.6 humano A × humano B. Como: 3–5
calls reais autorizadas, dois anotadores independentes, algoritmo §12.2. Inspeção: listar
todo par não casado e toda discordância de resolução; classificar a causa em categorias
nomeadas: `premature_closure` (fio fechado cedo: deferral não reconhecido, on-topic funcional
tratado como mudança de assunto, logística ou aparte de terceiro tratado como closure),
`late_closure`, `anchor` (§5.3), `list_membership` (objeção/contexto), `objector`,
`category`, `response_boundary` (§9.1), `aspect` (MIXED vs REJECT), `response_label`,
`transcript`; ajustar regras onde a causa for ambiguidade da regra. **Thresholds de
go/no-go só depois dos resultados.**

**D5 — decisor.** Identidade e papel de participante pertencem à Canonical Call / taxonomia
de participantes e **não** são alterados em AC-47. Enquanto aberto: só `role="lead"` ancora;
objeções de participantes `other` ficam sem episódio (lacuna documentada, não inferida).

## 20. Definition of Done (desta proposta)

- [x] Auditoria do v0 contra o código.
- [x] Definição de episódio, closure, âncora, objetor.
- [x] Evidence model (A/B/C), listas como grounding, não função.
- [x] Recorrência ≠ reabertura.
- [x] Resposta substantiva independente de segmentação, precedência e exemplos sintéticos.
- [x] Matching maximum-cardinality-first, TP/FP/FN, split/merge, N/A.
- [x] ID (D2 aprovado) com limitações.
- [x] 17 edge cases obrigatórios + adicionais.
- [x] Migração sem quebrar v0; impacto por área.
- [x] Aspecto operacional; mesma categoria em fio aberto; parked threads; logística e apartes.
- [x] Pinning da segmentação da Call de origem e precondição de eval.
- [x] Ordem/invalidade; deal linkage só `matched`; métricas com gold vazio.
- [x] Review Domain / Evaluator / Architecture (rev. 4): APPROVE (Evaluator após fix de closure retrospectiva, §5.1).
- [ ] D3, D5, D6 resolvidos.
- [ ] (Próxima task) ADR + implementação, só após D3 + D6.
