# Deal Identity Resolution (DEP-2) — Proposal

Status: **PROPOSAL — contrato estrutural implementado** (`src/closer_ai/domain/deal_identity.py`).
Política de fundação de Deals e integração com o matcher dependem de decisões de Matheus e Gabriel
listadas no fim.

Pergunta:

> Qual é a menor fundação que distingue **registro do CRM (card)** de **Deal canônico**, e
> lida com duplicatas/cards paralelos sem consolidar incorretamente?

## 1. Problem

Um card do CRM não é necessariamente um Deal. Pode existir: 1 Deal em 1 card; 1 Deal em vários
cards (reabertura, card paralelo, duplicata); 2 cards parecidos que são 2 Deals; card criado por
automação; card errado; informação insuficiente. O sistema precisa **preservar essa incerteza**,
e Outcome e Call matching precisam apontar para o **Deal**, não para um card arbitrário.

## 2. Current model (código é a fonte da verdade)

| # | Pergunta | Resposta |
|---|---|---|
| 1 | O que é Deal hoje? | snapshot de **um registro do CRM**: `source`, `external_id`, `pipeline_id`, `current_stage`, `outcome`, `closed_at` (`deal.py`) |
| 2 | Como `deal_id` é gerado? | `deal_ + hash(company_id, source, external_id)`, validado no modelo |
| 3–4 | external_id / provider? | sim: `external_id` (id do card) e `source` (provedor) |
| 5 | Representação explícita de card? | **não** — o próprio Deal é o card |
| 6 | Campos provider-specific? | genéricos no nome, mas semanticamente do card: `pipeline_id`, `current_stage`, `outcome` (projeção legada, D-M1), `closed_at` |
| 7 | `MatchEvidence` referencia? | sinais (`external_id_exact`, …), não registros |
| 8 | `ExactExternalIdMatcher` assume 1 card = 1 Deal? | **sim**: `call.source_id == deal.external_id` |
| 9 | Código que duplica Deal por card? | nenhum adapter de CRM existe; mas o único construtor possível de Deal exige um `external_id` → **qualquer ingestão futura cria 1 Deal por card** |
| 10 | Vários source records por Deal? | **não** |
| 11 | Outcome assume Deal resolvido? | sim: tudo é por `deal_id`; `OutcomeEvidence.source_record_ref` pode apontar para qualquer registro |
| 12 | O que quebra se mudar Deal? | `derive_deal_id`/validator, `Deal`, `ExactExternalIdMatcher`, testes de Deal/matching; `deal_id` usado em `MatchDecision`, `OutcomeAssessment`, `commercial_state` |

| Classe | Itens |
|---|---|
| **KEEP** | Deal como unidade comercial; `deal_id` opaco para matching/outcome; Outcome por Deal; resolver DEP-1 (Call → Deal) |
| **LIMITATION** | Deal = card (identidade derivada do id do card); matcher 1 card = 1 Deal; nenhum lugar para "este card pertence a este Deal" |
| **MUST EVOLVE** | relação explícita **source record → Deal canônico**, com incerteza e autoridade humana |
| **DEFER** | fusão de Deals já criados, sinais automáticos de identidade, adapter real |
| **DO NOT TOUCH** | `resolve_current_match`, `MatchDecision`, Outcome Domain, ids de Call/Lead |

**Consequência central:** com o modelo atual, "ligar o card B ao Deal X" só é possível **fundindo
dois Deals** (o card B já teria virado o Deal Y). Fusão move Outcome e matches de Y para X — é o
problema de MDM que queremos evitar. Por isso a decisão arquitetural (§7) precisa vir antes do
código.

## 3. Source record vs Canonical Deal

- **Source record:** um registro operacional num sistema (card do Kommo, oportunidade de outro
  CRM). Identidade estrutural: `(company_id, provider, external_record_id)` — as mesmas entradas de
  `derive_deal_id`, em namespace próprio (`srk_`). `record_type` foi descartado: nenhum campo atual o
  define e ele criaria chaves distintas que fundariam o mesmo `deal_id`.
  Carrega estado operacional (stage/status do card); nunca é o Deal.
- **Canonical Deal:** a negociação comercial. Dono único do Outcome e alvo do Call matching.
- A relação entre os dois é uma **decisão de identidade**, não uma derivação automática.

## 4. Designs comparados

| Opção | Veredito |
|---|---|
| A. 1 card = 1 Deal (atual) | rejeitada como modelo final: duplica Outcome por card, não representa reabertura/paralelo |
| B. `Deal.source_record_ids: list` | rejeitada: segunda fonte de verdade mutável num snapshot frozen (mesmo motivo de "sem `call_ids`" em `DEAL_MODEL.md`); sem incerteza nem autoridade |
| C. entidade `SourceRecord` separada | útil só se o card precisar de atributos próprios; em v0 o estado do card já entra como `OutcomeEvidence`/`StageEvent` → **não necessária agora** |
| D. decisão de identidade record → Deal (cadeia linear, autoridade humana) | **recomendada**: representa ligado / não resolvido / ambíguo, é auditável, provider-agnostic, reusa o padrão de `MatchDecision` e `_chain.linear_chain` |
| E. C + D | só se C se provar necessária |

**Recomendação: D sozinha.** Uma entidade append-only, `DealIdentityDecision` (nome a confirmar),
por source record:

| Campo | Significado |
|---|---|
| `identity_decision_id` | hash de todo o conteúdo (padrão do repo) |
| `company_id`, `provider`, `external_record_id` | chave do source record (sem PII) |
| `status` | `linked` \| `unresolved` \| `ambiguous` \| `not_a_deal` |
| `deal_id` | ⟺ `linked` |
| `candidate_deal_ids` | ≥ 2 ⟺ `ambiguous` |
| `decided_by` | `automatic` \| `manual` |
| `supersedes_decision_id` | head esperado (CAS) |
| `created_at` | só para o id; nunca ordena |

`not_a_deal` cobre card de automação/card errado que não representa negociação (a regra de
**quando** usar é de negócio; o estado só precisa existir). É **só manual** em v0.

**Fundação (self-link):** o card que funda um Deal se liga a ele com `deal_id ==
derive_deal_id(company_id, provider, external_record_id)`. Isso é identidade estrutural do próprio
registro (sinal STRONG "mesmo registro"), e é o **único** `linked` que uma decisão `automatic` pode
gravar. **Quando** a ingestão deve fundar um Deal é política (§7). Resolver:
`resolve_deal_for_source_record(key, decisions)` → estado atual (`linked`/`unresolved`/
`ambiguous`/`not_a_deal`/`no_decision`/`conflict`), mesma semântica de currentness e autoridade do
DEP-1.

## 5. Identity signals

| Sinal | Classe v0 | Por quê |
|---|---|---|
| decisão humana explícita | **STRONG** | única fonte de identidade autoritativa hoje |
| referência explícita de reabertura/pai no CRM | **OPEN** (Gabriel) | se o Kommo registra "continuação de card X", seria STRONG; não confirmado |
| mesmo `(provider, external_record_id)` | **STRONG** (identidade do próprio registro) | reingestão do mesmo card; não liga dois cards |
| id de oportunidade compartilhado entre sistemas | **UNAVAILABLE** | nenhum campo existe |
| mesmo `lead_id` | **SUPPORTING** | um lead pode ter várias negociações; nunca suficiente |
| mesmo closer (`owner_id`), mesmo pipeline, proximidade temporal | **WEAK** | comuns entre negociações distintas |
| nome do lead/cliente, similaridade textual | **WEAK** | nunca suficiente (proibido como regra) |
| email/telefone | **UNAVAILABLE** como chave | só existem crus em `Lead` (PII); sem hash/normalização definidos; e são sinal de pessoa, não de negociação |
| produto/oferta | **UNAVAILABLE** | nenhum campo |
| card criado por automação | **OPEN** (D-G1) | depende de o CRM distinguir automação × pessoa |

Regra v0: **decisão automática só produz `linked` no self-link de fundação**; ligar a qualquer
outro Deal exige decisão manual. Sinais
SUPPORTING/WEAK só produzem `ambiguous` (com candidatos) ou `unresolved`. "Card mais recente vence"
e "card aberto vence" são proibidos.

## 6. Semantics

- **Ambiguity:** `ambiguous` e `unresolved` são estados legítimos e persistentes; nada é consolidado.
  Ex.: dois cards com mesmo nome, mesmo closer, datas próximas, sem chave forte → `ambiguous`.
- **Human resolution:** humano grava `linked` (A e B → X) ou `linked` separados (A → X, B → Y);
  autoridade `manual` persiste; decisão `automatic` não substitui `manual` (mesma regra de
  `append_match_decision`); fork → `conflict`, reparo manual.
- **Reopen / parallel card:** representável como `linked` do card novo ao Deal existente **ou** como
  Deal novo — sem regra universal. Card antigo LOST + novo OPEN **não** implica mesmo Deal;
  reabertura explícita permite `linked` (manual ou via sinal STRONG se D-G confirmar).
- **Automation-created card:** existir não cria Deal; pode ficar `unresolved`, `linked` a um Deal
  existente ou `not_a_deal`.
- **Outcome:** continua por `deal_id`. Cards A e B → X ⇒ um só Outcome de X. Estado de cada card
  entra como `OutcomeEvidence` (`source_record_ref` = card) atribuída ao Deal pela identidade;
  cards paralelos com status conflitantes viram **evidências conflitantes** tratadas pela policy do
  Outcome (nunca "o status do card vence"). Só evidência de card `linked` ao Deal pode ser
  atribuída a ele.
- **Call matching:** DEP-1 continua Call → Deal. Hoje o matcher só casa com o card fundador
  (`deal.external_id`). Com identidade, o **gerador de candidatos** (matcher) resolve
  `call.source_id` → source record → Deal via `resolve_deal_for_source_record`; o resolver de
  match atual **não muda**.

## 7. Decisão arquitetural pendente (bloqueia a política de fundação e o matcher, não o contrato)

Como Deals nascem, dado que hoje Deal = card:

| Opção | Como | Custo |
|---|---|---|
| **7a. Deal fundado por um card (compatível)** | `Deal` continua como está; o card que o funda é o seu `external_id`; outros cards se ligam por decisão de identidade. **Ingestão não cria Deal por card**: cria decisão `unresolved`; um Deal só nasce por decisão explícita de fundar | aditivo; mas se dois cards já viraram Deals (X e Y), juntar exige **fusão de Deals** (alias Deal → Deal) — fora do v0 |
| **7b. Deal com identidade própria** | `deal_id` deixa de derivar do card; `Deal` perde `external_id`/campos de card | **breaking**: `derive_deal_id`, `Deal`, matcher, testes |

**Recomendação: 7a** + regra "nenhum Deal é criado automaticamente por card" + fusão de Deals
**deferred** (enquanto não houver ingestão real de CRM, não há Deals duplicados a fundir).

## 8. Invariants (para a implementação)

1. Source record nunca é Deal; Deal nunca é inferido do card sem decisão.
2. No máximo um head de identidade por source record; fork → `conflict`.
3. `linked` ⟺ exatamente um `deal_id`; `ambiguous` ⟺ ≥ 2 candidatos; demais sem Deal.
4. Automático só produz `linked` no self-link de fundação e nunca `not_a_deal`; nunca substitui
   `manual`.
5. `created_at` nunca decide. Três mecanismos distintos: **mesmo `identity_decision_id` + payload
   idêntico** → no-op; **mesmo id + payload diferente** → erro (`ValueError`); **outra decisão para o
   mesmo registro** → CAS: head esperado desatualizado ou automático sobre manual →
   `DealIdentityConflict`; decisão nova com o mesmo resultado do head → no-op.
6. Chaves nunca colidem entre providers nem com `deal_id` (todos os campos da chave no hash, prefixo
   próprio).
7. Outcome é único por Deal, independente de quantos cards estão `linked`.
8. Evidência de um card só é atribuível a um Deal se o card estiver `linked` a ele.

## 9. Edge cases (casos obrigatórios)

| # | Caso | Resultado |
|---|---|---|
| 1 | Card claramente um Deal | `linked` automático ao Deal que ele funda (self-link) |
| 2 | Dois cards confirmados como mesma negociação | ambos `linked` a X (manual) |
| 3 | Mesmo nome, sem evidência forte | `ambiguous`/`unresolved`; nunca consolidado |
| 4 | Card antigo LOST + novo OPEN | novo fica `unresolved`/`ambiguous`; não assume mesmo Deal |
| 5 | Novo card marcado explicitamente como reabertura | `linked` ao Deal existente (manual; automático só se D-G confirmar sinal) |
| 6 | Cards paralelos com status conflitantes | um Deal, evidências conflitantes → policy do Outcome |
| 7 | Card de automação | não cria Deal; `unresolved`/`linked`/`not_a_deal` |
| 8 | Mesmo registro ingerido duas vezes | decisão idêntica ou mesmo resultado → no-op |
| 9 | Mesma identidade, payload incompatível | mesmo id → hard error; decisão concorrente → CAS conflict |
| 10 | Dois providers | chaves diferentes; sem colisão |
| 11 | Humano resolve ambiguidade | `manual` `linked`; persiste |
| 12 | Automação contraria humano | recusada (`conflict` de autoridade) |
| 13 | Registro órfão | `unresolved` ou `no_decision` — legítimo |
| 14 | Deal com vários registros | um Outcome por `deal_id` |

## 10. Open business decisions

| # | Pergunta | Dono |
|---|---|---|
| DI-M1 | Aprovar 7a (Deal fundado por card, nenhum Deal automático por card, fusão deferred) ou 7b | Matheus |
| DI-M2 | D sozinha (sem `SourceRecord` em v0) — **adotada** no contrato implementado; reverter se o card precisar de atributos próprios além de evidências | Matheus |
| DI-M3 | ADR após validação de Gabriel | Matheus |
| DI-G1 | O Kommo registra reabertura/continuação ou vínculo entre cards? | Gabriel |
| DI-G2 | Quando um card novo do mesmo lead é continuação vs nova negociação? | Gabriel |
| DI-G3 | Cards de Salesbot/automação: representam negociação ou só ação operacional? (liga a D-G1) | Gabriel |
| DI-G4 | Existe id de oportunidade estável entre cards/sistemas? | Gabriel |

## 11. Rejected alternatives

1 card = 1 Deal; lista de cards no Deal; identidade por nome/similaridade; "card mais recente
vence"; "card aberto vence"; dedup automático/fuzzy/LLM; `SourceRecord` + MDM completo em v0.

## 12. Implementation plan

1. **Feito:** `domain/deal_identity.py` — `DealIdentityDecision`, `derive_source_record_key`,
   `derive_deal_identity_decision_id`, `resolve_deal_for_source_record`,
   `append_deal_identity_decision` (CAS, autoridade manual), reusando `_chain.linear_chain`.
   Aditivo; `Deal`, matching e Outcome intocados. Testes: `tests/unit/domain/test_deal_identity.py`.
2. **Após DI-M1:** política de fundação na ingestão (nenhum Deal automático por card).
3. **Depois (separado):** matcher consulta identidade para gerar candidatos; atribuição de
   `OutcomeEvidence` exige card `linked` (write path).
4. Fora: fusão de Deals, sinais automáticos, adapter Kommo.
