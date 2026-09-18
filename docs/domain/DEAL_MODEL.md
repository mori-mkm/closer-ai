# Deal Model v0

Contrato de `Lead`, `Deal`, `StageEvent`, `CallDealMatch`/`MatchEvidence` — a fundação de
domínio comercial descrita em `docs/architecture/DATA_MODEL.md`. Implementação:
`src/closer_ai/domain/lead.py`, `src/closer_ai/domain/deal.py`,
`src/closer_ai/domain/matching.py`. Desenhado por Domain Agent, revisado por Reviewer (2
rounds — 1 REJECT com 2 blockers resolvidos, depois aprovado) antes de qualquer código.

## Princípio central

**Deal é a unidade comercial. Call não tem outcome comercial.** Uma negociação (`Deal`) pode
ter zero, uma ou várias `Call`s ao longo do funil; o resultado final (ganho/perdido) existe
**uma única vez**, no `Deal`, nunca duplicado por call. `Call` (já existente,
`closer_ai.normalization.Call`) carrega eventos/comportamento — hoje `ObjectionEvent`, no
futuro sinais/riscos/momentos — nunca `outcome`, `value` ou `closed_at`.

```
Deal
│
├── Call A
│   ├── Objection 1
│   └── Objection 2
│
├── Call B
│   └── Objection 3
│
├── Stage Events (histórico append-only)
│
└── Outcome (OPEN / WON / LOST / UNKNOWN — só aqui, nunca em Call)
```

Esta árvore é conceitual — no schema real, `Deal` **não** embute `Call`/`Objection` (ver
"Sem nesting" abaixo). A ligação Deal↔Call é via `CallDealMatch`:

```
Call
  ↓
candidate Deals
  ↓
CallDealMatch (uma linha por candidato avaliado)
  ↓
MATCHED / AMBIGUOUS / REJECTED / UNMATCHED / MANUAL_REVIEW
  ↓
Deal (via CallDealMatch.deal_id, quando status permite)
```

## Entidades

### Lead (`domain/lead.py`)

Identidade da pessoa/empresa associada a um Deal, vinda de um contato de CRM. Não carrega
outcome nem histórico de calls.

| Campo | Tipo | Por quê |
|---|---|---|
| `lead_id` | `str` | determinístico, ver "IDs" |
| `company_id` | `str` | tenant — reusa o campo já existente em `Call`, não um `tenant_id` novo (ver "Tenant/Company" abaixo) |
| `source` / `external_id` | `str` | "qual sistema" + "id nesse sistema", mesmo padrão de `Call.source`/`Call.source_id` |
| `name`, `email`, `phone`, `company_name` | `str \| None` | nenhum obrigatório — Lead guarda o que a fonte deu; completude é problema de `CallDealMatch` avaliar, não de `Lead` armazenar |
| `metadata` | `dict` | passthrough, sem validação |

`company_name` (não `company`): o empregador do próprio lead, deliberadamente renomeado para
não colidir com `company_id`, o tenant.

Nenhum campo de identificação é obrigatório — ver "Edge cases".

### Deal + StageEvent (`domain/deal.py`)

| Campo (Deal) | Tipo | Por quê |
|---|---|---|
| `deal_id` | `str` | determinístico |
| `company_id`, `source`, `external_id` | `str` | mesmo padrão de Lead/Call |
| `lead_id`, `owner_id`, `pipeline_id` | `str \| None` | opcionais — um Deal pode existir sem contato vinculado; `owner_id` é o closer atribuído no CRM, deliberadamente não assumido igual a nenhum `Call.closer_id` (um colega pode conduzir uma call em deal de outra pessoa) |
| `current_stage` | `Stage` (sem default) | cache do estágio mais recente — ver "Stage vs Outcome" |
| `outcome` | `DealOutcome` (sem default) | ver "Stage vs Outcome" |
| `created_at` | `datetime` tz-aware | — |
| `closed_at` | `datetime \| None` | obrigatório sse `outcome` terminal — ver invariantes |
| `value`, `currency` | `float \| None`, `str \| None` | `currency` obrigatório se `value` setado; risco de precisão monetária conhecido (float, não Decimal) e aceito para v0 |
| `metadata` | `dict` | passthrough |

**Sem `call_ids`.** A associação Deal↔Call vive inteiramente em `CallDealMatch`
(`status='matched'`), nunca um campo/lista em `Deal`. Um campo assim seria uma segunda fonte de
verdade (um match pode ser rejeitado depois em revisão, sem atualizar a lista) e, num model
`frozen`, forçaria reemitir o snapshot inteiro a cada call nova — puro churn.

**Stage vs Outcome: eixos ortogonais.** `Stage` (`created`/`qualification`/`proposal`/
`negotiation`/`other`) **nunca** contém `won`/`lost` — isso vive só em `DealOutcome`
(`open`/`won`/`lost`/`unknown`). Bate com como Kommo/Pipedrive de fato modelam (won/lost é uma
flag de status independente do `pipeline_stage_id` — um deal pode ficar em "negotiation" pra
sempre depois de marcado como perdido) e com a própria árvore Stage/Outcome já existente neste
documento antes desta v0.

**Sem default em `current_stage`/`outcome`.** Todo caller precisa declarar os dois
explicitamente. É o mecanismo concreto que impede "OPEN virar LOST por omissão" e "UNKNOWN
virar OPEN por omissão" — não existe fallback que disfarce um caller que esqueceu de setar
outcome, o que importa dado quantos deals do Agro ficam OPEN por muito tempo.

| Campo (StageEvent) | Tipo | Por quê |
|---|---|---|
| `stage_event_id` | `str` | determinístico, único caso em `domain/` que inclui timestamp no hash — ver "IDs" |
| `deal_id`, `stage`, `occurred_at`, `source` | — | evento de log: "stage X em T" |
| `external_stage_id` | `str \| None` | id bruto do CRM, para quando `stage='other'` precisar de re-mapeamento futuro |

Append-only, sem constraint de unicidade em `(deal_id, stage)` — reentrar no mesmo stage depois
é um evento novo e legítimo (bounce-back), não duplicata.

### DealOutcome: enum, não entidade

Fica como `Literal` em `Deal`, não promovido a entidade própria — não tem identidade,
lifecycle ou necessidade de auditoria própria hoje (ninguém pediu "outcome voltou de WON pra
OPEN, mostra por quê"). `STALE` foi avaliado e descartado: precisaria de um threshold de
tempo-sem-atividade que é decisão de produto ainda em aberto
(`docs/context/OPEN_QUESTIONS.md`) e depende do ciclo de venda real do Agro, não documentado.
Isso é um rótulo derivado que `analytics/` pode calcular depois de `created_at` +
`outcome='open'`, não um estado que este contrato deveria inventar agora.

### CallDealMatch + MatchEvidence (`domain/matching.py`)

Um `CallDealMatch` significa **"a evidência disponível sugere que esta call pertence a este
deal"**, nunca "o algoritmo tem certeza". Uma linha = uma tentativa (call, deal candidato,
método, momento) — não uma crença mutável única por call.

| Campo | Tipo | Por quê |
|---|---|---|
| `call_deal_match_id` | `str` | determinístico, inclui `created_at` (mesma razão de `stage_event_id`) |
| `call_id` | `str` | — |
| `deal_id` | `str \| None` | `None` sse `status='unmatched'` (nenhum candidato) |
| `matching_method` | `MatchMethod` | ver "Matching method" |
| `status` | `MatchStatus` | ver "Matching status" |
| `confidence_level` / `confidence_score` | `ConfidenceLevel`, `float \| None` | ver "Confidence" |
| `evidence` | `list[MatchEvidence]` | não-vazio exceto quando `unmatched` |

#### Matching method

Um `Literal` plano — `exact_external_id`, `exact_email`, `exact_phone`, `name_and_datetime`,
`name_only`, `manual`, `other` — não uma hierarquia
determinístico/heurístico/manual. Essa "camada de confiabilidade" já é expressa por
`confidence_level`; um campo `method_class` paralelo seria redundante e divergiria (alguém
marca `exact_email` como confiança média, o que não deveria ser possível se é determinístico
por definição).

#### Confidence

`confidence_level: HIGH/MEDIUM/LOW` (sempre obrigatório) + `confidence_score: float | None`
opcional — **não** um float solto. Um float sozinho não é auditável sem uma tabela de
threshold rastreada fora do código (que pode divergir); pior, métodos determinísticos
(`exact_*`, `manual`) não têm score graduado real — forçá-los a reportar uma constante (ex.
sempre 1.0) repetiria exatamente por que `ObjectionEvent` não tem campo de confidence em v0
("uma constante sem sinal"). Métodos determinísticos/manuais são forçados a
`confidence_level='high'` e `confidence_score=None`; métodos heurísticos carregam um score real
em `[0, 1]` mais um level informado independentemente. As bandas numéricas score→level (ex.
`>=0.85 high`) ficam documentadas em código, não hardcoded num validator — calibração é
responsabilidade do algoritmo de matching (a ser construído), não deste contrato.

`status='matched'` **exigir** `confidence_level='high'` é a política pretendida, mas
deliberadamente **não** é enforçada pelo validator — seria a mesma classe de decisão de
calibração que o parágrafo acima já evita hardcodar. É responsabilidade do write path (o
matcher) nunca emitir `matched` abaixo de alta confiança, roteando o resto para
`manual_review`.

#### Matching status

`matched`, `ambiguous`, `rejected`, `unmatched`, `manual_review`. **Regra crítica**: ambiguidade
é representada como **múltiplas linhas** — uma `CallDealMatch` por candidato empatado, mesmo
`call_id`, mesmo `created_at` de batch, `deal_id`/`confidence_score` diferentes, todas
`status='ambiguous'`. Nunca uma única linha "vencedora" com os candidatos perdedores
descartados silenciosamente. Essa garantia é responsabilidade de quem escreve os matches
(comparar candidatos antes de decidir status), não algo que um validator de linha única consiga
ver (não enxerga as linhas irmãs).

#### Match evidence

`MatchEvidence(signal, matched, score, detail)` — `signal` é um `Literal` fechado
(`external_id_exact`, `email_exact`, `phone_exact`, `name_similarity`, `datetime_proximity`,
`human_decision`, `other`), nunca o dado comparado bruto. `detail` é uma nota textual não-PII
(ex. "89% similaridade de nome"), **convenção, não enforcement** — nada no schema impede um
caller descuidado de colocar um email real em `detail`; gap real, não resolvido aqui.

## IDs determinísticos

Mesma técnica de `normalization/ids.py` e `domain/objection.py` (sha256 sobre `json.dumps` de
lista, 24 hex chars, prefixo) — reimplementada localmente em cada módulo, nunca importando o
`_hash` privado de `normalization/ids.py` (dependência read-only).

| Função | Input | PII no hash? |
|---|---|---|
| `derive_lead_id(company_id, source, external_id)` | — | não |
| `derive_deal_id(company_id, source, external_id)` | — | não |
| `derive_stage_event_id(deal_id, stage, occurred_at, source)` | inclui timestamp | não |
| `derive_call_deal_match_id(call_id, deal_id, matching_method, created_at)` | inclui timestamp | não |

`derive_stage_event_id`/`derive_call_deal_match_id` são os únicos, em todo `domain/`, a incluir
timestamp no hash — desvio deliberado de `derive_call_id`/`derive_objection_id`. Ambos são
entidades de **log de evento/tentativa** ("algo aconteceu em T" / "uma tentativa de match em
T"), não fatos extraídos — a mesma transição/tentativa reenviada exatamente igual (retry de
webhook) precisa colapsar no mesmo id, mas a mesma tupla num momento genuinamente diferente é
um evento novo e distinto. O timestamp é canonicalizado para UTC (`astimezone(UTC).isoformat()`)
antes de entrar no hash — dois instantes equivalentes em offsets diferentes precisam produzir a
mesma string, e `json.dumps` não serializa `datetime` diretamente.

Nenhuma dessas funções altera `derive_call_id`/`derive_segment_id`
(`normalization/ids.py`) ou `derive_objection_id` (`domain/objection.py`), que continuam
exatamente como estavam.

## Tenant / Company

Decisão: **reusar `company_id`** (já existente em `Call`) como identificador de tenant em
`Lead`/`Deal`/`StageEvent`/`CallDealMatch` — nenhum `tenant_id` novo foi criado. Um único
conceito de multi-tenancy em todo o codebase.

## Cardinalidades

- Deal ↔ Lead: N:1 (`Deal.lead_id` opcional).
- Deal ↔ Call: logicamente 1:N, só via `CallDealMatch(status='matched')` — nunca um campo em
  nenhum dos dois lados (sem nesting, sem lista).
- Deal ↔ StageEvent: 1:N, append-only.
- Call ↔ CallDealMatch: 1:N (histórico de tentativas/candidatos/métodos ao longo do tempo).
- Deal ↔ CallDealMatch: 1:N (um deal pode ser candidato em várias calls, aceito ou não).

**Não impedido estruturalmente, de propósito**: nada no schema impede duas linhas
`status='matched'` para o mesmo `call_id` contra deals diferentes. Isso fica para uma
constraint de unicidade em nível de storage/aplicação (`(call_id, status='matched')`) quando
essa camada existir — rastreado aqui como requisito futuro explícito, não perdido em comentário
solto.

## Invariantes verificáveis no próprio model

- `Lead`/`Deal`/`StageEvent`/`CallDealMatch`: imutáveis (`frozen=True`) — "frozen" aqui
  significa "snapshot imutável", igual a `Call`/`ObjectionEvent`: um re-sync de CRM produz uma
  nova instância com o mesmo id, não uma mutação. Histórico completo vs. "última versão vence"
  é decisão futura de storage.
- `Deal`: `closed_at is not None` ⟺ `outcome` terminal (`won`/`lost`); `closed_at >= created_at`;
  `currency` obrigatório se `value` setado; `value >= 0`.
- `CallDealMatch`: `deal_id` obrigatório exceto quando `unmatched`; `evidence` não-vazio exceto
  quando `unmatched`; métodos determinísticos/manuais forçados a `confidence_level='high'` sem
  score; `call_deal_match_id`/`stage_event_id`/`deal_id`/`lead_id` sempre re-derivados e
  comparados contra o valor fornecido (mesmo padrão de `ObjectionEvent.objection_id`).

## Invariantes NÃO verificáveis no próprio model (conhecidas, não escondidas)

- `Deal.current_stage` deveria sempre bater com o `StageEvent` de `occurred_at` mais recente
  daquele `deal_id` — um `Deal` isolado não enxerga seu próprio histórico (por design, sem
  nesting). Fica para o write path futuro (`storage/`/`integrations/`) garantir isso
  atomicamente.
- No máximo uma linha `status='matched'` por `call_id` — ver "Cardinalidades" acima.
- `confidence_score` vs `confidence_level` para métodos heurísticos não têm cross-check: nada
  impede `score=0.1` com `level='high'` hoje. A correção da calibração é responsabilidade
  exclusiva do algoritmo de matching (write path), não deste schema.

## Edge cases considerados e rejeitados

- **`Lead` exigir pelo menos um campo de identificação (nome/email/telefone).** Rejeitado: isso
  é problema de `CallDealMatch` avaliar (um sinal só existe se o campo existir), não de `Lead`
  recusar armazenar o que a fonte deu.
- **`reviewed_by`/identidade de quem fez `manual_review`.** Rejeitado por agora — não existe
  conceito de usuário/auth em lugar nenhum do codebase ainda; adicionar isso agora inventaria um
  conceito estranho sem consumidor. Campo puramente aditivo para quando um fluxo de revisão
  humana existir de fato.
- **Hierarquia `MatchMethod` (determinístico/heurístico/manual) como classe própria.**
  Rejeitado: redundante com `confidence_level`.
- **Enforcement de PII em `MatchEvidence.detail` via regex/heurística.** Rejeitado — alto risco
  de falso positivo/negativo; fácil adicionar depois sem quebrar o contrato. Fica como gap
  documentado, não resolvido.

## Fora de escopo (deferred)

Nenhuma integração real com Kommo/CRM — todos os campos (`source`, `external_id`,
`pipeline_id`, `external_stage_id`) são genéricos, não assumem payload específico de nenhum
provedor. Nenhuma persistência (`storage/`). Nenhum algoritmo de matching sofisticado (fuzzy,
embeddings, LLM) — `ExactExternalIdMatcher` é o único baseline, com um único sinal
determinístico (`call.source_id == deal.external_id`). Outcome Intelligence não implementada.

## Relação com outros documentos

`docs/architecture/DATA_MODEL.md` tem a árvore conceitual completa do Deal. Domínio geral de
vendas: `docs/domain/SALES_MODEL.md`. Termos: `docs/domain/GLOSSARY.md`. `ObjectionEvent`
(`docs/domain/OBJECTION_MODEL.md`) permanece inalterado — liga-se a este modelo só via
`call_id` (nunca uma referência direta a `Deal` dentro de `ObjectionEvent`).
