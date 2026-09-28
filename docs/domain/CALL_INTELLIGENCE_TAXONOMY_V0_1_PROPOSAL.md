# Call Intelligence Taxonomy v0.1 — Proposal

Status: **PROPOSAL — research-integrated, pré-pilot.** Nenhum código, schema, enum, dataset ou
guideline muda com este documento. TAX, D3 e D6 continuam **abertas**. Todos os exemplos são
sintéticos.

## Purpose

Responder:

> O que da pesquisa externa deve virar **contrato** do AI Closer, o que deve virar
> **taxonomia/guideline**, o que deve ficar no futuro **Knowledge Base/RAG** e o que continua só
> como **referência externa**?

Resposta curta:

- **Contrato:** nada muda. `ObjectionEpisode` v1 continua a unidade fundamental e já implementa a
  opção "objeção atômica" que a pesquisa deixou aberta.
- **Taxonomia (provisória, só anotação):** 8 categorias candidatas para o workshop TAX, com
  `NEED_VALUE_FIT` e `TRUST_RISK` explicitamente marcadas como abstrações operacionais.
- **Guideline (proposta para v0.1, não editada aqui):** regras de fronteira (hesitação, brush-off,
  "consultar sócio ≠ autoridade", pedido de clarificação), vocabulário de reação mapeado para os
  rótulos de resposta do contrato.
- **Knowledge/RAG futuro:** definições, sinais, `often_confused_with`, exemplos, source refs,
  frameworks. Hoje isso é **arquivo Markdown versionado**, não infraestrutura.
- **Referência apenas:** ontologia de resistência (Hunt & Bashaw / Clark & Pinch), Challenger,
  Solution Selling, GAP Selling, achados observacionais da Gong como "boa prática".

## Inputs

| # | Input | Autoridade (ordem da task) | Nota |
|---|---|---|---|
| 1 | [`OBJECTION_EPISODE_V1_PROPOSAL.md`](OBJECTION_EPISODE_V1_PROPOSAL.md) rev. 5 | contrato (D1, D2, D4 APPROVED) | ainda não implementado (D7 BLOCKED) |
| 2 | `src/closer_ai/domain/objection.py` (`ObjectionCategory` v0) | contrato implementado | `price`, `timing_priority`, `trust_authority`, `no_need`, `other` |
| 3 | [`GOLDEN_SET_ANNOTATION_PROTOCOL_V1.md`](../evals/GOLDEN_SET_ANNOTATION_PROTOCOL_V1.md) | protocolo mergeado | pré-pilot |
| 4 | [`OBJECTION_ANNOTATION_GUIDELINE_V0.md`](../evals/OBJECTION_ANNOTATION_GUIDELINE_V0.md) | guideline mergeada | pré-pilot |
| 5 | `OPEN_SOURCE_REUSE_AUDIT.md` | referência | **não está em `main`**: só na branch `docs/reference-repos-audit` (lido via `git show`). Os links para `../references/` nos docs de evals estão quebrados em `main` até esse merge |
| 6 | `closer-ai-references/research/CALL_INTELLIGENCE_TAXONOMY_RESEARCH_V0_1.md` | pesquisa externa (nível 4) | fora do repo, read-only, sha256 `e50d7cad…6fd52`. **Citações não reverificadas nesta task** (sem pesquisa nova); graus de evidência abaixo são os da pesquisa, reclassificados por tipo de fonte |

Quando a pesquisa contradiz 1–4, este documento registra **CONFLICT** e a decisão necessária; não
altera o contrato.

## Design principles

A pesquisa propõe 8 princípios. Todos já existem, com a mesma força ou maior, no AI Closer:

| Princípio da pesquisa | Onde já vale no AI Closer | Estado |
|---|---|---|
| Transcript first | evidência = `segment_id` (contrato §7) | ALIGNED |
| Resistance ≠ objection | guideline: 4 testes de objeção | PARTIAL (ver Sales Resistance) |
| Surface wording ≠ underlying cause | guideline: "categorize pelo significado, não por palavra-chave" | ALIGNED |
| Seller response ≠ resolution | contrato §9.2 regra 5; guideline "closer respondeu não é `resolved`" | ALIGNED |
| Silence ≠ acceptance | contrato §9.2 (NEUTRAL descartado → `unknown`) | ALIGNED |
| Classify behavior before evaluating it | guideline: handling registra presença, não qualidade | ALIGNED |
| Uncertainty is first-class | protocolo: PRESENT/ABSENT/UNKNOWN/N/A/AMBIGUOUS | ALIGNED |
| Prefer observable labels | protocolo + guideline: dito × inferido | ALIGNED |

Regra central proposta pela pesquisa — *"Classify what the transcript supports, not what probably
happened"* — é compatível e pode ser citada literalmente na guideline v0.1.

Princípios adicionais deste documento:

1. **Minimalismo de domínio.** Conceito comercial só entra no domínio se houver necessidade
   estrutural (identidade, grounding, linkage). Semântica comercial fica em taxonomia/guideline.
2. **Pesquisa dá priors; pilot dá evidência operacional.** Nada abaixo é fechado sem D3.
3. **Força da fonte é registrada, não achatada** (ver Source strength).

## Existing domain constraints

Restrições que qualquer adoção precisa respeitar (contrato rev. 5):

- **7 campos armazenados**; objetor, âncora, tempos, `closer_segment_count` são derivados.
- **Uma categoria, um objetor por episódio** (§4). Categorias diferentes na mesma fala → dois
  episódios com a mesma âncora (§5 regra 5).
- **`category` entra na identidade:** `episode_id = hash(call_id, anchor_segment_id, category)`
  (D2). Trocar o valor string de uma categoria muda o id.
- **`category` reusa o enum v0** (§6, §18). Enum v0 é também o de `ObjectionEvent`, que coexiste
  inalterado (D1).
- **Rejeitados como campo:** `lead_reaction`, `resolution_evidence_segment_ids`, fase por segmento,
  `raised_by`, `next_step`, proveniência por registro (§16).
- **Adiados:** `objection_subtype`, handling steps/Strategy, `confidence`, `severity`,
  `reopens_episode_id` (§17).
- **Resolução in-call, do objetor**, 4 valores, precedência temporal (§9). D6 aberta.
- **Sem campo `confidence`** (§13): incerteza = `unknown`/AMBIGUOUS/não anotar.
- **Deal linkage indisponível até DEP-1**; resolução ≠ outcome.

## Sales Resistance

### Proposta da pesquisa

```
SALES_RESISTANCE
├── OBJECTION
├── COUNTERARGUMENT
├── HESITATION
├── BRUSH_OFF
├── CONDITION
└── IMPLICIT_RESISTANCE
```

### Análise

- A **definição de objeção da guideline já é ampla**: "barreira, discordância, **condição ainda não
  atendida** ou preocupação que [o lead] levanta como impedindo ou dificultando seguir em frente".
  Ou seja, o que o AI Closer chama de `ObjectionEpisode` já cobre OBJECTION + COUNTERARGUMENT +
  CONDITION da pesquisa. HESITATION e BRUSH_OFF sem barreira dita já são tratados como AMBIGUOUS
  (GL-2) ou não anotados.
- Nenhuma operação do produto hoje (anotação, grounding, matching de episódios, eval, Outcome
  Intelligence futura) precisa de um registro "resistência" **distinto** de um episódio: não há
  campo que viva na resistência e não no episódio, nem identidade própria.
- Uma entidade `SalesResistance`/`ResistanceEpisode` exigiria: id próprio, regra de agrupamento de
  episódios, novo matching no eval, nova dimensão de concordância. Custo alto, necessidade não
  demonstrada.
- O agrupamento "mesma fala, várias barreiras" **já é derivável**: episódios que compartilham
  `objection_segment_ids[0]` na mesma call.

### Decisão (CIT-M1)

**KEEP CURRENT CONTRACT.** `SalesResistance` é **conceito classificatório** (TAXONOMY/REFERENCE),
não entidade. `ObjectionEpisode` continua a unidade. `resistance_type` **não** vira campo.

Feature que exigiria `ResistanceEpisode` no futuro: nenhuma identificada. Reabrir só se o pilot
mostrar que anotadores divergem sistematicamente por agruparem barreiras de categorias diferentes
num "episódio de resistência" e isso afetar métricas (tipo `BOUNDARY`/`category` recorrente).

Nomenclatura (P2, não bloqueante): "objection" no AI Closer ≈ "sales resistance explícita" na
literatura. Documentar isso no glossário quando TAX fechar; não renomear o contrato.

## ObjectionEpisode vs atomic objection

Exemplo: *"Está caro e não temos time para implementar."*

| Pergunta | Resposta pelo contrato atual |
|---|---|
| O contrato já suporta duas objeções no mesmo anchor? | **Sim.** §5 regra 5: dois episódios, mesma âncora. Guideline "Multiple objections" idem. |
| `category` faz parte da identidade determinística? | **Sim.** D2: `hash(call_id, anchor, category)`. Os dois episódios têm ids diferentes. |
| Consequências para annotation/evals | Cada barreira tem sua própria `resolution_status` → a pesquisa reconhece que "duas objections" produz `NEED_VALUE_FIT = RESOLVED`, `PRICE_BUDGET = UNRESOLVED` sem precisar de `PARTIALLY_RESOLVED`. Matching (§12.2) particiona por categoria; divergência de categoria entre anotadores é pareada sem particionar (protocolo). |
| Mudar agora quebraria IDs? | Introduzir um pai **não** quebra ids de episódio (seria entidade nova), mas duplica unidade de anotação/eval. Mudar para "um episódio com várias categorias" **quebraria** D2 (categoria sai do id ou vira lista). |
| Precisamos de entidade pai? | **Não.** O agrupamento é derivável pela âncora compartilhada. |

A hipótese operacional da pesquisa ("duas objections atômicas ligadas ao mesmo resistance episode")
é **exatamente** o contrato atual, sem o objeto pai: a ligação é a âncora compartilhada.

### Decisão (CIT-M2)

**KEEP CURRENT CONTRACT.** Classificação dos sub-itens:

| Item | Classificação |
|---|---|
| ObjectionEpisode como unidade fundamental | KEEP CURRENT CONTRACT |
| Uma categoria por episódio; várias categorias → vários episódios | KEEP CURRENT CONTRACT |
| Entidade pai `ResistanceEpisode` | EVOLVE LATER (só se o pilot mostrar necessidade) |
| `primary_category + secondary_category` | REJECT para v0.1 (colide com D2 e com "uma categoria"); "causa subjacente" é `objection_subtype`/relação, já DEFER (§17) |
| Barreira aparente escondendo outra causa ("está caro" = falta de valor?) | OPEN — categorize pelo **dito**; inferência de causa vai para nota INFERIDO |

Nada é **MUST CHANGE**.

## Resistance Types

Nenhum label abaixo vira campo. A pergunta é só: **o conceito entra na guideline v0.1 como regra de
detecção/fronteira?**

| Label | Definição proposta | Suporte (tipo) | Discriminabilidade | Risco de inferência | Guideline atual | Utilidade de produto | Decisão |
|---|---|---|---|---|---|---|---|
| **OBJECTION** | barreira/preocupação explícita ligada à possibilidade de avançar | peer-reviewed (Hunt & Bashaw) + practitioner (HubSpot, Gong) | alta (4 testes da guideline) | baixo | é a definição de episódio | é o objeto do produto | **ADOPT_V0_1** (já adotado; = `ObjectionEpisode`) |
| **COUNTERARGUMENT** | resposta que contradiz a informação do seller com base em crença/experiência **prévia** | peer-reviewed (Hunt & Bashaw), contestado por Clark & Pinch (peer-reviewed) | baixa: exige identificar schema prévio | **alto** (psicológico) | não existe; cai em "objeção" | nenhuma consumidora hoje | **DEFER** — anotar como OBJECTION; "experiência prévia dita" pode ir em nota OBSERVADO. Nunca inferir schema não verbalizado |
| **HESITATION** | incerteza/indecisão sem barreira específica dita | peer-reviewed (Schurr et al., "buyer indecision") para o fenômeno; label separado é abstração | média | médio | GL-2: "vou pensar" isolado → AMBIGUOUS | útil como aviso contra categorizar cedo | **PROVISIONAL** — como **regra de guideline**: hesitação sem barreira dita não abre episódio categorizado; AMBIGUOUS (objeção?) ou categoria UNKNOWN se já há episódio. Não é label |
| **BRUSH_OFF** | tentativa de encerrar/adiar sem barreira concreta | practitioner (HubSpot) | **baixa** vs TIMING (a própria pesquisa: "não existe regra lexical confiável") | alto (intenção) | GL-2 cobre parcialmente | baixa até o pilot mostrar frequência | **PROVISIONAL** — regra de fronteira: motivo concreto dito → TIMING_PRIORITY (ou outra categoria); sem motivo → AMBIGUOUS. Nunca rotular "brush-off" como fato |
| **CONDITION** | condição explícita para avançar ("se parcelar em 12x, seguimos") | pesquisa: **NOT SUPPORTED BY CURRENT SOURCES** como classe | média | baixo | já dentro da definição de objeção ("condição ainda não atendida") | nenhuma adicional | **DEFER** — é OBJECTION com a categoria da condição. Reavaliar só se o pilot mostrar que condição tem padrão de resolução próprio |
| **IMPLICIT_RESISTANCE** | resistência não explícita (Clark & Pinch) | peer-reviewed para o fenômeno; **a pesquisa não dá definição operacional nem evidência mínima** | muito baixa | **muito alto** | contradiz o teste "palavras próprias" | nenhuma que não viole dito × inferido | **REJECT** como label de anotação. Fica REFERENCE_ONLY, como justificativa teórica para preservar AMBIGUOUS e ler em sequência |

`NO_RESISTANCE` (pesquisa) = call ABSENT do protocolo (ALIGNED). `UNKNOWN`/`AMBIGUOUS` = status do
protocolo (ALIGNED).

**Nota de integridade:** a pesquisa atribui "Confidence: STRONG" à árvore de 6 tipos, mas ela mesma
classifica CONDITION como WEAK–MODERATE / NOT SUPPORTED e não define IMPLICIT_RESISTANCE. A árvore
**não** é tratada aqui como STRONG; só o conceito-pai (resistência ≠ só objeção) é.

## Objection Categories

### Mapa v0 → candidatas v0.1

| Enum v0 (contrato) | Candidata v0.1 | Relação |
|---|---|---|
| `price` | `PRICE_BUDGET` | 1:1 (renomeia/explicita verba) |
| `timing_priority` | `TIMING_PRIORITY` | 1:1 |
| `no_need` | `NEED_VALUE_FIT` | **alarga** (inclui valor e adequação) |
| `trust_authority` | `AUTHORITY_INTERNAL_BUY_IN` + `TRUST_RISK` | **split** — não há lifting determinístico |
| `other` | `COMPETITION_EXISTING_SOLUTION`, `IMPLEMENTATION_INTEGRATION`, `TERMS_PROCESS`, `OTHER` | split do resíduo |

**CONFLICT (CIT-M3):** o contrato fixa `category` = enum v0 inalterado. Adotar as 8 categorias no
`ObjectionEpisode` é mudança de contrato e muda `episode_id` (valor string entra no hash). Hoje o
custo é zero (nada implementado, nenhum gold), mas cresce a cada gold produzido. Decisão humana
necessária — ver Decisions.

### Tabela de avaliação

Tipo de fonte: **PR** = peer-reviewed; **RM** = research-derived methodology; **PO** = proprietary
observational (Gong Labs); **PG** = practitioner guide (HubSpot, blog Gong); **CF** = commercial
framework (MEDDPICC, Sandler, BANT); **AC** = abstração do AI Closer/da pesquisa, sem fonte.

| Category | Source strength | Operational clarity | Overlap risk | Evidência mínima | Often confused with | Keyword risk | Recommendation |
|---|---|---|---|---|---|---|---|
| `PRICE_BUDGET` | PR (Schurr: price objections) + PG | alta | médio (valor, termos, timing de verba) | custo/verba ligado explicitamente à dificuldade de avançar | NEED_VALUE_FIT, TERMS_PROCESS, TIMING_PRIORITY | **alto** ("caro", "valor", "orçamento") | **ADOPT_PROVISIONALLY** |
| `TIMING_PRIORITY` | PG + PO | média | **alto** vs brush-off; médio vs verba | momento/prioridade ligado ao impedimento | BRUSH_OFF, PRICE_BUDGET ("verba só em janeiro"), TERMS_PROCESS | alto ("agora", "depois") | **ADOPT_PROVISIONALLY** |
| `NEED_VALUE_FIT` | PG (Need) + RM (SPIN, suporte conceitual); fusão = AC | média | **alto** vs PRICE ("não sei se vale esse preço") | negação explícita de necessidade, utilidade, benefício ou adequação | PRICE_BUDGET, IMPLEMENTATION, COMPETITION | médio | **ADOPT_PROVISIONALLY** (fusão v0.1; **SPLIT_LATER** candidato) |
| `AUTHORITY_INTERNAL_BUY_IN` | PG (HubSpot, Gong) | alta **se** exigir restrição explícita | médio vs processo normal de decisão | restrição explícita ao poder de decisão/aprovação ("não tenho alçada") | processo normal de decisão, consulta a stakeholder | **alto** ("sócio", "diretora") | **ADOPT_PROVISIONALLY** |
| `TRUST_RISK` | PG; união = **AC** | média-baixa | **alto** (need, implementation, competition) | receio/dúvida ligada à disposição de avançar | NEED_VALUE_FIT, IMPLEMENTATION, COMPETITION, pedido de case | médio ("medo", "receio") | **ADOPT_PROVISIONALLY** (abstração operacional; SPLIT_LATER só com dados) |
| `COMPETITION_EXISTING_SOLUTION` | PG + CF (MEDDPICC Competition) | alta | médio (status quo, need) | alternativa existente apresentada como razão para não avançar | NEED_VALUE_FIT, TIMING_PRIORITY, informação competitiva neutra | médio (nome de concorrente) | **ADOPT_PROVISIONALLY** |
| `IMPLEMENTATION_INTEGRATION` | PG (menção, não taxonomia) | alta | médio (trust, timing) | dificuldade de implementação explicitamente ligada ao avanço | TRUST_RISK, TIMING_PRIORITY, NEED_VALUE_FIT, pergunta técnica | médio ("integra?") | **ADOPT_PROVISIONALLY** — relevância para as operações Agro/Empreende **não verificada**; se ausente no pilot, candidata a MERGE em OTHER |
| `TERMS_PROCESS` | PG + CF (Paper Process); B2B-dependente | média | **alto** vs PRICE (forma de pagamento), AUTHORITY, TIMING | termo/processo funcionando como impedimento ou condição | PRICE_BUDGET, AUTHORITY, TIMING, processo normal ("jurídico vai revisar") | médio ("contrato") | **ADOPT_PROVISIONALLY** — mesma ressalva de relevância; regra de fronteira com PRICE a validar ("não cabe à vista" = PRICE; "não assinamos contrato de 3 anos" = TERMS) |
| `OTHER` | — | — | — | objeção clara fora das 8 | — | — | **KEEP** (válvula; nunca no lugar de UNKNOWN/AMBIGUOUS) |
| `UNKNOWN` / `AMBIGUOUS` | protocolo | — | — | — | — | — | **KEEP como status de anotação**, **não** valores do enum de categoria (como hoje) |

**Rejeitadas para v0.1** (concordando com a pesquisa): `STATUS_QUO` (ver abaixo), `PRODUCT`
(ampla demais), `RISK` separado de `TRUST`, `VALUE` separado de `NEED/FIT`, `PROCUREMENT` separado
de `TERMS_PROCESS`.

**Outcome Intelligence:** nenhuma categoria tem utilidade de outcome demonstrada. Qualquer
associação categoria × outcome depende de DEP-1, dado real e amostra suficiente, e é
**associação observacional**, nunca causal.

**Keyword risk:** toda categoria tem sinais lexicais; a pesquisa lista "positive signals" como
palavras. Na guideline, sinais são **evidência que precisa estar ligada à barreira**, nunca gatilho.
Cada categoria precisa de ao menos um *falsifying example* (protocolo).

## NEED / VALUE / FIT

**Não há consenso nas fontes.** A fusão é decisão de parcimônia da pesquisa, não achado.

| Sub-conceito | O que resiste | Exemplo sintético | Suporte |
|---|---|---|---|
| NEED | "não temos esse problema" | "Hoje a gente não tem dificuldade com isso." | PG (HubSpot) + RM (SPIN implied/explicit need) |
| VALUE | "o benefício não compensa" | "Não vejo retorno suficiente para mudar." | PG; fronteira com PRICE fraca |
| FIT | "não serve para o nosso caso" | "Isso não resolve a parte que mais importa pra nós." | PG; fronteira com IMPLEMENTATION fraca |

Por que fundir no v0.1: as três fronteiras são as de menor concordância esperada; separar antes do
pilot multiplica divergências CATEGORY sem ganho demonstrado.

Ambiguidades que surgem:

- VALUE × PRICE: "Não sei se vale esse preço." → a pesquisa manda não inferir: AMBIGUOUS
  {`PRICE_BUDGET`, `NEED_VALUE_FIT`}.
- FIT × IMPLEMENTATION: "Não funciona com nosso sistema." (fit do produto ou esforço de integração?).
- NEED × TIMING: "Por enquanto não precisamos." (necessidade ausente ou adiada?).

Onde a distinção poderia importar: coaching futuro (need pede discovery; value pede prova de
retorno; fit pede escopo) — isso é Strategy, **DEFER**.

Decisão: **fusão só no v0.1, PROVISIONAL.** O pilot registra, em nota, qual sub-conceito o anotador
leu; se as notas mostrarem concordância alta num sub-conceito, SPLIT_LATER.

## TRUST / RISK

**`TRUST_RISK` não é categoria acadêmica estabelecida.** A pesquisa admite: "trust e risk não
aparecem como uma categoria acadêmica consolidada nas fontes analisadas. A junção é uma abstração
operacional." Fonte principal: guia practitioner (HubSpot), que lista trust entre causas de
objeção.

Ambiguidades: receio de resultado (risco) × desconfiança no vendedor (trust) × dúvida sobre
implementação × pedido de case (informação). "Já tivemos problema com outra plataforma" sustenta
**experiência negativa anterior (observado)**, não "não confia no vendedor" (inferido).

Decisão: **ADOPT_PROVISIONALLY, rotulada AC** em todo documento que a use. Pedido de case/prova sem
barreira dita → não é episódio.

**CONFLICT com v0:** o enum v0 junta `trust_authority`. A pesquisa separa AUTHORITY (suporte PG,
evidência explícita) de TRUST (abstração). As duas têm evidências mínimas diferentes; manter a
junção v0 no pilot gera um rótulo com dois critérios. Entra em CIT-M3.

## STATUS QUO

A pesquisa: **NOT SUPPORTED BY CURRENT SOURCES** como categoria independente discriminante.

Compatibilidade: o AI Closer não tem `status_quo` (v0 nem guideline). A guideline lista "status quo"
só como semente externa. **Decisão: REJECT como categoria v0.1.** Destino pelo **que foi dito**:

| Dito (sintético) | Destino |
|---|---|
| "Estamos satisfeitos com o fornecedor atual." | `COMPETITION_EXISTING_SOLUTION` |
| "Fazemos na planilha e funciona." | `NEED_VALUE_FIT` (alternativa não-fornecedor = ausência de necessidade) — **a validar no pilot** |
| "Agora não é hora de mudar nada." | `TIMING_PRIORITY` |
| "Deixa como está, qualquer coisa te procuro." | sem barreira dita → AMBIGUOUS (regra de brush-off) |

Nenhum destino é `resistance_type`. Se o pilot mostrar muitos AMBIGUOUS
{COMPETITION, NEED_VALUE_FIT} por "solução interna", reabrir.

## Seller Response

### Como o contrato armazena hoje

- Segmentos do closer dirigidos ao fio ficam em `context_segment_ids` (§5 regra 6).
- `closer_segment_count` / `has_closer_segment` são **derivados** (§8).
- Handling steps, estratégia, tipo de resposta: **DEFER (Strategy)**. Fase por segmento: **REJECT
  em v1** (§7.1 B: exige taxonomia de fases com estudo de concordância próprio e um segmento pode ter
  mais de uma fase).

### Avaliação

| Pergunta | Resposta |
|---|---|
| Taxonomia de resposta vira campo do domínio agora? | **Não.** Contradiz §7.1 B/§17 e não há consumidor. |
| Pode ficar numa futura annotation/extraction layer? | **Sim.** Camada separada, chaveada por `episode_id` + `segment_id`, versionada pela taxonomia. Não é desenhada aqui. |
| Multilabel? | **Sim, conceitualmente** — um turno pode ser ACKNOWLEDGE + CLARIFY + ADDRESS. Concordância multilabel exige métrica própria (não kappa simples). |
| Ordem precisa ser preservada? | Sim para qualquer análise tipo "clarificar antes de responder". **De graça** se o rótulo for anexado a `segment_id` (ordem = `segment_index`). Não criar campo de ordem. |
| Distinguir segmento de resposta da sua classificação? | **Sim.** Segmento = evidência estrutural (DOMAIN, já existe). Classificação = julgamento (TAXONOMY). Mesmo problema de §7.1 B: segmento ≠ passo conversacional; um rótulo pode ocupar vários segmentos. |

### Labels

| Label | Suporte | Nota de compatibilidade |
|---|---|---|
| ACKNOWLEDGE_VALIDATE | PG + PO | — |
| CLARIFY | PO + PG | fronteira com PROBE admitidamente imperfeita |
| PROBE_EXPLORE | PG + PO | — |
| CONFIRM_UNDERSTANDING | PG (+ menção Gong) | — |
| ADDRESS_EXPLAIN | PR (Schurr) + PG | não implica correção, convencimento nem resolução |
| PROVIDE_EVIDENCE | PG | — |
| REFRAME | PO/PG (Gong) | — |
| NEGOTIATE_OFFER_ALTERNATIVE | PG | — |
| DEFER_FOLLOW_UP | PG | ≠ PARKED do contrato: PARKED é deferral **dentro da call** com retomada possível; DEFER_FOLLOW_UP é pós-call. Nenhum dos dois implica `unresolved` |
| IGNORE_CHANGE_TOPIC | **AC** (a pesquisa admite) | rótulo de **ausência**; equivale a handling ABSENT + closure por mudança de assunto (guideline). Não é resposta |

**Decisão (CIT-M4): DEFER** a taxonomia de resposta inteira. Não entra no pilot D3 (o pilot mede
fronteira/categoria/resolução; somar 10 labels multilabel dilui o sinal). Guarda-se como
TAXONOMY/RAG_KNOWLEDGE candidata para a fase Strategy. **Nenhum label implica qualidade**: a
evidência da Gong é observacional e proprietária — não autoriza "melhor resposta".

## Prospect Reaction

### Como o contrato trata hoje

Reação = respostas substantivas do objetor (§9.1), cada uma com **um** rótulo de julgamento
(ACCEPT / REJECT / MIXED / NEUTRAL / OFF_CATEGORY / UNKNOWN), **não armazenado** (`lead_reaction`
REJECT como campo, §6). `resolution_status` é o único resultado persistido.

### Mapeamento

| Label da pesquisa | Observável? | Rótulo do contrato | Ajuda a determinar resolução? |
|---|---|---|---|
| ACCEPTS_RESPONSE | sim (declaração) | ACCEPT | sim |
| MOVES_FORWARD | sim, se ligado ao tema | ACCEPT ("próximo passo que pressupõe a objeção superada") | sim; next step genérico não basta (ALIGNED) |
| REPEATS_OBJECTION | sim | REJECT | sim |
| CONTINUES_CONCERN | sim | REJECT | sim; sobreposição alta com REPEATS |
| REJECTS_RESPONSE | sim | REJECT | sim |
| NEW_OBJECTION | sim | abre **outro episódio**; para o fio atual só conta o que for dito sobre ele | não prova resolução do anterior (ALIGNED) |
| REQUESTS_CLARIFICATION | sim | **sem equivalente** | **GAP** — ver abaixo |
| TOPIC_CHANGED_NO_CONFIRMATION | sim (estrutura) | OFF_CATEGORY / closure | não; leva a `unknown` se não houver resposta anterior (ALIGNED) |
| AMBIGUOUS | — | status AMBIGUOUS da anotação | — |
| UNKNOWN | — | UNKNOWN | — |

Sobreposições: REPEATS ⊂ CONTINUES ≈ REJECTS → para resolução, os três colapsam em REJECT. Separá-los
só teria valor para Strategy.

Inferência: MOVES_FORWARD e NEW_OBJECTION exigem julgar ligação com o tema; os demais são próximos
do dito.

**PARTIAL/CONFLICT pequenos:**

1. **"Hmm... tá."** — pesquisa: AMBIGUOUS; contrato: NEUTRAL (interjeição, descartada → `unknown` se
   não houver outra). O efeito na resolução é o mesmo (nenhum valor definido). **Manter o contrato.**
2. **REQUESTS_CLARIFICATION** ("Como funcionaria essa migração?") — conteúdo interpretável sobre o
   ponto que não aceita nem rejeita. Não é NEUTRAL (tem conteúdo) nem UNKNOWN (é interpretável).
   Se for a **última** resposta, §9.2 não diz o que fazer. **OPEN (CIT-O4)**: proposta para a
   guideline v0.1/D6 tratá-la como não-sobrescrevente (como NEUTRAL) → vale a anterior ou `unknown`.
   Não decidido aqui.

### Decisão (CIT-M5)

- **Single-label por resposta** (MIXED cobre aceito + pendente). Multilabel não é necessário para
  resolução.
- **Derivada/julgada, não persistida.** Mantém §6. O ponteiro de justificativa opcional do protocolo
  (GS-3) já cobre auditoria.
- Vocabulário da pesquisa → **GUIDELINE** como sinônimos didáticos dos rótulos do contrato.

## Resolution

| | Contrato (§9) / guideline | Pesquisa | Compatibilidade |
|---|---|---|---|
| Valores | `resolved`, `partially_resolved`, `unresolved`, `unknown` | mesmos 4 | ALIGNED |
| `resolved` exige evidência do prospect | sim (só falas do objetor) | sim ("não basta: seller respondeu, ok, assunto mudou, call terminou, **Deal ganho**") | ALIGNED |
| `unknown` ≠ `unresolved` | sim | sim | ALIGNED |
| `partially_resolved` | MIXED: dois **aspectos da mesma categoria**, mesma resposta | "redução com parte relevante pendente"; exemplo é **cross-category** (valor resolvido, verba pendente) | PARTIAL — no AI Closer o exemplo da pesquisa são **dois episódios** (`NEED_VALUE_FIT` resolved, `PRICE_BUDGET` unresolved), que é a opção "atômica" da própria pesquisa |
| Suporte de fonte | — | RESOLVED/UNRESOLVED: PO (Gong) + regra metodológica; PARTIALLY: **nenhuma definição padronizada** (WEAK–MODERATE, AC) | registrar |

### "Ainda preciso verificar se consigo pagar."

**SOURCE-BACKED OPERATIONAL RECOMMENDATION** (da pesquisa; não padronizada nas fontes; **não
resolve D6**):

| Situação | Pesquisa | Contrato (regra provisória §9.1) | Leitura |
|---|---|---|---|
| Objeção financeira já estabelecida no episódio e a fala é a última resposta | UNRESOLVED | REJECT → `unresolved` | **ALIGNED** |
| Outra parte **da mesma categoria** aceita na mesma resposta ("o total está ok; ainda preciso ver se consigo pagar a entrada") | PARTIALLY_RESOLVED | MIXED → `partially_resolved` | **ALIGNED** |
| Outra parte **de outra categoria** mudou ("agora vejo o retorno; ainda preciso ver se consigo pagar") | PARTIALLY_RESOLVED (se composta) | dois episódios: `NEED_VALUE_FIT` resolved + `PRICE_BUDGET` unresolved | ALIGNED com a opção atômica da pesquisa |
| Frase **isolada**, sem objeção estabelecida | UNKNOWN | não é resposta (não há episódio); é questão de **detecção**: é objeção? (GL-2 / hesitação) | PARTIAL — o contrato diz "nunca UNKNOWN", mas isso vale para a fala **como resposta** num episódio. Se a fala é a própria âncora, não há resposta → `unknown` pelo §9.2 regra 2 |

Wording futuro sugerido (não editado aqui): no contrato §9.1, qualificar "Nunca UNKNOWN" com
"quando a fala é resposta dentro de um episódio já ancorado".

**D6 continua OPEN.** A pesquisa **reforça** a regra provisória (REJECT → `unresolved`) para o caso
estabelecido e **não** fornece base para `partially_resolved` além do MIXED já definido, nem para um
estado "pending". A validação é de Otávio + Gabriel com dados do pilot.

## Observed vs Inferred

A pesquisa propõe `evidence → observation → optional interpretation`, nunca
`interpretation → retroactive fact`. Guideline e protocolo já exigem o mesmo (só o dito vira
evidência ou valor; inferência vai para nota INFERIDO; se a inferência decide a categoria →
UNKNOWN/AMBIGUOUS). **KEEP.**

Melhorias de wording propostas para a guideline v0.1 (**não editadas nesta branch**):

1. Citar a cadeia `evidence → observation → optional interpretation` como regra-mãe.
2. Adicionar a distinção "**tópico observado ≠ categoria de objeção**": "Esse preço é bem acima do
   que esperávamos" → tópico preço (observado), objeção PRICE_BUDGET (julgamento), "não consegue
   pagar" (não observado).
3. **Resolver tensão interna (item para a guideline v0.1):** a guideline usa "Está caro e (eu
   ainda) preciso falar com meu sócio" como exemplo **inequívoco** de dois episódios `price` +
   `trust_authority` (seção "Multiple objections" e exemplo sintético 4), enquanto a própria tabela
   observado × inferido diz que "preciso falar com meu sócio antes de decidir" **não** sustenta "não
   tem poder de decisão". A pesquisa fica do lado da tabela ("Vou conversar com minha diretora" ≠
   authority objection; exige restrição explícita). Pode-se defender a leitura v0 como "internal
   buy-in", mas então o exemplo não é inequívoco. Proposta: trocar o exemplo por um com restrição
   explícita ("sem ele eu não posso fechar") e tratar a consulta genérica como OBSERVADO (outro
   stakeholder) ou AMBIGUOUS; validar no pilot junto de GL-1. O calibration kit não usa esse
   exemplo (verificado por grep).
4. Rejeitar a notação da pesquisa `category = TIMING_PRIORITY?` / `confidence = LOW`: o contrato não
   tem `confidence` (§13); o equivalente é AMBIGUOUS com candidatas.

## Uncertainty

Os 5 estados da pesquisa (PRESENT, ABSENT, UNKNOWN, AMBIGUOUS, NOT_APPLICABLE) são **exatamente** os
do protocolo. UNKNOWN ≠ ABSENT, AMBIGUOUS ≠ UNKNOWN, e "sem resistência → seller response N/A, não
ABSENT" batem com a guideline ("N/A só quando não se aplica estruturalmente"). **ALIGNED, KEEP.**

`concern_present` como atributo (pesquisa): **REJECT** como campo; "preocupação sem função
impeditiva" já não abre episódio pelo teste 4 da guideline. Fronteira concern × objection fica
como item do pilot (CIT-O3).

## Framework mapping

Frameworks **não viram labels**. Regras de não-equivalência (entram na guideline como negativos):

- MEDDPICC field ≠ objeção. Economic Buyer existe ≠ `AUTHORITY_INTERNAL_BUY_IN`.
- Budget discutido (Sandler/BANT) ≠ `PRICE_BUDGET`. Só há objeção quando o tema funciona como
  barreira.
- Dimensão de qualificação ≠ categoria de objeção (BANT reaproveitado pela HubSpot).
- Necessidade expressa (SPIN) ≠ objeção.

| Framework | Tipo | Uso aqui | Classificação |
|---|---|---|---|
| SPIN (Huthwaite) | RM | distinguir pergunta de discovery / necessidade / objeção; suporte conceitual de NEED | **USEFUL_FOR_RAG** (+ nota de fronteira na guideline) |
| MEDDIC/MEDDPICC | CF (qualificação de deal) | reforça que authority/competition/paper process são fenômenos distintos, que só viram objeção como barreira | **USEFUL_FOR_RAG** |
| Sandler | CF | "discutir budget ≠ objeção de budget" | **REFERENCE_ONLY** (a regra já está coberta) |
| BANT | CF (via PG) | origem de 4 das 8 categorias; caveat qualificação ≠ objeção | **USEFUL_FOR_TAXONOMY** (como origem/caveat, não como estrutura) |
| Challenger | — | a pesquisa não levantou definição operacional | **INSUFFICIENT_SOURCE** |
| Solution Selling | — | só menção secundária via Gong (confirmação) | **INSUFFICIENT_SOURCE** |
| GAP Selling | — | nenhuma fonte analisada | **INSUFFICIENT_SOURCE** |

## Source strength

Níveis preservados (não somar nem achatar):

| Nível | Tipo | Fontes (como reportadas pela pesquisa) | O que pode sustentar |
|---|---|---|---|
| S1 | peer-reviewed research | Hunt & Bashaw; Clark & Pinch; Schurr et al. (Industrial Marketing Management) | existência de conceitos (resistência, objeção × contra-argumento, indecisão, resistência implícita, preço) |
| S2 | research-derived methodology | SPIN (Huthwaite) | distinções conceituais (necessidade × objeção) |
| S3 | proprietary observational study | Gong Labs (67.149 demos) | que comportamentos ocorreram **no dataset deles**; **nenhuma causalidade**, generalização moderada |
| S4 | practitioner guide | HubSpot; blog Gong (técnicas) | definições operacionais iniciais de categorias e respostas |
| S5 | commercial framework | MEDDPICC, Sandler, BANT | só distinções (fenômeno ≠ objeção) |
| AC | abstração operacional (pesquisa/AI Closer) | fusões NEED_VALUE_FIT, TRUST_RISK; IGNORE_CHANGE_TOPIC; taxonomia de reação; PARTIALLY_RESOLVED | nada além de hipótese para o pilot |

Regras:

- Todo item de taxonomia/knowledge registra `source_refs` **com nível**. Categoria cuja definição
  depende só de S4/AC é marcada assim na guideline.
- "STRONG" na pesquisa frequentemente significa **convergência entre fontes**, não força
  metodológica (ex.: seller responses STRONG com base em S3+S4). Aqui reclassificado por tipo.
- Citações da pesquisa **não foram reverificadas** nesta task. Antes de citar em material externo,
  verificar.

## Domain vs Taxonomy vs Guideline vs RAG

| Conceito | Destino | Por quê |
|---|---|---|
| `segment_id`, `call_id`, `episode_id` | DOMAIN | identidade/grounding (já existe) |
| `objection_segment_ids` / `context_segment_ids` | DOMAIN | evidência estrutural (já existe) |
| `resolution_status` (4 valores) | DOMAIN | já existe; semântica final em D6 |
| `category` (campo) | DOMAIN | já existe; **valores** = TAXONOMY versionada (CIT-M3) |
| SalesResistance, resistance_type | TAXONOMY (conceito) / REFERENCE_ONLY | sem necessidade estrutural |
| As 8 categorias (definição, evidência mínima) | TAXONOMY | provisórias, versionadas |
| Regras de fronteira (hesitação, brush-off, sócio ≠ autoridade, status quo) | GUIDELINE | decidem a anotação |
| Vocabulário de reação → rótulos do contrato | GUIDELINE | didático; rótulos do contrato mandam |
| Positive/negative signals, often_confused_with | GUIDELINE + RAG_KNOWLEDGE | ajudam anotador/extractor; nunca provam ocorrência |
| Seller response taxonomy | DEFER → TAXONOMY/RAG_KNOWLEDGE (Strategy) | sem consumidor hoje |
| Explicações HubSpot/Gong, "por que clarificar" | RAG_KNOWLEDGE | explicação/coaching futuro |
| Framework mapping (SPIN, MEDDPICC, BANT) | RAG_KNOWLEDGE / REFERENCE_ONLY | nunca labels |
| Source strength por item | TAXONOMY + RAG_KNOWLEDGE (metadado) | rastreabilidade |
| Hunt & Bashaw / Clark & Pinch ontologia | REFERENCE_ONLY | justificativa teórica |
| COUNTERARGUMENT, CONDITION | DEFER | colapsam em OBJECTION |
| IMPLICIT_RESISTANCE | REFERENCE_ONLY | viola dito × inferido |
| `concern_present`, `confidence`, primary/secondary category | REJECT (como campo) | ver seções acima |

## Knowledge Base implications

**Não é RAG agora.** O audit coloca RAG/vector DB fora de escopo; esta proposta não muda isso.
"RAG_KNOWLEDGE" aqui significa: *conhecimento que pode ser consultado para definir/explicar, e que
não pertence ao domínio*. Hoje ele vive como **Markdown versionado no Git**.

### Menor unidade de conhecimento

Reusar o **"Future category template" que já existe na guideline** e acrescentar só o que falta
para rastreabilidade:

```
concept_id            # ex.: category.PRICE_BUDGET  (tipo vem do prefixo)
version               # da taxonomia
status                # PROVISIONAL | ADOPTED | DEFERRED
definition
positive_signals      # absorve use_when
negative_signals      # absorve do_not_use_when + falsifying examples
often_confused_with
examples              # sintéticos, cada um com o rótulo esperado (inclui counterexamples e ambiguous)
source_refs           # [{ref, level: S1..S5|AC}]
```

Cortados da sugestão da task: `name` (= id), `concept_type` (prefixo do id), `use_when`/`do_not_use_when`
(duplicam signals), `counterexamples` separado (é um exemplo com rótulo negativo), `framework`
(é um `source_ref`), `source_strength` separado (vai no `source_ref`). **Não é schema executável.**

## Evidence boundary

Regra arquitetural:

> **RAG/knowledge pode sustentar** definição, interpretação, taxonomia, guideline e explicação.
> **RAG/knowledge NUNCA sustenta "isso aconteceu na Call".** Só evidência do transcript
> (`segment_id` da Call) sustenta ocorrência.

```
fonte externa:  "Budget objection é resistência ligada à verba…"   → define a categoria
transcript s12: "não temos verba este ano."                         → prova a ocorrência
episódio:       category = PRICE_BUDGET, objection_segment_ids = (s12)
```

Consequências: um extractor futuro que usa knowledge recuperado **não** pode citar o knowledge como
evidência; grounding (§12.1) só aceita `segment_id`s da Call. Knowledge recuperado entra na
proveniência do run (D4: versão da taxonomia/knowledge), nunca no episódio.

## Compatibility matrix

| Research proposal | Existing AI Closer | Compatibility | Decision | Destination |
|---|---|---|---|---|
| SalesResistance como conceito-pai | "objeção" da guideline já é ampla; sem entidade | PARTIAL | conceito classificatório, sem entidade (CIT-M1) | TAXONOMY / REFERENCE_ONLY |
| Objection (barreira ao avanço) | 4 testes da guideline | ALIGNED | KEEP | GUIDELINE |
| Atomic objection vs resistance episode | uma categoria por episódio; mesma âncora para várias | ALIGNED (contrato = opção atômica) | KEEP CURRENT CONTRACT (CIT-M2) | DOMAIN (já existe) |
| Resistance type (6) | inexistente; parte em GL-2 | NEW_CONCEPT | OBJECTION adotado; HESITATION/BRUSH_OFF regras PROVISIONAL; COUNTERARGUMENT/CONDITION DEFER; IMPLICIT REJECT | GUIDELINE / REFERENCE_ONLY |
| Objection category (8) | enum v0 (5 valores) no contrato | **CONFLICT** | candidatas provisórias; adoção no contrato = decisão humana (CIT-M3) | TAXONOMY |
| NEED_VALUE_FIT / TRUST_RISK | `no_need` / `trust_authority` | CONFLICT (split/alarga) | provisórias, AC | TAXONOMY |
| Seller Response (10, multilabel) | só segmentos do closer + count derivado; Strategy DEFER | NEW_CONCEPT | DEFER (CIT-M4) | futuro TAXONOMY/RAG |
| Prospect Reaction (10) | 6 rótulos de resposta, julgados, não armazenados | PARTIAL (GAP: clarificação) | mapear; manter derivado (CIT-M5) | GUIDELINE |
| Resolution (4) | 4 valores, §9, D6 OPEN | ALIGNED (PARTIAL em `partially_resolved`) | D6 não muda (CIT-M6) | DOMAIN (já existe) |
| "ainda preciso verificar se consigo pagar" | REJECT → `unresolved` (provisório) | ALIGNED no caso estabelecido; PARTIAL no isolado | wording futuro; D6 OPEN | GUIDELINE / D6 |
| Observed vs Inferred | guideline + protocolo | ALIGNED | KEEP; wording futuro | GUIDELINE |
| Uncertainty (5 estados) | protocolo | ALIGNED | KEEP | GUIDELINE |
| `confidence = LOW` / `TIMING?` | sem `confidence` (§13) | CONFLICT | REJECT; usar AMBIGUOUS | — |
| `concern_present` | teste 4 da guideline | PARTIAL | REJECT como campo; fronteira no pilot | GUIDELINE |
| Framework mapping | guideline: externos são só sementes | ALIGNED | frameworks nunca labels | RAG_KNOWLEDGE / REFERENCE_ONLY |
| Source strength | inexistente como regra | NEW_CONCEPT | níveis S1–S5 + AC por item | TAXONOMY / RAG metadado |
| Resolution ≠ Deal outcome | ADR-001, guideline | ALIGNED | KEEP | DOMAIN |

## Decisions

| ID | Pergunta | Proposta | Estado |
|---|---|---|---|
| CIT-M1 | SalesResistance vira entidade? | Não. Conceito classificatório | PROPOSED (sem mudança de contrato) |
| CIT-M2 | ObjectionEpisode continua unidade fundamental? | Sim; contrato já é a opção atômica | PROPOSED — KEEP CURRENT CONTRACT |
| CIT-M3 | As 8 categorias entram como provisional v0.1? | Como **candidatas para o workshop TAX**. Recomendação: se Gabriel + Otávio aceitarem, a guideline v0.1 usa as 8 no pilot D3 (labels de anotação); o enum do contrato `ObjectionEpisode` só muda em D7, depois do pilot (antes de existir gold não-pilot, para não regenerar ids). `ObjectionEvent` v0 **nunca** muda (D1). Alternativa: pilot com enum v0 e 8 categorias só como referência | **OPEN — humano** (CONFLICT com §6/§18) |
| CIT-M4 | Seller Response é multilabel? | Sim conceitualmente, ancorado em `segment_id`; taxonomia inteira DEFER, fora do pilot | PROPOSED |
| CIT-M5 | Prospect Reaction armazenada ou derivada? | Derivada/julgada; single-label por resposta; vocabulário da pesquisa mapeado para rótulos do contrato | PROPOSED — KEEP CURRENT CONTRACT |
| CIT-M6 | D6 muda com a pesquisa? | Não. Pesquisa reforça REJECT → `unresolved` no caso estabelecido; `partially_resolved` sem suporte de fonte além do MIXED | D6 **OPEN** |
| CIT-M7 | O que fica só no RAG/knowledge? | explicações de fontes, framework mapping, seller response (até Strategy), source refs; nunca como evidência | PROPOSED |

## Open questions

| ID | Pergunta | Quem/como fecha |
|---|---|---|
| CIT-O1 | Pilot usa 8 categorias ou enum v0? (CIT-M3) | workshop TAX (Gabriel + Otávio) |
| CIT-O2 | NEED/VALUE/FIT e TRUST/RISK: fundir fica? | notas do pilot |
| CIT-O3 | Fronteira concern × objection e brush-off × timing | divergências DETECTION/CATEGORY do pilot |
| CIT-O4 | REQUESTS_CLARIFICATION como última resposta: não-sobrescrevente? | guideline v0.1 + D6 |
| CIT-O5 | IMPLEMENTATION_INTEGRATION e TERMS_PROCESS aparecem nas operações reais? | pilot; se ausentes, MERGE em OTHER |
| CIT-O6 | "Solução interna/planilha" = NEED_VALUE_FIT ou COMPETITION? | pilot |
| D3, D5, D6, TAX | inalteradas | ver contrato §19 |

## Proposed minimal v0.1

Tudo abaixo é **PROVISIONAL** até o pilot.

1. **Unidade:** `ObjectionEpisode` v1 inalterado. Sem entidade de resistência.
2. **Detecção:** definição de objeção da guideline + regras de fronteira: hesitação sem barreira →
   AMBIGUOUS/UNKNOWN; brush-off sem motivo → AMBIGUOUS; condição e contra-argumento → OBJECTION;
   resistência implícita não se anota.
3. **Categoria:** 8 candidatas + `OTHER`; UNKNOWN/AMBIGUOUS como status. Cada uma com evidência
   mínima, `often_confused_with`, ao menos um falsifying example e nível de fonte. Sujeito a CIT-M3.
4. **Handling:** como hoje (segmentos do closer em contexto). Sem taxonomia de resposta.
5. **Reação:** rótulos do contrato; vocabulário da pesquisa como guia.
6. **Resolução:** 4 valores do contrato; `partially_resolved` = MIXED (mesma categoria); D6 aberta.
7. **Regra central:** *classify what the transcript supports; a topic is not an objection unless it
   functions as resistance; a seller response is not a resolution; silence is not acceptance; lack
   of evidence is UNKNOWN, not ABSENT.*

## Deferred concepts

`ResistanceEpisode`/entidade pai; `resistance_type` como campo; COUNTERARGUMENT; CONDITION como
tipo; IMPLICIT_RESISTANCE (reference only); seller response taxonomy (Strategy); ordem/sequência de
respostas; primary/secondary category; `objection_subtype`; split NEED/VALUE/FIT e TRUST/RISK;
STATUS_QUO, PRODUCT, PROCUREMENT; `concern_present`; `confidence`; estado "pending" (D6);
infraestrutura de RAG/knowledge (retrieval, embeddings, vector DB); Challenger/Solution/GAP Selling.

## Next steps

1. Revisão humana deste documento; decidir **CIT-M3** no workshop TAX (Gabriel + Otávio).
2. Mergear `docs/reference-repos-audit` (ou corrigir os links para `../references/` em `main`).
3. Guideline v0.1 (task própria, **depois** de CIT-M3): categorias no template existente com nível de
   fonte; corrigir o exemplo "sócio"; regras de hesitação/brush-off/status quo; cadeia
   evidence → observation → interpretation; mapeamento de reação; CIT-O4.
4. Dry run do calibration kit; depois pilot D3 com a guideline vigente; registrar notas NEED/VALUE/FIT
   e TRUST/RISK.
5. Só depois do pilot: D6, TAX final, e (D7) ADR + enum do `ObjectionEpisode`.
