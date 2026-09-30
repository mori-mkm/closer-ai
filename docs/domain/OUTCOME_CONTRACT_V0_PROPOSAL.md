# Outcome Contract v0 — Proposal

Status: **PROPOSAL rev. 2 — não implementado.** Nenhum código muda com este documento. Contrato
vigente continua sendo `Deal.outcome` (`src/closer_ai/domain/deal.py`,
`docs/domain/DEAL_MODEL.md`).

> **Current status (2026-09-29):** aceito como [ADR-001](../decisions/ADR_001-outcome-contract-v0.md);
> o **núcleo estrutural** foi implementado depois (`src/closer_ai/domain/outcome.py`,
> `commercial_state.py`), e `Deal.outcome` passou a ser só projeção legada do CRM. A **policy
> comercial** (§7.3, §9.2–§9.4) continua não implementada (D-G1/D-G2/D-G5/D-G6). O parágrafo acima é
> o status original desta proposta.

Pergunta:

> Qual é o menor contrato de Outcome capaz de representar o estado comercial de uma
> oportunidade sem confundir CRM raw state com verdade canônica?

Resposta curta: **três entidades append-only novas**, sem alterar `Deal`, `StageEvent` ou
matching:

- `OutcomeEvidence` — uma **observação** de uma fonte, com o estado bruto preservado e um
  **sinal** interpretado.
- `EvidenceDisposition` — correção explícita de uma evidência (invalidada ou remapeada), sem
  apagar nada; define o **conjunto elegível**.
- `OutcomeAssessment` — uma decisão (automática ou humana) sobre o outcome do Deal, numa
  **cadeia linear** com CAS; a decisão **autoritativa** é derivada da cadeia (humano mais
  recente, senão o head).

Rev. 2 corrige: elegibilidade de evidência (P0-1), autoridade humana persistente (P0-2),
override como decisão inteira (P0-3), reversal como modificador (P0-4), identidade da
observação (P0-5), concorrência/bifurcação (P1).

Status canônicos v0: **`won`, `rejected`, `open`, `unknown`**. `future` vira **`open` +
sinal `deferral`**; `stale` não existe; no-contact **nunca** vira `rejected`.

## 1. Problem

A auditoria real do CRM AgroTalento (relatada por Matheus; os achados **não** estão
versionados neste repo e nenhum dado real foi usado aqui) mostrou que o CRM não representa de
forma confiável os resultados negativos pós-call. Leads que rejeitaram a oferta:

- continuam abertos no CRM;
- aparecem como unknown;
- são fechados por automação/no-contact (Salesbot);
- têm o retorno registrado só em planilhas/retorno dos closers;
- têm cards paralelos;
- não têm motivo de perda confiável.

Logo **CRM status ≠ Canonical Outcome**. Outcome Intelligence treinada sobre o status bruto do
CRM aprenderia ruído de higiene de CRM, não comportamento comercial.

## 2. Current model (código é a fonte da verdade)

| Item | Estado atual (`domain/deal.py`) |
|---|---|
| `Deal.outcome` | `Literal["open", "won", "lost", "unknown"]`, sem default |
| `Deal.closed_at` | obrigatório ⟺ outcome ∈ {won, lost}; `closed_at >= created_at` |
| `Deal.current_stage` | `created`/`qualification`/`proposal`/`negotiation`/`other`; ortogonal ao outcome |
| `StageEvent` | append-only, id inclui `occurred_at`; `external_stage_id` guarda id bruto |
| Identidade | `deal_id = hash(company_id, source, external_id)` → **1 Deal = 1 registro do CRM** |
| Histórico de outcome | nenhum; `Deal` é snapshot frozen; "promover a entidade se aparecer requisito de auditoria (chargebacks, reopened deals)" — o requisito apareceu |
| `STALE` | explicitamente rejeitado (threshold é decisão de produto aberta) |
| Matching | `CallDealMatch` append-only; "match atual" não é autoritativo (DEP-1, `OBJECTION_EPISODE_V1_PROPOSAL.md` §19) |

### Auditoria

| Classe | Itens |
|---|---|
| **CURRENT** | outcome é um campo de snapshot do Deal, preenchido por quem ingere o CRM; sem evidência, sem fonte, sem histórico, sem confiança |
| **KEEP** | Deal como unidade comercial; Call sem outcome; Stage ⟂ Outcome; sem default; `unknown` legítimo; sem `STALE`; ids determinísticos sha256; eventos append-only com timestamp no id (padrão `StageEvent`) |
| **LIMITATION** | (1) `Deal.outcome` na prática é o **estado do CRM normalizado**, mas o docstring o trata como verdade comercial; (2) `lost` mistura rejeição comercial com fechamento por automação; (3) nenhum lugar guarda o estado bruto do CRM (`external_stage_id` só existe no `StageEvent`, e só para stage); (4) sem histórico nem motivo da mudança; (5) `closed_at` vem do CRM, que fecha por automação; (6) 1 Deal = 1 card: cards paralelos viram Deals distintos |
| **MUST EVOLVE** | camada canônica separada do estado da fonte; evidência com fonte e tempo; histórico auditável; conflito → revisão, não precedência cega |
| **DEFER** | consolidação de cards em oportunidade canônica (DEP-2); motivo de rejeição tipado; data de retomada; `stale_candidate`; valor/receita realizada |

## 3. Observed CRM limitations → consequência no contrato

| Achado | Consequência |
|---|---|
| Rejeitado mas aberto no CRM | CRM `open` sozinho **não** sustenta `open` canônico (§4) |
| Fechado por Salesbot/no-contact | sinal `no_contact`, **nunca** `rejection` (§4, invariante I6) |
| Retorno só em planilha do closer | fonte `closer_report` de primeira classe (§7.1) |
| Cards paralelos | evidência referencia o registro de origem; consolidação é DEP-2 (§14.1) |
| Motivo de perda não confiável | sem `rejection_type` em v0 (§4) |
| Silêncio no CRM | não é abandono; sem `stale` (§4.6) |

## 4. Outcome semantics

Status canônicos v0 (`OutcomeStatus`):

| Status | Significado comercial | Evidência mínima (invariante I4) |
|---|---|---|
| **`won`** | a venda aconteceu | ≥ 1 evidência com sinal `sale` |
| **`rejected`** | o lead **decidiu** não comprar esta oportunidade | ≥ 1 evidência com sinal `rejection` |
| **`open`** | a oportunidade está **comercialmente viva**: há engajamento ativo ou adiamento combinado, sem evidência terminal vigente | ≥ 1 evidência com sinal `active` ou `deferral` |
| **`unknown`** | a evidência não sustenta nenhum dos três | nenhuma exigida |

Nome `rejected` (não `lost`) de propósito: distingue a interpretação canônica do `lost` do
CRM, que mistura rejeição com automação.

### 4.1 WON

| Evidência | Sinal | Força (policy, §7.3) |
|---|---|---|
| pagamento confirmado | `sale` | high |
| pós-venda / membership ativa | `sale` | high |
| confirmação humana (operador) | `sale` | high |
| CRM em estado de venda ganha (ex. "VENDA GANHA") | `sale` | medium |
| closer diz "fechou" | `sale` | medium |

CRM "VENDA GANHA" sozinho é suficiente para `won` com confiança `medium`; com pagamento ou
pós-venda, `high`. A auditoria achou problema nos **negativos**; positivos do CRM não foram
apontados como não confiáveis — mesmo assim ficam abaixo de pagamento.

### 4.2 REJECTED

**Rejeição comercial ≠ no-contact/automação.**

- "Não vou comprar", "não é pra mim", "fechei com outro" → sinal **`rejection`**.
- Salesbot encerrou após tentativas sem resposta; lead sumiu → sinal **`no_contact`**.

`no_contact` **nunca** sustenta `rejected` (I6). Um deal fechado só por automação fica
`unknown` (ver D-G3: o negócio pode querer tratar ghosting como perda em analytics — isso é
um rótulo derivado futuro, não o status canônico).

**`rejection_type` não entra no v0.** Razões:

1. o motivo de perda do CRM foi apontado como não confiável;
2. motivos (preço, timing, fit...) duplicam a taxonomia de objeções e criariam uma segunda
   fonte de verdade sobre "por que";
3. a distinção que importa agora — rejeição vs. no-contact — já é feita por sinal/status.

A pergunta "rejeitou por quê?" será respondida por Outcome Intelligence cruzando
`ObjectionEpisode` × `rejected`, não por um enum no outcome. Deferido.

### 4.3 OPEN

**Não** é "o card está aberto". É: existe evidência de **engajamento ativo** (closer reporta
negociação em andamento, proposta enviada e em discussão, reunião marcada) ou **adiamento
combinado** (`deferral`), e nenhuma evidência terminal mais recente vigente.

CRM `open` sozinho → sinal `unclassified` → não sustenta `open` → status `unknown`.

### 4.4 FUTURE → `open` + `deferral`

"PROPOSTA FUTURA", "me liga no próximo trimestre", "retomar em março" → sinal **`deferral`**,
status **`open`**. FUTURE não é status próprio porque não é um resultado — é um sub-estado de
uma oportunidade viva, e como status separado exigiria regras de transição próprias
(é terminal? vira `unknown` quando a data passa?) sem ganho. A visão "open adiado" é
**derivável**: status `open` cuja evidência de suporte mais recente tem sinal `deferral`.

**Data de retomada não entra no v0** (fica no registro de origem via `source_record_ref`).
Se o negócio precisar de fila de retomada, é campo aditivo futuro (D-G7).

Se o negócio considerar "PROPOSTA FUTURA" como perda (é comum em algumas operações), o
mapeamento CRM → sinal muda para `rejection` — decisão de Gabriel (D-G4), sem mudar o
contrato.

### 4.5 UNKNOWN

Estado legítimo e **default honesto**: sem evidência, só evidência `unclassified`/
`no_contact`, ou conflito não adjudicado (§9). Correctness > coverage.

### 4.6 STALE

**Não existe como status.** Silêncio no Kommo ≠ abandono (há pós-call fora do CRM).
`stale_candidate` pode existir no futuro como **sinal derivado de analytics** (ex.: sem
evidência nova há N dias), nunca gravado como outcome, e só depois de a regra de negócio ser
validada (D-G8). Mesma posição já registrada em `deal.py`.

## 5. Raw vs canonical state

Três camadas, nunca misturadas:

| Camada | Onde | Quem produz | Mutável? |
|---|---|---|---|
| **Source state** (raw) | `OutcomeEvidence.raw_state` (+ `source_record_ref`) | ingestão, verbatim | nunca — nova observação = nova evidência |
| **Sinal** (interpretação de 1 evidência) | `OutcomeEvidence.signal` | mapeamento versionado (CRM) ou julgamento (humano/closer) | nunca |
| **Canonical outcome** (interpretação do conjunto) | `OutcomeAssessment.status` | policy versionada ou humano | nunca — nova avaliação supersede |

- `crm_stage_raw`/`crm_status_raw` = `raw_state` de evidências `source="crm_status"`,
  **verbatim** (ex. `"VENDA GANHA"`, `"PROPOSTA FUTURA"`, `"Fechado - perdido"`). Um campo
  só: stage e status do CRM chegam como observações separadas, cada uma com seu `raw_state`.
- Texto livre (nota do CRM, planilha, mensagem) **nunca** é copiado: só `source_record_ref`
  (PII fica na fonte, como em `MatchEvidence.detail`).
- `Deal.outcome`/`Deal.closed_at` **continuam existindo e não mudam**; passam a ser
  documentados como a **projeção normalizada do estado do CRM** (source state), não o outcome
  canônico (D-M1). Nunca são sobrescritos pela camada canônica, e a camada canônica nunca é
  lida deles sem passar por uma evidência.

## 6. Conceitos distintos

| Conceito | O que é | Armazenado? |
|---|---|---|
| **Raw observation** | o que a fonte disse, verbatim (`raw_state`, `source_record_ref`, `observation_key`, `observed_at`) | sim, dentro de `OutcomeEvidence` |
| **Evidence** | uma raw observation + o `signal` que ela afirma, atribuída a um Deal | sim, `OutcomeEvidence` (append-only) |
| **Eligible evidence** | evidências do Deal **sem** disposição (§7.2) no momento da avaliação | conceito; o snapshot usado fica em `OutcomeAssessment.eligible_evidence_ids` |
| **Supporting evidence** | o subconjunto das elegíveis que sustenta o status escolhido (§9) | `OutcomeAssessment.supporting_evidence_ids` (⊆ eligible) |
| **Automatic candidate** | a decisão que a policy (`rule`) produz | sim, como `OutcomeAssessment` com `decision_method="rule"` |
| **Authoritative canonical decision** | a decisão que governa o outcome do Deal (§8.2) | conceito derivado: aponta para **um** `OutcomeAssessment` existente, inteiro |

Autoridade é **derivada**, não armazenada: nenhum campo novo para isso.

## 7. Evidence contract

### 7.1 `OutcomeEvidence`

| Field | Purpose | Observable? | Derived? | Required? | MVP? | Why |
|---|---|---|---|---|---|---|
| `schema_version` | versionar | — | — | default | sim | padrão do repo |
| `evidence_id` | identidade da **observação** | — | sim (§11) | sim | sim | idempotência; colisão (P0-5) |
| `deal_id` | Deal ao qual foi atribuída | atribuição é julgamento | — | sim | sim | outcome pertence ao Deal |
| `source` | tipo de fonte | sim | — | sim | sim | policy de força |
| `source_record_ref` | id opaco do registro na fonte | sim | — | sim | sim | auditoria; cards paralelos; nunca PII |
| `observation_key` | discriminador estável da observação **dentro** do registro (campo/path, id de evento, versão, linha/coluna) | sim | — | sim, não vazio | sim | **rev. 2 (P0-5):** stage e status do mesmo card no mesmo instante são observações diferentes |
| `raw_state` | estado bruto verbatim de fonte estruturada | sim | — | obrigatório p/ `crm_status`; `None` p/ texto livre | sim | preservar CRM raw |
| `signal` | o que a evidência afirma | não | mapeamento/julgamento | sim | sim | separa raw de interpretação |
| `observed_at` | quando o fato ocorreu na fonte (tz-aware) | sim | — | sim | sim | temporalidade |

`observation_key` é um campo **genérico** (string); o valor é específico da fonte
(ex.: `"stage"`, `"status"`, `"event:8812"`, `"row:14"`), mas o schema não conhece nenhum
provedor.

`source` (8, fechado): `crm_status`, `crm_note`, `closer_report`, `payment`, `post_sale`,
`automation`, `human`, `other`. `parallel_card` = `crm_*` com `source_record_ref` de outro card;
`membership` ∈ `post_sale`; `salesbot` ∈ `automation`.

`signal` (7, fechado):

| Valor | Afirma |
|---|---|
| `sale` | a venda aconteceu |
| `rejection` | o lead decidiu não comprar |
| `active` | negociação viva agora |
| `deferral` | adiamento combinado |
| `no_contact` | sem resposta / encerrado por falta de contato |
| `reversal` | venda desfeita (reembolso, estorno, cancelamento) — **modificador**, não classe de outcome (§9.3) |
| `unclassified` | estado observado sem significado canônico (ex. CRM "open", stage intermediário) |

Mapeamento `raw_state` do CRM → `signal`: tabela versionada de Gabriel (DEP-3/D-G1); não
mapeado → `unclassified`.

### 7.2 Eligibility — `EvidenceDisposition` (rev. 2, P0-1)

**Problema:** evidência é imutável e append-only; sem um registro de correção, a policy
reconsumiria uma evidência errada (pagamento atribuído ao Deal errado; rejeição remapeada
para no-contact) a cada nova avaliação.

**Alternativas:**

| Opção | Como | Veredito |
|---|---|---|
| A — só snapshot na avaliação | cada avaliação guarda o conjunto elegível; a próxima herda "snapshot anterior ∪ evidência nova" | rejeitada **sozinha**: invalidação vira omissão silenciosa (sem motivo, sem autor), e "evidência nova desde o snapshot" exige ordem de ingestão que o contrato não tem |
| B — disposição explícita por evidência | registro append-only pequeno: "evidência X foi invalidada / remapeada para Y, por quem, quando" | **escolhida** para definir elegibilidade |
| C — `supersedes_evidence_id` na própria evidência | remap vira nova evidência apontando a antiga | rejeitada: não representa invalidação pura (atribuição errada não tem substituta) sem inventar um sinal falso como "void" |

**Escolha: B para definir, A para registrar.** `EvidenceDisposition` define elegibilidade;
`OutcomeAssessment.eligible_evidence_ids` registra o snapshot usado (auditoria + CAS, §10).

`EvidenceDisposition` (append-only, frozen):

| Field | Purpose | Required? |
|---|---|---|
| `schema_version` | versionar | default |
| `disposition_id` | determinístico sobre todos os campos de conteúdo (§11) | sim |
| `evidence_id` | evidência afetada | sim |
| `kind` | `invalidated` \| `remapped` | sim |
| `replacement_evidence_id` | nova evidência com o sinal corrigido | ⟺ `remapped` |
| `decided_by` | `human` \| `mapping` | sim |
| `mapping_version` | versão da tabela DEP-3 que remapeou | ⟺ `decided_by="mapping"` |
| `decided_at` | quando | sim, tz-aware |

**Definições precisas:**

- **Invalidated:** a evidência não deveria estar neste Deal ou não é uma observação válida
  (atribuição errada, dado corrompido, card errado). Só `decided_by="human"`. Sem
  substituta.
- **Remapped (superseded):** a observação é válida, mas o `signal` estava errado. A
  substituta tem **o mesmo** `deal_id`, `source`, `source_record_ref`, `observation_key`,
  `raw_state` e `observed_at`, e `signal` diferente (logo `evidence_id` diferente, §11). Pode
  ser `human` ou `mapping` (nova versão da tabela DEP-3).
- **Eligible** (para um Deal, num momento) = evidências do Deal **sem nenhuma disposição**.
- **Supporting** = subconjunto das elegíveis citado pela decisão como sustentação do status.

Regras:

- Nada é apagado: evidência e disposição ficam para auditoria.
- No máximo **uma** disposição por evidência; uma segunda é **hard error**.
- Disposição não é reversível em v0. Para "des-invalidar", um humano registra uma **nova**
  evidência `source="human"` (novo `evidence_id`) — reinstauração explícita e auditável.
- A policy **nunca** opera sobre "toda evidência já observada", só sobre o conjunto elegível.

### 7.3 Força da evidência (policy, não campo)

| source \ signal | sale | rejection | active / deferral | no_contact | reversal |
|---|---|---|---|---|---|
| `human` | high | high | high | high | high |
| `payment` / `post_sale` | high | — | — | — | high |
| `closer_report` | medium | medium | medium | medium | medium |
| `crm_status` (estado mapeado) | medium | low (D-G2) | low | medium | medium |
| `crm_note` | low | low | low | low | low |
| `automation` | — | **proibido** (I6) | — | medium | — |
| `other` | low | low | low | low | low |

"—" = não esperado; se ocorrer, `low`. Versionada com a policy (`policy_version`).

## 8. Canonical decision — `OutcomeAssessment` e autoridade

### 8.1 Schema discipline

| Estado | Detalhe |
|---|---|
| **CURRENT (rev. 1)** | `assessment_id`, `deal_id`, `status`, `evidence_ids`, `confidence_level`, `needs_human_review`, `decision_method`, `policy_version`, `effective_at`, `decided_at`, `supersedes_assessment_id`, `schema_version` |
| **WHY IT FAILS** | (1) `evidence_ids` misturava "elegível" com "suporte" e não impedia reuso de evidência inválida (P0-1); (2) autoridade humana dependia de "o head é humano" e sumia após uma avaliação `rule` (P0-2); (3) override trocava só `status` (P0-3); (4) supersessão permitia bifurcação (P1) |
| **MINIMAL NEW INFO** | renomear `evidence_ids` → `supporting_evidence_ids`; **+1 campo** `eligible_evidence_ids`; autoridade **derivada** da cadeia (zero campos); `supersedes_assessment_id` passa a ser o **expected head** do CAS (zero campos); + `EvidenceDisposition` (§7.2) |

### 8.2 Campos

| Field | Purpose | Required? | Why |
|---|---|---|---|
| `schema_version` | versionar | default | padrão |
| `assessment_id` | identidade | sim | §11 |
| `deal_id` | Deal avaliado | sim | — |
| `status` | `won`/`rejected`/`open`/`unknown` | sim, sem default | a resposta |
| `supporting_evidence_ids` | evidências que sustentam **este** status | sim; ≥ 1 exceto `unknown` | "qual evidência sustenta?" |
| `eligible_evidence_ids` | snapshot do conjunto elegível usado nesta avaliação | sim (pode ser vazio) | auditoria; CAS de elegibilidade (§10) |
| `confidence_level` | `high`/`medium`/`low` | `None` ⟺ `unknown` | categórico, sem float |
| `needs_human_review` | esta decisão pede humano | sim, sem default | §9.4 |
| `decision_method` | `rule` \| `human` | sim | autoridade (§8.3) |
| `policy_version` | policy + tabela de força | ⟺ `rule` | reprodutibilidade |
| `effective_at` | quando o outcome passou a valer no mundo | ⟺ `won`/`rejected` | alinhar calls antes/depois |
| `decided_at` | quando foi registrada | sim | auditoria; id |
| `supersedes_assessment_id` | **head esperado** no momento da escrita | `None` só na primeira | cadeia linear + CAS (§10) |

Rejeitados nesta revisão: `authority` armazenado (derivável), `candidate_*` paralelos
(o candidato **é** a própria avaliação `rule`), `invalidated_evidence_ids` na avaliação
(correção de evidência não é decisão de outcome).

### 8.3 Autoridade (P0-2, P0-3)

Numa cadeia linear de avaliações de um Deal:

> **Decisão autoritativa canônica** = a avaliação `decision_method="human"` **mais recente
> na cadeia**, se existir; senão, o **head** (avaliação `rule` mais recente).

Consequências:

- **Autoridade humana persiste** até outra avaliação `human` a substituir. Avaliações `rule`
  posteriores ficam na cadeia como **candidatos automáticos**: registram o que a policy
  concluiu e se pede revisão, mas **não** governam o outcome.
- Não existe "devolver autoridade à regra" em v0 (deferred): enquanto houver humano na
  cadeia, só humano muda o canônico.
- **Override é a decisão inteira:** o canônico é **um registro existente, inteiro** —
  `status`, `supporting_evidence_ids`, `confidence_level`, `effective_at`,
  `decision_method` e `needs_human_review` vêm todos do mesmo `OutcomeAssessment`. Nunca se
  monta um candidato e se troca só o `status`.
- **Revisão pendente** do Deal = `head.needs_human_review` (o candidato mais recente pode
  pedir revisão de uma decisão humana vigente).
- Visão de consumo de um Deal: `(canonical_decision, review_pending)`.
- **Regra de consumo (hard, I16):** um outcome só é **utilizável** (Outcome Intelligence,
  métricas, treino, qualquer analytics) se `review_pending = false`. Com revisão pendente, o
  outcome do Deal é **indisponível para consumo** — a decisão canônica continua registrada
  para auditoria, mas não é lida como verdade. Ex.: humano `won` + reembolso posterior →
  canônico registrado `won`, **utilizável: não** até um humano decidir.
- Decisão `human`: `needs_human_review=false`; `confidence_level="high"` (ou `None` se
  `unknown`); `supporting_evidence_ids ⊆ eligible_evidence_ids` como qualquer outra; o
  humano escolhe `effective_at` para `won`/`rejected`.

## 9. Policy (`rule`) — máquina de estados

Toda avaliação automática segue **exatamente** esta ordem. Nenhum resultado depende de ordem
implícita.

| # | Passo | Falha/saída |
|---|---|---|
| 1 | **Deal:** o `deal_id` existe (DEP-1/DEP-2 não são resolvidos aqui; card = Deal em v0) | Deal inexistente → erro, nada escrito |
| 2 | **Head linear:** carregar a cadeia; verificar linearidade (cada avaliação supersede exatamente a anterior; um único head) | bifurcação → **canônico indisponível**; parar sem escrever; reparo manual (§10.2) |
| 3 | **Autoridade:** avaliação `human` mais recente na cadeia, se houver | — |
| 4 | **Conjunto elegível E:** evidências do Deal sem disposição | — |
| 5 | **Validar evidências de E:** ids re-derivam; mesmo `deal_id`; I2 | inválida → hard error, parar |
| 6 | **Seleção de outcome (candidato)** sobre E, §9.2 | → (status, supporting, confidence, effective_at) |
| 7 | **Modificador de reversão** §9.3 | pode substituir o candidato por `unknown` |
| 8 | **Revisão** §9.4 | → `needs_human_review` |
| 9 | **Resolução de autoridade:** a nova avaliação é `rule`; se existe autoridade humana (passo 3), ela é **candidato não autoritativo**; senão, torna-se o canônico | — |
| 10 | **No-op:** (a) se (status, supporting, confidence, effective_at, review, E, `policy_version`) do candidato = do head → não escrever; (b) se existe autoridade humana e E == `eligible_evidence_ids` da decisão humana (nada mudou desde que o humano decidiu) → não escrever | — |
| 11 | **Validar invariantes** (§12) do novo registro contra E e a cadeia | violação → erro, nada escrito |
| 12 | **Append atômico** com `supersedes_assessment_id = head` e `eligible_evidence_ids = E` (CAS, §10) | CONFLICT → recarregar, recomputar do passo 1 |

### 9.1 Pré-filtro

Dentro de E, descartar sinais `unclassified` para a seleção (continuam em E).

### 9.2 Seleção de outcome (passo 6)

Buckets: `sale`→`won`; `rejection`→`rejected`; `active`/`deferral`→`open`. `no_contact` e
`reversal` **não** implicam status. Avaliar em ordem; o primeiro que se aplica decide:

1. **Evidência de fonte humana:** se há evidência `source="human"` com sinal de bucket, vale
   a de `observed_at` mais recente → status do bucket, `high`, supporting = essa evidência.
   Empate de `observed_at` com buckets diferentes → `unknown`, revisão.
2. **Um bucket só com evidência ≥ medium** → esse status; confidence = força da mais forte;
   supporting = as evidências ≥ medium desse bucket.
3. **Conflito (≥ 2 buckets com evidência ≥ medium):** ordem indeterminável (mesmo
   `observed_at`) → `unknown` + revisão; senão, bucket da evidência ≥ medium mais recente,
   supporting = as evidências ≥ medium de ambos os buckets, revisão **exceto** se a mais
   recente for `high`.
4. **Só evidência `low`:** um bucket → esse status `low`; buckets contraditórios →
   `unknown`.
5. **Terminal:** nenhum bucket com evidência → `unknown`, `confidence=None`, supporting vazio.

`effective_at` do candidato `won`/`rejected` = `observed_at` da evidência de suporte **mais
antiga do bucket vencedor** (em conflito, só as do bucket vencedor contam).

`confidence_level` é definido **só** aqui; evidência contrária não o rebaixa.

### 9.3 Reversal é modificador (passo 7, P0-4)

`reversal` **não** é classe de outcome e **nunca** vira `rejected` (reembolso ≠ decisão de
não comprar).

| Caso | Condição (em E) | Candidato |
|---|---|---|
| A | existe `reversal` com `observed_at` posterior à `sale` mais recente | `unknown`, `confidence=None`, `effective_at=None`, supporting = essa `sale` + esse `reversal`, **revisão** |
| C | existe `reversal` e nenhuma `sale` elegível anterior | `unknown`, revisão, supporting = o `reversal` |
| — | `sale` posterior ao último `reversal` (recompra) | seleção normal (§9.2) |

Caso B (autoridade humana existe): o modificador produz o candidato A/C normalmente; o
passo 9 o registra como **não autoritativo**; a decisão humana continua canônica, com
revisão pendente.

Por quê `unknown` e não `won`: após reembolso, "a venda está de pé?" não é representável com
segurança pela taxonomia v0. Estado `cancelled`/`refunded`/`churned` é **DEFERRED** (D-G5).

### 9.4 Revisão (passo 8)

**Sem autoridade humana:** `needs_human_review = true` se qualquer um de 1–2 abaixo.

**Com autoridade humana:** só há avaliação `rule` se E mudou desde a decisão humana (passo
10b). Então `needs_human_review = true` se: critério 4; **ou** critério 1, 2 ou 3 **causado por
pelo menos uma evidência nova** — elegível agora e ausente de `eligible_evidence_ids` da
decisão humana (para 3: presente em `supporting_evidence_ids` do candidato). O que o humano já
viu não reabre revisão: ex. humano `won` após reembolso; chega uma observação nova
`unclassified` → candidato ainda `unknown` pelo mesmo reembolso → **sem** revisão.

Critérios:

1. conflito em §9.2 (item 1 com empate, ou item 3);
2. modificador de reversão aplicado (§9.3);
3. existe autoridade humana e o candidato difere dela em `status`;
4. existe autoridade humana e alguma evidência em `supporting_evidence_ids` **dela** não está
   mais em E (evidência citada pelo humano foi invalidada/remapeada).

Senão, `false`. Nunca "desligado" por um passo posterior.

## 10. Concorrência e linearidade (P1)

### 10.1 CAS

- Histórico de avaliações é **linear** por Deal. Sem branching em v0.
- Toda escrita declara `supersedes_assessment_id` = **head esperado** (`None` se a cadeia
  está vazia).
- A escrita só é aceita se:
  1. head esperado == head atual; **e**
  2. `eligible_evidence_ids` == conjunto elegível atual (nenhuma evidência/disposição nova
     desde a leitura).
- Caso contrário → **CONFLICT**: operação rejeitada antes de persistir; o caller recarrega,
  recomputa (passo 1) e tenta de novo.
- Aplica-se a `rule` **e** `human`.
- **Protocolo humano:** a decisão humana é preparada contra um snapshot (head H, conjunto
  elegível E) mostrado ao humano e gravada com esses H e E. Em CONFLICT, a decisão humana
  **não** é recomputada nem reaplicada automaticamente (a policy §9 é só para `rule`): ela é
  rejeitada e devolvida ao humano com o novo head e o novo E, e ele decide de novo
  (inclusive reenviar o mesmo bundle, que é revalidado contra o novo E — I12).
- Append de evidência e de disposição **não** fazem CAS na cadeia de avaliações; apenas
  disparam reavaliação. A condição 2 garante que nenhuma avaliação seja gravada com base em
  evidência já invalidada.

Ex.: duas avaliações partem do head A. A primeira grava `A → B`. A segunda tenta `A → C`:
head atual é B ≠ A → CONFLICT; recarrega B, recomputa; grava `B → C'` ou no-op.

### 10.2 Fork legado / corrompido

Se uma bifurcação aparecer (importação, bug, dado legado):

- canônico = **indisponível**;
- o resolver automático **não** escolhe vencedor (nem por timestamp);
- reparo humano/manual fora do contrato.

Reconciliação multi-parent: **DEFERRED**.

## 11. IDs (P0-5)

Mesma técnica do repo (sha256 sobre `json.dumps(..., ensure_ascii=True, separators=(",",
":"))`, 24 hex, timestamps via `_canonical_timestamp`):

```
raw_digest    = sha256_hex_lower(utf8_bytes(raw_state)) se raw_state não é None, senão ""
evidence_id   = "oev_" + h(["outcome_evidence", deal_id, source, source_record_ref,
                            observation_key, raw_digest, signal, ts(observed_at)])
assessment_id = "oas_" + h(["outcome_assessment", deal_id, status,
                            sorted(supporting_evidence_ids), sorted(eligible_evidence_ids),
                            confidence_level, needs_human_review, decision_method,
                            policy_version, ts_or_null(effective_at), ts(decided_at),
                            supersedes_assessment_id])
disposition_id = "odp_" + h(["evidence_disposition", evidence_id, kind,
                             replacement_evidence_id, decided_by, mapping_version,
                             ts(decided_at)])
```

- Stage `"NEGOCIAÇÃO"` e status `"ABERTO"` do mesmo card no mesmo instante: `observation_key`
  (`"stage"` × `"status"`) e `raw_digest` diferem → ids diferentes.
- `raw_state` entra só como digest (sem texto no id).
- `signal` entra no id: remap gera nova evidência (e disposição da antiga, §7.2).
- **Regra geral (as três entidades):** o id é o hash de **todos** os campos de conteúdo do
  registro (tudo exceto o próprio id e `schema_version`), em ordem fixa; `None` serializado
  como `null`. Nenhum campo de conteúdo fica fora do hash. Logo:
  - **mesmo `evidence_id` + payload idêntico** → redelivery idempotente (no-op);
  - **mesmo `evidence_id` + payload diferente** → **HARD ERROR**, nunca tratado como
    redelivery (indica bug de ingestão ou colisão); nada é gravado.
- A comparação de payload na chegada inclui `schema_version`: mesmo id com
  `schema_version` diferente também é hard error (migração nunca reusa id em silêncio).
- Retry após CONFLICT recomputa e gera novo registro; se o conteúdo recomputado for idêntico
  ao já gravado (mesmo id), é idempotente.
- Deal/Call/Lead/StageEvent/CallDealMatch ids inalterados.

## 12. Invariants

| # | Invariante | Onde |
|---|---|---|
| I1 | Evidence, Disposition e Assessment são frozen e append-only; nada é apagado | modelo + write path |
| I2 | `raw_state` obrigatório p/ `crm_status`; nunca texto livre; `observation_key` não vazio | modelo |
| I3 | timestamps tz-aware; `effective_at ≤ decided_at` | modelo |
| I4 | `won` exige ≥ 1 `sale` em supporting; `rejected` ≥ 1 `rejection`; `open` ≥ 1 `active`/`deferral` | write path |
| I5 | `confidence_level is None` ⟺ `status == "unknown"` | modelo |
| I6 | `no_contact`, `reversal` e `source="automation"` nunca sustentam `rejected` | write path |
| I7 | `effective_at` obrigatório ⟺ `won`/`rejected` | modelo |
| I8 | `policy_version` ⟺ `rule`; `mapping_version` ⟺ disposição `mapping` | modelo |
| I9 | uma avaliação que **se torna canônica** saindo de `won`/`rejected` exige: evidência elegível nova com `observed_at > effective_at` anterior, **ou** remoção (disposição) de evidência de suporte anterior, **ou** `decision_method="human"` | write path |
| I10 | com autoridade humana na cadeia, avaliação `rule` nunca é canônica (§8.3) | derivação |
| I11 | cadeia linear; escrita só com CAS (§10); fork → canônico indisponível | write path |
| I12 | `supporting_evidence_ids ⊆ eligible_evidence_ids`; todas do mesmo `deal_id` | write path |
| I13 | ids re-derivados e validados; mesmo id + payload diferente = hard error | modelo + write path |
| I14 | no máximo uma disposição por evidência; `remapped` exige substituta com mesma observação e `signal` diferente; `invalidated` só `human` | write path |
| I15 | `human` ⇒ `needs_human_review=false` e `confidence_level ∈ {high, None}` | modelo |
| I16 | outcome só é consumível (analytics/Outcome Intelligence) se `head.needs_human_review = false` e a cadeia é linear; senão, indisponível para consumo | leitura |

"Write path" = requer o conjunto (cadeia/evidências); fica para a camada de persistência
futura (mesma posição de TD-07/TD-09).

## 13. Outcome ≠ Objection

- `ObjectionEpisode.resolution_status` é **in-call**; o outcome canônico é do **Deal**.
- Objeção `resolved` + deal `rejected` e objeção `unresolved` + deal `won` são válidos.
- Nenhum campo de um referencia o outro; a relação é análise, não schema.

## 14. Dependencies

- **DEP-1 (existente)** — resolver autoritativo do match Call↔Deal atual. Não resolvido
  aqui. Outcome opera só sobre um Deal existente; Outcome Intelligence só junta evidência de
  Call quando o linkage Call → Deal for autoritativo.
- **DEP-2 (nova)** — consolidação de cards do CRM numa oportunidade canônica.
- **DEP-3 (nova)** — tabela estado bruto do CRM → `signal`, versionada (Gabriel), incluindo
  atribuição automação × pessoa: se o Kommo não distinguir, o estado mapeia para
  `unclassified`/`no_contact`, **nunca** `rejection`. Nova versão da tabela = disposições
  `remapped` com `decided_by="mapping"`.
- **Persistência/write path** — CAS da cadeia, unicidade de disposição por evidência (I14, sem CAS próprio: constraint de unicidade no storage), invariantes cross-object (TD-07/TD-09).

### 14.1 Deal / CRM card

- Hoje `deal_id = hash(company_id, source, external_id)`: **Deal = card**. v0 não muda `Deal`.
- Evidência de outro card entra num Deal **só** por atribuição explícita (humana ou regra
  documentada), com `source_record_ref` do card de origem.
- Cards conflitantes atribuídos ao **mesmo** Deal → conflito normal (§9.2-3).
- Cards paralelos como **Deals distintos**: cada um tem seu outcome; v0 não sabe que são a
  mesma oportunidade → DEP-2.
- Card errado: disposição `invalidated` (§7.2); nada é apagado.

## 15. Scenario matrix

Abreviações: E = eligible evidence; cand. = candidato automático; aut. = decisão autoritativa;
rev. = `needs_human_review` do head; canônico = outcome final.
Toda linha com Rev. = **sim** tem o canônico **registrado mas não utilizável** para consumo até
revisão humana (I16).

| # | Cenário | E | Cand. | Aut. | Rev. | Canônico |
|---|---|---|---|---|---|---|
| 1 | CRM OPEN only | {crm open → `unclassified`} | `unknown` (§9.2-5) | rule | não | `unknown` |
| 2 | CRM LOST por Salesbot | {`no_contact`} | `unknown` (I6) | rule | não | `unknown` |
| 3 | Rejeição comercial explícita (closer) | {`rejection` medium} | `rejected` medium | rule | não | `rejected` |
| 4 | Pagamento com CRM OPEN | {`sale` high, `unclassified`} | `won` high | rule | não | `won` |
| 5 | Pagamento atribuído errado → invalidado | antes {P}; depois {} | antes `won`; depois `unknown` (I9: suporte removido) | rule | não | `unknown` |
| 6 | Rejeição remapeada p/ no-contact | {`no_contact`} (rejeição com disposição `remapped`) | `unknown` | rule | não | `unknown` |
| 7 | Humano REJECTED → automação vê `active` posterior | {rejection, active} | `open` medium | human (REJECTED) | **sim** (§9.4-3) | `rejected` |
| 8 | Humano UNKNOWN → pagamento aparece | {…, `sale` high} | `won` high | human (UNKNOWN) | **sim** | `unknown` |
| 9 | Humano WON → reembolso | {`sale`, `reversal`} | `unknown` (§9.3-A) | human (WON) | **sim** | `won` |
| 10 | Pagamento → reembolso → humano revisa | {`sale`, `reversal`} | antes: `unknown` + rev.; depois do humano: nenhuma avaliação `rule` nova enquanto E não mudar (passo 10b) | antes rule; depois human | antes sim; depois não (head = decisão humana) | antes `unknown` (não utilizável); depois o bundle humano, utilizável (tipicamente `won` ou `unknown`; `rejected` só com evidência `rejection`, I4) |
| 11 | Duas avaliações simultâneas a partir de A | — | — | — | — | primeira `A→B`; segunda CONFLICT, recarrega B, recomputa (§10.1) |
| 12 | Stage e status do mesmo card, mesmo instante | 2 evidências distintas (`observation_key`, `raw_digest`) | conforme sinais (ambas `unclassified` → `unknown`) | rule | não | `unknown` |
| 13 | Mesma evidência reenviada idêntica | inalterado | no-op | — | — | inalterado |
| 14 | Mesmo `evidence_id`, payload diferente | inalterado | — | — | — | **hard error**; nada gravado |
| 15 | Cards paralelos discordam | Deals distintos: cada um seu E (DEP-2). Mesmo Deal (atribuição explícita): ex. {`sale` medium, `rejection` medium} | mesmo Deal: bucket da mais recente (§9.2-3) | rule | sim (conflito medium) | ex. `won` medium com revisão |
| 16 | Nenhuma evidência elegível | {} | `unknown` | rule | não | `unknown` |
| 17 | Toda evidência anterior invalidada | {} | `unknown` | rule → canônico `unknown`; se havia humano → human | rule: não; human: **sim** (§9.4-4) | rule: `unknown`; human: bundle humano mantido |
| 18 | Follow-up futuro com data | {`deferral`} | `open` | rule | não | `open` (data não armazenada, D-G7) |
| 19 | Rejected reaberto de verdade | {`rejection` medium, `active` medium posterior (closer)} | `open` medium (I9: evidência nova; §9.2-3 conflito) | rule | **sim** (conflito medium; seria não só se a evidência nova fosse `high`, ex. pagamento/humano) | `open`, **não utilizável** até revisão (I16) |
| 20 | Match Call↔Deal errado corrigido | evidência de outcome é do Deal; se alguma veio atribuída pela call errada → disposição `invalidated` (→ #5) | conforme E | — | — | outcome não muda por si; só o join de Outcome Intelligence (DEP-1) |

## 16. Evaluation (medir contra julgamento humano)

- **Amostra:** Deals com pacote de **evidências elegíveis**; dois operadores rotulam **cegos**
  à saída da regra.
- **O anotador vê:** por evidência, `source`, `raw_state`, `observed_at` e o registro de
  origem via `source_record_ref` — **não** o `signal` mapeado.
- **O anotador rotula:** (a) `signal` de cada evidência (avalia DEP-3); (b) `status` do Deal
  e se precisaria de revisão (ponta a ponta). A regra também roda sobre os **sinais do
  anotador** (policy-only).
- **Métricas:** uma matriz 4×4 **por anotador** (regra × A, regra × B), nunca coluna
  "humano" colapsada; kappa humano × humano (N/A quando indefinido); taxa crítica
  **no-contact/automação/reversal classificado como `rejected`** (deve ser 0 por I6);
  precisão/recall de `needs_human_review` contra "humanos discordam da regra ou entre si".
- **Auditoria:** toda avaliação cita `supporting_evidence_ids`, `eligible_evidence_ids` e
  `policy_version` → reproduzível.
- Sem thresholds agora.

## 17. Rejected alternatives

| Alternativa | Por que não |
|---|---|
| Estender `Deal.outcome` | mistura source state e canônico; quebra o contrato atual |
| Só estado atual, sem histórico | não audita reabertura, reembolso, override |
| Precedência fixa por fonte | qualquer fonte erra; conflito → review |
| "Mais recente por timestamp" como atual | falha do DEP-1; cadeia linear + CAS |
| Branching/multi-parent history | complexidade sem necessidade em v0; fork → indisponível |
| Apagar/mutar evidência para corrigir | destrói auditoria (§7.2) |
| Policy sobre toda evidência já observada | reconsumiria evidência inválida (P0-1) |
| Autoridade = "head é humano" | some após uma avaliação `rule` (P0-2) |
| Override trocando só `status` | registros impossíveis, ex. `unknown` + `high` (P0-3) |
| `reversal` → `rejected` | reembolso ≠ decisão de não comprar |
| `FUTURE`, `STALE`, `lost` como status | §4 |
| `rejection_type`, float de confiança | §4.2, §8 |
| Campo `authority` armazenado | derivável da cadeia |

## 18. Deferred

`rejection_type`; data de retomada; `stale_candidate`; estado `cancelled`/`refunded`/
`churned`; devolução de autoridade humana à regra; reinstauração direta de evidência
disposta; reconciliação multi-parent; consolidação de cards (DEP-2); valor/receita
realizada; `reviewed_by`; ligação Outcome ↔ Call (DEP-1).

## 19. Open decisions

| # | Decisão | Recomendação | Dono |
|---|---|---|---|
| D-M1 | `Deal.outcome`/`closed_at` documentados como projeção do estado do CRM (sem mudar código) | aprovar; docs atualizados só na implementação | Matheus |
| D-M2 | Três entidades append-only: `OutcomeEvidence`, `EvidenceDisposition`, `OutcomeAssessment` | aprovar | Matheus |
| D-M3 | FUTURE = `open` + `deferral` | aprovar | Matheus (+ D-G4) |
| D-M4 | DEP-2 fora desta task | aprovar | Matheus |
| D-M5 | Implementar após D-G1/D-G2 | sim | Matheus |
| D-M6 | ADR como primeiro passo da implementação | sim | Matheus |
| D-M7 | Autoridade humana persiste sem mecanismo de devolução à regra em v0 | aprovar | Matheus |
| D-M8 | Histórico linear com CAS; fork → indisponível + reparo manual | aprovar | Matheus |
| D-G1 | Tabela estado bruto do Kommo → `signal` (incl. automação × pessoa) | — | Gabriel |
| D-G2 | CRM "perdido" manual é confiável como `rejection`? | `low` até confirmar | Gabriel |
| D-G3 | Ghosting conta como perda em analytics (rótulo derivado)? | canônico segue `unknown` | Gabriel |
| D-G4 | "PROPOSTA FUTURA" é viva ou perda? | `open` + `deferral` | Gabriel |
| D-G5 | Reembolso/cancelamento: que estado comercial é? Janela? | v0: `unknown` + revisão; estado próprio deferred | Gabriel |
| D-G6 | "VENDA GANHA" sozinho basta para `won`? | sim, `medium` | Gabriel |
| D-G7 | Data de retomada no v0? | não | Gabriel |
| D-G8 | Regra de `stale_candidate` | não definir agora | Gabriel |

## 20. Definition of Done (desta proposta)

- [x] Auditoria de `Deal.outcome`, `closed_at`, `StageEvent`, matching, premissas de CRM.
- [x] Semântica won/rejected/open/unknown; FUTURE e STALE decididos.
- [x] Raw observation / evidence / eligible / supporting / candidate / authoritative separados.
- [x] Elegibilidade por disposição (P0-1); autoridade humana persistente (P0-2); decisão
      inteira (P0-3); reversal como modificador (P0-4); identidade da observação (P0-5);
      cadeia linear com CAS (P1).
- [x] Máquina de estados explícita; matriz de 20 cenários.
- [x] Review State & Audit / Concurrency & Invariants / Domain (rev. 2): APPROVE (após correções em §8.3, §9.4, §10.1, §11, §15, I16).
- [ ] D-M*, D-G* decididos.
- [ ] (Próxima task) ADR + implementação.
