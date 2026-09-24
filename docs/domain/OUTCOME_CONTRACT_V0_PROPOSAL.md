# Outcome Contract v0 — Proposal

Status: **PROPOSAL — não implementado.** Nenhum código muda com este documento. Contrato
vigente continua sendo `Deal.outcome` (`src/closer_ai/domain/deal.py`,
`docs/domain/DEAL_MODEL.md`).

Pergunta:

> Qual é o menor contrato de Outcome capaz de representar o estado comercial de uma
> oportunidade sem confundir CRM raw state com verdade canônica?

Resposta curta: **duas entidades append-only novas**, sem alterar `Deal`, `StageEvent` ou
matching:

- `OutcomeEvidence` — uma observação de uma fonte (CRM, closer, pagamento, automação,
  humano), com o **estado bruto preservado** e um **sinal** interpretado.
- `OutcomeAssessment` — a **interpretação canônica** do outcome de um Deal num momento,
  citando as evidências, com confiança, flag de revisão e cadeia de supersessão.

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
| Retorno só em planilha do closer | fonte `closer_report` de primeira classe (§5) |
| Cards paralelos | evidência referencia o registro de origem; consolidação é DEP-2 (§10) |
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

| Evidência | Sinal | Força (policy, §6) |
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

## 6. Evidence contract — `OutcomeEvidence`

| Field | Purpose | Observable? | Derived? | Required? | MVP? | Why |
|---|---|---|---|---|---|---|
| `schema_version` | versionar | — | — | default | sim | padrão do repo |
| `evidence_id` | identidade/idempotência | — | sim (hash) | sim | sim | redelivery colapsa (§11) |
| `deal_id` | a qual Deal a evidência foi atribuída | atribuição é julgamento | — | sim | sim | outcome pertence ao Deal |
| `source` | tipo de fonte | sim | — | sim | sim | policy de força depende da fonte |
| `source_record_ref` | id opaco do registro na fonte (card, pagamento, linha de planilha) | sim | — | sim | sim | auditoria; cards paralelos; nunca PII |
| `raw_state` | estado bruto verbatim da fonte estruturada | sim | — | obrigatório p/ `crm_status`; `None` p/ texto livre | sim | preservar CRM raw |
| `signal` | o que esta evidência afirma | não | mapeamento/julgamento | sim | sim | separa raw de interpretação |
| `observed_at` | quando o fato ocorreu na fonte (tz-aware) | sim | — | sim | sim | temporalidade, reabertura |
| `confidence_level` | — | — | — | — | **não** | força vem da policy (source × signal), não de cada linha |
| `needs_human_review` | — | — | — | — | **não** | revisão é propriedade da decisão, não da observação |
| texto/quote | — | — | — | — | **não** | PII |
| data de retomada | — | — | — | — | **não** | D-G7 |

`source` (8 valores, fechado):

| Valor | Cobre |
|---|---|
| `crm_status` | stage/status estruturado do CRM, de qualquer card (inclusive paralelo) |
| `crm_note` | nota/texto livre do CRM |
| `closer_report` | retorno do closer (planilha, mensagem, relatório) |
| `payment` | pagamento confirmado, reembolso, estorno |
| `post_sale` | pós-venda, membership, onboarding, cancelamento de membership |
| `automation` | Salesbot e qualquer ação automática |
| `human` | decisão/confirmação de um operador |
| `other` | válvula de escape |

`parallel_card` não é fonte: é `crm_status`/`crm_note` com `source_record_ref` de outro card.
`membership` está em `post_sale`. `salesbot` está em `automation`.

`signal` (7 valores, fechado):

| Valor | Afirma |
|---|---|
| `sale` | a venda aconteceu |
| `rejection` | o lead decidiu não comprar |
| `active` | negociação viva agora |
| `deferral` | adiamento combinado |
| `no_contact` | sem resposta / encerrado por falta de contato |
| `reversal` | venda desfeita (reembolso, estorno, cancelamento) |
| `unclassified` | estado observado sem significado canônico (ex. CRM "open", stage intermediário) |

Mapeamento `raw_state` do CRM → `signal` é uma **tabela versionada**, de Gabriel (D-G1);
estados não mapeados → `unclassified`.

### 6.1 Força da evidência (policy, não campo)

| source \ signal | sale | rejection | active / deferral | no_contact | reversal |
|---|---|---|---|---|---|
| `human` | high | high | high | high | high |
| `payment` / `post_sale` | high | — | — | — | high |
| `closer_report` | medium | medium | medium | medium | medium |
| `crm_status` (estado mapeado) | medium | low (D-G2) | low | medium | medium |
| `crm_note` | low | low | low | low | low |
| `automation` | — | **proibido** (I6) | — | medium | — |
| `other` | low | low | low | low | low |

"—" = combinação não esperada; se ocorrer, força `low`. A tabela é versionada junto com a
policy (`policy_version`). CRM "perdido" como `rejection` é `low` até Gabriel confirmar que
fechamentos manuais de closer são confiáveis (D-G2).

## 7. Canonical decision — `OutcomeAssessment`

| Field | Purpose | Observable? | Derived? | Required? | MVP? | Why |
|---|---|---|---|---|---|---|
| `schema_version` | versionar | — | — | default | sim | padrão |
| `assessment_id` | identidade | — | sim (hash) | sim | sim | §11 |
| `deal_id` | Deal avaliado | — | — | sim | sim | — |
| `status` | outcome canônico | não | policy/humano | sim, **sem default** | sim | a resposta |
| `evidence_ids` | evidências que sustentam | — | — | sim; ≥ 1 exceto `unknown` | sim | "qual evidência sustenta?" |
| `confidence_level` | `high`/`medium`/`low` | não | policy | sim; `None` ⟺ `unknown` | sim | categórico, sem float (padrão de `CallDealMatch`) |
| `needs_human_review` | decisão precisa de humano | não | policy | sim, **sem default** | sim | conflito/reversão |
| `decision_method` | `rule` / `human` | sim | — | sim | sim | auditoria; human override |
| `policy_version` | versão da policy + tabela de mapeamento | sim | — | ⟺ `rule` | sim | reproduzir e medir a regra |
| `effective_at` | quando o outcome passou a valer no mundo | via evidência | julgamento | ⟺ `won`/`rejected` | sim | alinhar calls antes/depois do outcome |
| `decided_at` | quando a decisão foi registrada | sim | — | sim | sim | auditoria; id |
| `supersedes_assessment_id` | avaliação anterior substituída | — | — | `None` só na primeira | sim | currentness autoritativa (§8) |
| `rejection_type` | — | — | — | — | **não** | §4.2 |
| `closed_at` | — | — | — | — | **não** | substituído por `effective_at`; `Deal.closed_at` segue como estado da fonte |
| score float | — | — | — | — | **não** | sem semântica |
| `reviewed_by` | — | — | — | — | **não** | não há conceito de usuário no repo (mesma razão de `DEAL_MODEL.md`) |

Pseudocódigo (**não implementado**):

```python
OutcomeStatus = Literal["won", "rejected", "open", "unknown"]
EvidenceSource = Literal["crm_status", "crm_note", "closer_report", "payment",
                         "post_sale", "automation", "human", "other"]
EvidenceSignal = Literal["sale", "rejection", "active", "deferral",
                         "no_contact", "reversal", "unclassified"]

class OutcomeEvidence(BaseModel):          # frozen
    schema_version: str = "1.0.0"
    evidence_id: str
    deal_id: str
    source: EvidenceSource
    source_record_ref: str
    raw_state: str | None
    signal: EvidenceSignal
    observed_at: datetime                   # tz-aware

class OutcomeAssessment(BaseModel):        # frozen
    schema_version: str = "1.0.0"
    assessment_id: str
    deal_id: str
    status: OutcomeStatus                   # sem default
    evidence_ids: tuple[str, ...]
    confidence_level: Literal["high", "medium", "low"] | None
    needs_human_review: bool                # sem default
    decision_method: Literal["rule", "human"]
    policy_version: str | None
    effective_at: datetime | None
    decided_at: datetime
    supersedes_assessment_id: str | None
```

### 7.1 Confidence semantics

`confidence_level` é definido **exclusivamente** pelo algoritmo de §9 (fonte única de
verdade): força (§6.1) da evidência de suporte mais forte do status escolhido. Evidência
contrária **não rebaixa** a confiança; ela é tratada por §9 (regras 5–7: conflito ≥ medium →
review; só `low` contraditória → `unknown`). `human` → `high`. `unknown` → `None` (não existe
"confiança em não saber").
Sem float: mesma razão de `CallDealMatch` — um número sem tabela de calibração não é auditável.

### 7.2 Review semantics

`needs_human_review` pertence à **avaliação**, não à evidência: é a decisão que está em
dúvida. É `true` quando:

1. evidências de força ≥ medium apontam para status diferentes (§9);
2. existe `reversal` após `sale` (reembolso/cancelamento);
3. uma avaliação `rule` encontraria status diferente de uma avaliação `human` vigente (§8);
4. a cadeia de supersessão tem bifurcação (§8).

Flag não bloqueia o status; bloqueia o **uso** em Outcome Intelligence se o consumidor exigir
(`needs_human_review=false`) — recomendação: exigir.

## 8. Temporal model

Opção escolhida: **C — histórico append-only + atual derivado**, como `StageEvent` +
`Deal.current_stage`, mas com **currentness autoritativa** (lição do DEP-1):

- Toda mudança de interpretação é uma **nova** `OutcomeAssessment` com
  `supersedes_assessment_id` = a avaliação vigente. Nada é atualizado in-place.
- **Avaliação atual** de um Deal = a **única** avaliação não supersedida.
  - 0 avaliações → sem outcome canônico (tratado como `unknown`, sem avaliação).
  - ≥ 2 não supersedidas (bifurcação, escritas concorrentes) → **outcome atual
    indisponível** + revisão. **Nunca** "a mais recente por `decided_at`".
- Transições permitidas (nenhum status é absorvente):

```
unknown ⇄ open
open → won | rejected
rejected → open → won          (reabertura, exige evidência nova — I9)
won → (won + needs_review)     (reversal; mudar status exige humano — D-G5)
```

`won`/`rejected` são **fechados**, não **terminais absorventes**: reabertura real acontece
(rejeitou e voltou). Sair deles exige evidência nova observada após `effective_at` ou decisão
`human` (I9).

## 9. Conflict handling (adjudication policy)

**Nenhuma fonte vence sempre.** Policy v0 (aplicada por `rule`):

1. Considerar só evidências do Deal com sinal ≠ `unclassified`.
2. Se existe evidência com `source="human"`: vale a de **`observed_at` mais recente** entre
   elas (status implicado por seu sinal, confiança `high`, `needs_human_review=false`).
   Duas ou mais `human` com o mesmo `observed_at` mais recente e sinais diferentes →
   `unknown`, `needs_human_review=true`. Se o sinal vencedor for `no_contact` → `unknown`
   (I6); se for `reversal` → regra 6. *Isto trata **evidência** de fonte humana (um operador
   registrou uma observação). Uma **avaliação** `decision_method="human"` não passa por esta
   policy — é escrita diretamente pelo humano e protegida por I10.*
3. Senão, agrupar por status implicado (`sale`→won, `rejection`→rejected, `active`/`deferral`
   →open; `no_contact` não implica status; `reversal` ver 6).
4. Se só um status tem evidência ≥ medium → esse status, com a confiança da mais forte.
5. Se ≥ 2 status têm evidência ≥ medium (conflito):
   - `observed_at` iguais ou ordem indeterminável → `unknown`, `needs_human_review=true`,
     citando ambas;
   - senão, status da evidência ≥ medium **mais recente**, citando ambas, com
     `needs_human_review=true` — **exceto** se essa mais recente for `high` (pagamento,
     pós-venda, humano), caso em que `needs_human_review=false`.
     Ex.: closer "rejeitou" 10/03 e pagamento 12/03 → `won` high, sem review; closer
     "rejeitou" 10/03 e CRM "VENDA GANHA" 12/03 → `won` medium **com** review.
6. *(override, ver ordem abaixo)* Se existe evidência `reversal` com `observed_at` posterior
   a alguma evidência `sale` citada e o status candidato é `won`: mantém `won`,
   `needs_human_review=true` (D-G5 decide se reembolso desfaz a venda). `reversal` sem
   `sale` anterior não implica status; entra só como citação e força
   `needs_human_review=true`.
7. Só evidência `low` → status implicado com `low`; se `low` contraditórias → `unknown`.
8. Avaliação `rule` nunca supersede uma `human` com status diferente: gera avaliação com o
   **mesmo** status humano e `needs_human_review=true`.
9. **Terminal:** se nenhum status tem evidência após os passos anteriores (ex.: só
   `unclassified`, só `no_contact`/automação, ou nenhuma evidência) → `unknown`,
   `confidence_level=None`, `needs_human_review=false`.

**Ordem de avaliação (determinística):**

1. **Status candidato** — passos **2, 4, 5, 7, 9**, nessa ordem; o primeiro que se aplica
   define status, confiança e flag de revisão candidatos (passos 1 e 3 são preparação).
2. **Overrides, sempre aplicados depois**, nessa ordem, sobre o candidato:
   - passo **6** (reversal) — pode só **ligar** `needs_human_review`;
   - passo **8** (avaliação `human` vigente com status diferente) — restaura o status humano
     e liga `needs_human_review`.

Overrides nunca desligam um `needs_human_review` já ligado. Se o passo 8 restaurar `won`, o
passo 6 é reavaliado contra esse status final.

| Conflito | Resultado v0 |
|---|---|
| pagamento vs CRM open | `won` high (CRM open é `unclassified`) |
| closer "rejeitou" vs Salesbot/CRM open | `rejected` medium (automação/CRM open não afirmam nada comercial) |
| CRM won vs reembolso/cancelamento | `won` + review |
| humano vs automação | humano |
| CRM LOST vs closer "ainda negociando" (mais recente) | `open` medium (CRM lost é low) |
| card A "VENDA GANHA" vs card B aberto | se ambos atribuídos ao mesmo Deal: `won` medium; se Deals diferentes: cada um avaliado — DEP-2 |

## 10. Deal / CRM card relationship

Hoje `deal_id = hash(company_id, source, external_id)`: **Deal = card**. A auditoria mostra
que card ≠ oportunidade.

- **v0 não muda `Deal`.** Outcome pertence ao `deal_id` (card) existente.
- Evidência de outro card entra num Deal **só** por atribuição explícita (humana ou regra
  documentada), com `source_record_ref` do card de origem — rastreável.
- Cards paralelos com status conflitantes no **mesmo** Deal → §9.
- Cards paralelos como **Deals distintos** da mesma pessoa/oportunidade: v0 não sabe que são
  a mesma oportunidade; cada um tem seu outcome. Consolidar cards numa oportunidade canônica
  é uma decisão arquitetural maior → **DEP-2** (fora desta task).
- Card errado (evidência atribuída ao Deal errado): evidência é imutável; a correção é uma
  nova avaliação que **não cita** a evidência errada (e, quando existir storage, a atribuição
  errada é registrada como erro, nunca apagada).

## 11. IDs

Mesma técnica de `normalization/ids.py`/`domain/deal.py` (sha256 sobre `json.dumps(...,
ensure_ascii=True, separators=(",", ":"))`, 24 hex, timestamps via `_canonical_timestamp`):

```
evidence_id   = "oev_" + h(["outcome_evidence", deal_id, source, source_record_ref, signal, ts(observed_at)])
assessment_id = "oas_" + h(["outcome_assessment", deal_id, status, sorted(evidence_ids),
                            decision_method, supersedes_assessment_id, ts(decided_at)])
```

- Redelivery idêntica colapsa; nova observação (outro `observed_at`) é nova evidência.
- `signal` no id: re-mapear o mesmo estado bruto com uma tabela nova gera **nova** evidência
  (a antiga fica, citada pelas avaliações antigas com seu `policy_version`). Aceito: mantém
  imutabilidade.
- Sem PII no hash (`source_record_ref` é id opaco).
- Deal/Call/Lead/StageEvent/CallDealMatch ids inalterados.

## 12. Invariants

| # | Invariante | Onde | Por quê |
|---|---|---|---|
| I1 | Evidence e Assessment são frozen e append-only | modelo + write path | auditabilidade |
| I2 | `raw_state` obrigatório para `source="crm_status"`; nunca texto livre | modelo | preservar CRM raw sem PII |
| I3 | timestamps tz-aware; `effective_at ≤ decided_at` | modelo | mesmo padrão de `Deal` |
| I4 | `won` exige ≥ 1 `sale`; `rejected` ≥ 1 `rejection`; `open` ≥ 1 `active`/`deferral`; entre `evidence_ids` | cross-object (write path) | status sustentado por evidência |
| I5 | `confidence_level is None` ⟺ `status == "unknown"` | modelo | sem confiança em "não sei" |
| I6 | `no_contact` e `source="automation"` nunca sustentam `rejected` | cross-object | ponto central da auditoria |
| I7 | `effective_at` obrigatório ⟺ `won`/`rejected` | modelo | espelha `Deal.closed_at`; `unknown` não tem data de fechamento |
| I8 | `policy_version` obrigatório ⟺ `decision_method == "rule"` | modelo | reprodutibilidade |
| I9 | sair de `won`/`rejected` exige evidência nova (`observed_at > effective_at`) ou `decision_method == "human"` | cross-object | reabertura real, não oscilação |
| I10 | avaliação `rule` não muda o status de uma `human` vigente | cross-object | human override |
| I11 | currentness = única não supersedida; bifurcação → indisponível | cross-object | lição DEP-1 |
| I12 | todas as `evidence_ids` pertencem ao mesmo `deal_id` | cross-object | integridade |
| I13 | ids re-derivados e validados | modelo | padrão do repo |

Checagens "cross-object" exigem o conjunto de evidências/avaliações: ficam no write path
futuro (mesma posição de TD-07/TD-09), não no modelo isolado.

## 13. Outcome ≠ Objection

- `ObjectionEpisode.resolution_status` é **in-call**; `OutcomeAssessment.status` é do **Deal**.
- Objeção `resolved` + deal `rejected` e objeção `unresolved` + deal `won` são ambos válidos.
- Nenhum campo de um referencia o outro. A relação é **análise** (Outcome Intelligence), não
  schema. Nenhuma alteração no proposal de `ObjectionEpisode`.

## 14. Dependencies

- **DEP-1 (existente)** — resolver autoritativo do match Call↔Deal atual. Outcome **não**
  resolve DEP-1. Outcome Intelligence só usa evidência de Call quando o linkage Call → Deal
  for autoritativo; até lá, outcomes existem por Deal, mas não se juntam a calls.
- **DEP-2 (nova)** — consolidação de cards/registros do CRM numa oportunidade canônica
  (card ≠ oportunidade). Decisão arquitetural; fora desta task.
- **DEP-3 (nova)** — tabela de mapeamento de estados brutos do CRM → `signal`, versionada,
  definida por Gabriel. **Inclui atribuição de autoria:** I6 depende de saber se um
  fechamento no CRM foi feito por automação ou por uma pessoa. Se o Kommo não distinguir isso
  de forma confiável (fechamento do Salesbot e manual podem parecer iguais), esse estado
  bruto mapeia para `unclassified`/`no_contact`, **nunca** `rejection` — a atribuição de fonte
  pode ser tão pouco confiável quanto o motivo de perda que ela substitui.
- Storage/write path (TD-07/TD-09) — invariantes cross-object e unicidade.

## 15. Edge cases

| Caso | Tratamento |
|---|---|
| Explicit rejection ("não vou comprar") | `rejection` (closer/humano) → `rejected` |
| No-contact | `no_contact` → `unknown`, nunca `rejected` |
| Salesbot closure | `automation`/`no_contact`; CRM "perdido" gerado pelo bot também é `no_contact` via mapeamento → `unknown` |
| CRM WON + pagamento | `won` high |
| CRM OPEN + pagamento | `won` high (CRM open é `unclassified`) |
| CRM LOST + closer "ainda negociando" | `open` medium (CRM "perdido" é `low` até D-G2; só o closer é ≥ medium → §9 regra 4). Se D-G2 subir CRM "perdido" para medium → conflito → §9 regra 5 |
| Cards duplicados conflitantes | mesmo Deal → §9; Deals distintos → DEP-2 |
| Follow-up com data futura | `deferral` → `open`; data não armazenada (D-G7) |
| "Volta no próximo trimestre" | `deferral` → `open` (salvo D-G4) |
| Reembolso após venda | `reversal` → `won` + review (D-G5) |
| Cancelamento após pagamento | idem |
| Card errado | nova avaliação sem a evidência errada (§10) |
| Unknown | status legítimo, `confidence_level=None` |
| Evidência insuficiente | só `low` contraditória ou `unclassified` → `unknown` |
| Human override | `decision_method="human"`; `rule` não reverte (I10) |
| Reabertura após rejeição | nova evidência `active`/`sale` posterior → `open`/`won` supersedendo (I9) |
| Deal sem nenhuma evidência | sem avaliação; consumidores tratam como `unknown` |

## 16. Evaluation (medir contra julgamento humano)

- **Amostra:** Deals com pacote de evidências; dois operadores rotulam **cegos** à saída da
  regra, a partir do mesmo pacote.
- **O que o anotador vê:** por evidência, `source`, `raw_state`, `observed_at` e acesso ao
  registro de origem via `source_record_ref` — **não** o `signal` mapeado.
- **O que o anotador rotula:** (a) o `signal` de cada evidência — avalia o mapeamento
  (DEP-3/D-G1); (b) o `status` do Deal e se precisaria de revisão — avalia o resultado ponta a
  ponta. Para isolar a policy de §9, a regra também é executada sobre os **sinais do
  anotador** (policy-only).
- **Métricas:** **uma matriz 4×4 por anotador** (regra × anotador A, regra × anotador B),
  nunca uma coluna "humano" colapsada; concordância humano × humano separada (kappa; N/A
  quando indefinido); taxa crítica **no-contact classificado como `rejected`** (deve ser 0 por I6 —
  é a métrica que pega um mapeamento DEP-3 que atribua fechamento de automação a pessoa); precisão/recall de `needs_human_review` contra "humanos discordam
  da regra ou entre si".
- **Auditoria:** toda avaliação cita evidências + `policy_version` → qualquer rótulo é
  reproduzível.
- Sem thresholds agora; definidos após o piloto (mesma postura do D3 de AC-47).

## 17. Rejected alternatives

| Alternativa | Por que não |
|---|---|
| Estender `Deal.outcome` (novos valores/campos) | mistura source state e canônico no mesmo campo; exige re-emitir snapshot; quebra o contrato atual |
| Só estado atual, sem histórico | não audita reabertura, reembolso, override |
| Precedência fixa por fonte | a auditoria mostra que qualquer fonte erra; conflito → review |
| "Mais recente por timestamp" como atual | mesma falha do DEP-1; substituído por supersessão |
| `FUTURE` como status | sub-estado de `open`; regras de transição sem ganho |
| `STALE` / `stale_candidate` como status | silêncio ≠ abandono; regra não validada |
| `rejection_type` | motivo não confiável; duplica objeções |
| `confidence_score` float | sem calibração |
| confiança/revisão por evidência | força é policy; revisão é da decisão |
| `crm_stage_raw` + `crm_status_raw` como campos no Deal | exigiria mudar Deal; `raw_state` por evidência cobre os dois |
| Status `lost` | ambíguo com CRM; `rejected` é explícito |

## 18. Deferred

`rejection_type`; data de retomada; `stale_candidate` derivado; consolidação de cards (DEP-2);
valor/receita realizada e parcial; `reviewed_by`; política de janela de reembolso; ligação
Outcome ↔ Call (DEP-1).

## 19. Open decisions

| # | Decisão | Recomendação | Dono |
|---|---|---|---|
| D-M1 | `Deal.outcome`/`closed_at` passam a ser documentados como projeção do estado do CRM (sem mudar código) | aprovar; docstring de `deal.py` e `DEAL_MODEL.md` atualizados só na implementação | Matheus |
| D-M2 | Duas entidades novas (`OutcomeEvidence`, `OutcomeAssessment`) com supersessão | aprovar | Matheus |
| D-M3 | FUTURE = `open` + `deferral` | aprovar | Matheus (+ Gabriel via D-G4) |
| D-M4 | DEP-2 (card ≠ oportunidade) fora desta task, com task própria | aprovar | Matheus |
| D-M5 | Implementar após D-G1/D-G2 | sim | Matheus |
| D-M6 | ADR (contrato entre módulos) como primeiro passo da implementação | sim | Matheus |
| D-G1 | Tabela estado bruto do Kommo → `signal` (quais estados = venda, rejeição, adiamento, automação) | — | Gabriel |
| D-G2 | CRM "perdido" fechado manualmente pelo closer é confiável como `rejection`? | manter `low` até confirmar | Gabriel |
| D-G3 | Ghosting/no-contact deve contar como perda em analytics (rótulo derivado)? | status canônico continua `unknown` | Gabriel |
| D-G4 | "PROPOSTA FUTURA" é oportunidade viva ou perda? | `open` + `deferral` | Gabriel |
| D-G5 | Reembolso/cancelamento desfaz a venda? Em qual janela? | review manual até definir | Gabriel |
| D-G6 | CRM "VENDA GANHA" sozinho basta para `won`? | sim, `medium` | Gabriel |
| D-G7 | Precisa de data de retomada no v0? | não | Gabriel |
| D-G8 | Regra de `stale_candidate` (dias sem evidência) | não definir agora | Gabriel |

## 20. Definition of Done (desta proposta)

- [x] Auditoria de `Deal.outcome`, `closed_at`, `StageEvent`, matching, premissas de CRM.
- [x] Semântica de won/rejected/open/unknown; FUTURE e STALE decididos.
- [x] Raw vs sinal vs canônico separados.
- [x] Evidence contract, confiança, revisão.
- [x] Modelo temporal com currentness autoritativa.
- [x] Policy de conflito sem precedência cega.
- [x] Deal vs card; DEP-1/DEP-2/DEP-3.
- [x] Invariantes, edge cases, avaliação.
- [x] Review Domain / Architecture / Evaluator: APPROVE (Domain e Evaluator após correções em §7.1, §9, §14, §16).
- [ ] D-M*, D-G* decididos.
- [ ] (Próxima task) ADR + implementação.
