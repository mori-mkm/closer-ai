# Data Dependency Map

Mapa explícito do que depende de dado real, para que o time (e agents) saibam exatamente onde
o trabalho para até que um humano resolva um acesso/decisão. Complementa
`docs/context/CURRENT_STATE.md` (estado) e `docs/product/ROADMAP.md` (sequência de fases).

Papéis usados abaixo (sem nomes pessoais — só quem decide/resolve cada blocker):
**Data/Analytics Lead**, **AI/Backend Lead**, **Product/RevOps**.

## Cadeia 1 — Agro/Zoom → Call Intelligence

Runbook operacional: [`docs/data/REAL_CALL_VALIDATION_KIT.md`](../data/REAL_CALL_VALIDATION_KIT.md).
Armazenamento compartilhado (OCI, privado, nunca no Git): [`docs/data/OCI_SHARED_STORAGE.md`](../data/OCI_SHARED_STORAGE.md).

```
Agro/Zoom real (108 calls)
    ↓
source adapter          (não existe ainda — a escrever quando o formato real for conhecido)
    ↓
Canonical Calls          (normalize_call(), já implementado)
    ↓
Objection extraction     (RuleBasedObjectionExtractor, já implementado)
    ↓
Call Intelligence
```

| Nó | INPUTS | OUTPUTS | BLOCKERS | OWNER ROLE | STATUS |
|---|---|---|---|---|---|
| Agro/Zoom real | acesso ao corpus de 108 calls | nenhum ainda | localização/acesso não confirmados; autorização de uso não confirmada | Data/Analytics Lead | BLOCKED |
| source adapter | formato real confirmado (Zoom API/vtt/srt) | dict compatível com `AgroRawCall` | depende do nó acima | AI/Backend Lead | NOT STARTED |
| `AgroRawCall` → `parse_agro_call()` | dict do source adapter | `AgroParseResult` (raw_input + quality_flags + metadata) | nenhum de código — implementado e testado contra hipótese sintética | AI/Backend Lead | IMPLEMENTED (não validado contra dado real) |
| `normalize_call()` | `AgroParseResult.raw_input` | `Call` canônico | nenhum | AI/Backend Lead | IMPLEMENTED |
| Objection extraction | `Call` canônico | `list[ObjectionEvent]` | keyword matcher em português, taxonomia v0 de 4 categorias | AI/Backend Lead | IMPLEMENTED (baseline determinístico) |
| Call Intelligence (agregado por call) | `ObjectionEvent[]` | nenhum consumidor ainda | `analytics/` vazio, sem decisão de o que agregar | AI/Backend Lead | NOT STARTED |

## Cadeia 2 — Kommo → Deal timeline

```
Kommo real
    ↓
Lead/Deal/StageEvent      (contrato já implementado, nenhum adapter Kommo)
    ↓
CallDealMatcher
    ↓
Deal timeline
```

| Nó | INPUTS | OUTPUTS | BLOCKERS | OWNER ROLE | STATUS |
|---|---|---|---|---|---|
| Kommo real | export ou acesso de API v4 | nenhum ainda | export/acesso não disponível; payload/pipelines/stages reais desconhecidos | Data/Analytics Lead / Product/RevOps | BLOCKED |
| Kommo adapter | payload real confirmado | `Lead`/`Deal`/`StageEvent` instâncias | depende do nó acima | AI/Backend Lead | NOT STARTED |
| `Lead`/`Deal`/`StageEvent` contrato | dict mapeado pelo adapter | instâncias validadas (IDs determinísticos, invariantes de outcome) | nenhum de código | AI/Backend Lead | IMPLEMENTED |
| `CallDealMatcher` (`ExactExternalIdMatcher`) | `Call` + `list[Deal]` candidatos | `list[CallDealMatch]` | só um sinal determinístico (`source_id == external_id`); sem email/telefone (Participant não carrega esses campos) | AI/Backend Lead | IMPLEMENTED (baseline único) |
| Deal timeline | `CallDealMatch(status='matched')` + `StageEvent[]` | nenhum consumidor ainda | `analytics/`/`storage/` vazios | AI/Backend Lead | NOT STARTED |

## Cadeia 3 — Outcome Intelligence

```
Canonical Calls + CRM real
    ↓
Call↔Deal (matched)
    ↓
Deal → Calls → Events → Outcome
    ↓
Outcome Intelligence
```

| Nó | INPUTS | OUTPUTS | BLOCKERS | OWNER ROLE | STATUS |
|---|---|---|---|---|---|
| Call↔Deal matched | Cadeia 1 + Cadeia 2 completas | linhas `CallDealMatch(status='matched')` reais | ambas as cadeias acima bloqueadas por dado | AI/Backend Lead | BLOCKED |
| Deal → Calls → Events → Outcome (join) | matches reais + `ObjectionEvent[]` + `Deal.outcome` | dataset unificado por deal | nenhuma camada de storage/query existe ainda | AI/Backend Lead | NOT STARTED |
| Outcome Intelligence | dataset unificado, amostra suficiente de won/lost | padrões/agregados | definição de "outcome" ainda em aberto (`docs/context/OPEN_QUESTIONS.md`); amostra real inexistente | AI/Backend Lead / Product/RevOps | NOT STARTED |

## Cadeia 4 — Golden Set → Extractor v1

```
Golden Set
    ↓
LLM extraction evaluation
    ↓
Extractor v1
```

| Nó | INPUTS | OUTPUTS | BLOCKERS | OWNER ROLE | STATUS |
|---|---|---|---|---|---|
| Golden Set real | 20-30 calls reais representativas, dupla anotação | dataset rotulado + agreement calculado | corpus real não disponível; anotadores não definidos; regras de anotação não fechadas | Data/Analytics Lead / Product/RevOps | NOT STARTED |
| Avaliação do extractor v0 contra Golden Set real | Golden Set real + `RuleBasedObjectionExtractor` | precision/recall/F1 real, decisão sobre extractor v1 | depende do nó acima | AI/Backend Lead | BLOCKED |
| Extractor v1 (LLM-backed, se justificado) | avaliação acima mostrando gap real | novo `ObjectionExtractor` (mesma interface `Protocol`) | depende de decisão de provedor de LLM (`docs/context/OPEN_QUESTIONS.md`) e da avaliação acima | AI/Backend Lead | NOT STARTED |

## Lineage (rastreabilidade, sem PII no id)

Cadeia de proveniência desejada, para sempre poder responder "de onde veio este resultado?"
sem que o próprio id identifique a pessoa:

```
source file / source API object     (ex.: um .vtt do Zoom, um objeto "deal" da API Kommo —
                                      vive só em data/raw/, nunca em Git)
    ↓
raw dataset id                      (identificador do lote recebido — ver manifest,
                                      data/README.md — nunca o conteúdo em si)
    ↓
source adapter                       (Agro: já existe; Kommo: não existe ainda)
    ↓
canonical entity                     (Call, Lead, Deal — ids determinísticos derivados de
                                      company_id/source/source_id, nunca de nome/email)
    ↓
extracted event                      (ObjectionEvent — id derivado de call_id+segment_id+
                                      category)
    ↓
deal association                     (CallDealMatch — liga call_id a deal_id, com evidence
                                      não-PII)
    ↓
analytics                            (agregados — `analytics/` ainda não existe)
```

Cada seta acima já é rastreável hoje pelos ids determinísticos existentes (`normalization/ids.py`,
`domain/objection.py`, `domain/lead.py`, `domain/deal.py`, `domain/matching.py`) — nenhuma dessas
funções hash+deriva a partir de um campo *chamado* nome/email/telefone. Isso é uma garantia
literal sobre os campos hasheados (`company_id`/`source`/`source_id`/`external_id`/etc.), **não**
uma garantia de que o resultado é anonimizado: sha256 de um valor de baixa entropia (ex.: um
`external_id` de CRM que por acaso seja um email) é reversível por dicionário — hash não é
anonimização quando o espaço de entrada é pequeno/enumerável. Isso é uma pré-condição sobre os
adapters de origem, não algo que este pack resolve: **nenhum adapter (Agro, Kommo, futuro)
deve popular `source_id`/`external_id` com um valor que já seja PII em si** (email, telefone,
nome) — deve ser um identificador opaco do sistema de origem (id numérico, UUID), confirmado
contra a amostra real antes do primeiro batch. O elo que falta na cadeia é só o primeiro
(`source file → raw dataset id`), porque não existe ainda um manifest real associando um lote
recebido a um id — ver `data/README.md` para o template proposto.

## Leitura rápida

Toda cadeia acima converge no mesmo bloqueador transversal: **acesso a dado real** (Agro +
Kommo) e **autorização de uso**. Nenhum item marcado BLOCKED progride com mais código — só com
uma decisão/acesso humano. Itens NOT STARTED que não dependem diretamente de dado real (ex.:
desenho de taxonomia, regras de anotação) podem progredir em paralelo — ver
`docs/product/ROADMAP.md` ("PARALLEL / CAN PROGRESS WITHOUT DATA").
