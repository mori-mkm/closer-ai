# Data Dependency Map

Mapa explícito do que depende de dado real (reconciliado em 2026-09-29), para que o time (e agents) saibam exatamente onde
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
| Call Intelligence (agregado por call) | `ObjectionEvent[]` | nenhum consumidor ainda | nenhum módulo de analytics existe; sem decisão de o que agregar | AI/Backend Lead | NOT STARTED |

## Cadeia 2 — Kommo → Deal timeline

```
Kommo real
    ↓
source record (card) ──DealIdentityDecision──► Deal canônico   (ADR-002; contrato implementado)
    ↓
Lead/Deal/StageEvent      (contrato já implementado, nenhum adapter Kommo)
    ↓
CallDealMatcher → CallDealMatch (candidatos) → MatchDecision → resolve_current_match   (ADR-003)
    ↓
Deal timeline
```

| Nó | INPUTS | OUTPUTS | BLOCKERS | OWNER ROLE | STATUS |
|---|---|---|---|---|---|
| Kommo real | export ou acesso de API v4 | nenhum ainda | export/acesso não disponível; payload/pipelines/stages reais desconhecidos | Data/Analytics Lead / Product/RevOps | BLOCKED |
| Kommo adapter | payload real confirmado | `Lead`/`Deal`/`StageEvent` instâncias + decisões de identidade card → Deal (fundação explícita, nunca 1 Deal por card) | depende do nó acima | AI/Backend Lead | NOT STARTED |
| `Lead`/`Deal`/`StageEvent` contrato | dict mapeado pelo adapter | instâncias validadas (IDs determinísticos, invariantes de outcome) | nenhum de código | AI/Backend Lead | IMPLEMENTED |
| `CallDealMatcher` (`ExactExternalIdMatcher(provider)`) | `Call` + decisões de identidade + `list[Deal]` candidatos | `list[CallDealMatch]` (candidatos) | só um sinal determinístico (registro do CRM da call via Deal Identity, só `linked`); sem email/telefone | AI/Backend Lead | IMPLEMENTED (baseline único) |
| `MatchDecision` + `resolve_current_match` | candidatos + decisões automáticas/manuais | relação atual Call → Deal (só `matched` fornece `deal_id`) | atomicidade do CAS depende de storage (TD-09); workflow de revisão manual inexistente | AI/Backend Lead | IMPLEMENTED (contrato) |
| Deal timeline | `resolve_current_match` (estado `matched`) + `StageEvent[]` | nenhum consumidor ainda | nenhuma camada de analytics/storage existe | AI/Backend Lead | NOT STARTED |

## Cadeia 3 — Outcome Intelligence

```
Canonical Calls + CRM real
    ↓
Call ↔ Deal atual (resolve_current_match == matched)
    ↓
Deal → OutcomeEvidence → EvidenceDisposition → OutcomeAssessment → outcome canônico atual (ADR-001)
    ↓
Deal → Calls → Events → Outcome   (composição: commercial_state.resolve_call_commercial_state)
    ↓
Outcome Intelligence
```

| Nó | INPUTS | OUTPUTS | BLOCKERS | OWNER ROLE | STATUS |
|---|---|---|---|---|---|
| Call↔Deal atual | Cadeia 1 + Cadeia 2 completas | `MatchDecision` reais cujo head é `matched` (nunca linhas `CallDealMatch(status='matched')` sozinhas) | ambas as cadeias acima bloqueadas por dado | AI/Backend Lead | BLOCKED |
| Outcome canônico | `OutcomeEvidence` reais do CRM/closers + policy | `OutcomeAssessment` atual por Deal | núcleo estrutural implementado; **policy real bloqueada** por D-G1/D-G2/D-G5/D-G6; nenhum dado real | AI/Backend Lead / Product/RevOps | PARTIAL (núcleo) |
| Deal → Calls → Events → Outcome (join) | relação atual Call → Deal + `ObjectionEvent[]` + outcome canônico atual (nunca `Deal.outcome`, que é projeção legada) | dataset unificado por deal | composição por call existe (`commercial_state`); nenhuma camada de storage/query | AI/Backend Lead | PARTIAL (composição por call) |
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
| Classifier LLM experimental (E0/E1/E2) | `Call` + prompt por braço + `ClassificationProvider` | `ClassificationRun` / artifacts do Experiment Runner | implementado com Ollama local (ADR-005); só compliance operacional, sem gold | AI/Backend Lead | IMPLEMENTED (experimental) |
| Extractor v1 de produto (se justificado) | avaliação contra gold real mostrando gap | contrato de domínio (`ObjectionEpisode`, D7) + extractor | depende de gold real (D3), D6/D7 e de provider autorizado para dado real (ADR-004/005) | AI/Backend Lead | NOT STARTED |

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
deal association                     (CallDealMatch = candidato com evidence não-PII;
                                      MatchDecision = relação atual autoritativa — ADR-003)
    ↓
analytics                            (agregados — `analytics/` ainda não existe)
```

Cada seta acima já é rastreável hoje pelos ids determinísticos existentes (`normalization/ids.py`,
`domain/objection.py`, `domain/lead.py`, `domain/deal.py`, `domain/deal_identity.py`,
`domain/matching.py`, `domain/outcome.py`) — nenhuma dessas
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
