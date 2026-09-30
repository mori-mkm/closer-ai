# ADR-001 — Canonical Outcome Contract v0

## Status

Accepted

Aceito como design antes da implementação (o texto original registrava "Implementação ainda não
iniciada — ver Implementation gate"). O estado atual está em "Implementation status" no fim deste ADR.

Contrato detalhado: [`OUTCOME_CONTRACT_V0_PROPOSAL.md`](../domain/OUTCOME_CONTRACT_V0_PROPOSAL.md)
(rev. 2). Este ADR registra **por que** decidimos e **que consequências aceitamos**; o
proposal continua sendo a fonte de **como** o contrato funciona.

## Context

- O CRM não representa toda a verdade comercial. A auditoria do CRM AgroTalento mostrou leads
  que rejeitaram a oferta e continuam abertos, aparecem como unknown, são fechados por
  automação/no-contact (Salesbot), têm retorno só em planilhas de closers, ou têm motivo de
  perda não confiável.
- Rejeições e perdas podem existir **fora** do CRM.
- Fechamento por automação parece perda sem ser rejeição comercial.
- Cards paralelos do CRM podem conflitar entre si.
- `Deal.outcome` hoje é um campo de snapshot preenchido a partir do CRM, sem evidência, fonte,
  histórico ou confiança ([`deal.py`](../../src/closer_ai/domain/deal.py),
  [`DEAL_MODEL.md`](../domain/DEAL_MODEL.md)).
- Outcome Intelligence precisa de outcomes **auditáveis e reproduzíveis**, com incerteza
  explícita, sem aprender ruído de higiene do CRM.

## Decision

1. **CRM raw state ≠ canonical commercial outcome.** Estado da fonte e interpretação
   canônica ficam em camadas separadas; o estado bruto nunca é sobrescrito.
2. **Outcome pertence ao Deal**, nunca à Call.
3. **Três entidades append-only** (D-M2): `OutcomeEvidence`, `EvidenceDisposition`,
   `OutcomeAssessment`. `Deal`, `StageEvent` e matching não mudam.
4. **`Deal.outcome` atual é projeção/estado legado do CRM**, não o outcome canônico (D-M1).
5. Status canônicos v0: **`won`, `rejected`, `open`, `unknown`**.
6. **FUTURE não é status**: é `open` + sinal `deferral` (D-M3).
7. **No-contact / fechamento por Salesbot não implica `rejected`.**
8. **`unknown` é estado legítimo**, não falha a esconder.
9. **Correção de evidência não apaga histórico** (`EvidenceDisposition`).
10. **Autoridade humana persiste** até outra decisão humana a substituir; a regra automática
    não a remove silenciosamente (D-M7).
11. **Override humano é uma decisão inteira e coerente**, nunca troca só o `status`.
12. **Refund/cancellation é sinal de reversão**, não `rejected`.
13. **Histórico de avaliações é linear**, com append por **CAS**; fork persistido = outcome
    canônico indisponível + reparo manual, sem escolha por timestamp (D-M8).
14. **Outcome registrado pode ficar indisponível para analytics** enquanto houver revisão
    pendente.
15. **Call só se liga a Outcome via resultado autoritativo atual do matching** (DEP-1).
16. **Conflito de identidade entre cards/Deal fica fora deste contrato** (DEP-2, D-M4).
17. **Objection resolution ≠ Deal outcome**: nenhuma dependência direta entre os dois.
18. **ADR antes da implementação** (D-M6); policy real só após validar D-G1/D-G2 (D-M5),
    com gate ampliado para D-G5/D-G6 (ver "Open business decisions").

## Canonical outcome semantics

| Status | Significado |
|---|---|
| `won` | a venda aconteceu (sustentado por evidência de venda) |
| `rejected` | o lead **decidiu** não comprar (sustentado por evidência de rejeição; nunca por automação/no-contact) |
| `open` | a oportunidade está comercialmente viva (engajamento ativo ou adiamento combinado) — **não** "o card está aberto" |
| `unknown` | a evidência não sustenta nenhum dos três |
| future / deferral | `open` com sinal `deferral`; não é status |

Detalhe e evidência mínima: proposal §4.

## Evidence and correction model

- **`OutcomeEvidence`**: uma observação de uma fonte, com estado bruto preservado e um sinal
  interpretado. Append-only; identidade da **observação**, não só do registro de origem.
- **`EvidenceDisposition`**: marca uma evidência como **invalidated** (não pertence ao Deal)
  ou **remapped/superseded** (sinal corrigido, com substituta). Nada é apagado.
- **Eligible** = evidências do Deal sem disposição; a policy só opera sobre esse conjunto.
- **Supporting** = subconjunto elegível que sustenta o status escolhido.

Detalhe: proposal §6–§7.

## Human authority

A decisão autoritativa de um Deal é a avaliação humana mais recente da cadeia; sem humano, é o
head. Avaliações automáticas posteriores ficam registradas como candidatos e podem pedir
revisão, mas não governam o outcome. Não há devolução automática de autoridade à regra no v0.
O outcome canônico é sempre um registro armazenado inteiro. Detalhe: proposal §8.3.

## Temporal / concurrency model

- Evidência, disposição e avaliação são append-only.
- Avaliações formam uma cadeia **linear** por Deal; cada escrita declara o head esperado
  (**CAS**); head divergente → conflito, recarregar e recomputar.
- Fork persistido → outcome indisponível, reparo manual; nenhum vencedor por timestamp.
- A regra de CAS está no contrato; a atomicidade real é do storage (TD-09).

Detalhe: proposal §9–§10.

## Reversal semantics

Refund/cancellation é um **modificador**, não uma classe de outcome: não vira `rejected`
automaticamente; em v0 leva a `unknown` + revisão humana (ou preserva a decisão humana vigente,
com revisão pendente). Estados `cancelled`/`refunded`/`churned` estão deferred (D-G5).
Detalhe: proposal §9.3.

## Call → Deal → Outcome boundary

DEP-1 está resolvido ([`CURRENT_MATCH_RESOLVER.md`](../domain/CURRENT_MATCH_RESOLVER.md)):

```
Call → resolve_current_match → state == "matched" → deal_id → Outcome
Call → resolve_current_match → qualquer outro state → sem linkage de Outcome por esta Call
```

MATCHED histórico ≠ match autoritativo atual. O Outcome Contract não resolve matching; opera
só sobre um Deal existente.

## Alternatives considered

| Alternativa | Por que foi rejeitada |
|---|---|
| Usar diretamente stage/status do CRM | a auditoria mostrou que o CRM erra justamente nos negativos; misturaria higiene de CRM com verdade comercial |
| Tratar Salesbot/no-contact como `rejected` | silêncio/automação não é decisão do lead; contaminaria qualquer análise de rejeição |
| FUTURE como status próprio | é sub-estado de uma oportunidade viva; exigiria regras de transição próprias sem ganho |
| Só outcome atual mutável | perde auditoria de reabertura, reembolso, correção e override |
| "Timestamp mais recente vence" | empates e relógios; mesma falha já corrigida no DEP-1 |
| Regra automática sobrescrevendo decisão humana | a revisão humana seria desfeita silenciosamente na próxima execução |
| Histórico com branching | complexidade de reconciliação sem necessidade no v0; fork vira indisponível |

## Consequences

### Positive

- Auditabilidade: toda decisão cita as evidências que a sustentam e o conjunto elegível
  usado; decisões automáticas citam também a versão da policy.
- Incerteza explícita (`unknown`, revisão) em vez de outcome forçado.
- Override humano seguro e persistente.
- Reprodutibilidade: mesma evidência elegível + mesma policy → mesma decisão.
- Analytics mais seguro: outcomes com revisão pendente não são consumidos.

### Negative

- Mais entidades (três) e um fluxo de decisão mais longo que um campo no Deal.
- Depende do resolver de matching (DEP-1) para ligar Calls a outcomes.
- Casos ambíguos e de reversão exigem revisão humana.
- Exige storage com CAS atômico (TD-09).
- Migração/backfill não é automática: histórico legado do CRM vira evidência, não outcome.

## Open business decisions (Gabriel)

Nenhuma bloqueia este ADR (design); quatro delas bloqueiam a implementação (ver abaixo).

| # | Pergunta |
|---|---|
| D-G1 | Mapeamento de sinais/fontes reais do CRM, distinguindo automação × pessoa |
| D-G2 | "Perdido" manual é confiável como rejeição? |
| D-G3 | Ghosting conta como perda em analytics? |
| D-G4 | "PROPOSTA FUTURA" é oportunidade viva ou perdida? |
| D-G5 | Que estado comercial representa refund/cancellation, e em qual janela? |
| D-G6 | "VENDA GANHA" sozinho basta para `won`? |
| D-G7 | Precisamos de data de retomada? |
| D-G8 | Regra de `stale_candidate` |

D-G1, D-G2, D-G5 e D-G6 **bloqueiam a implementação completa da policy real**. Isso amplia
D-M5 (que no proposal §19 cita só D-G1/D-G2): decisão de Matheus ao aceitar este ADR, porque
as recomendações provisórias do proposal para D-G5 (reversão → `unknown` + revisão) e D-G6
("VENDA GANHA" sozinho → `won` medium) definem a semântica de venda/reversão e precisam de
validação de negócio antes de virar código.

## Dependencies

- **DEP-1 — RESOLVED.** Resolver autoritativo do match Call↔Deal atual
  ([`CURRENT_MATCH_RESOLVER.md`](../domain/CURRENT_MATCH_RESOLVER.md)).
- **DEP-2 — OPEN.** Identidade/conflito entre cards do CRM e Deal canônico; task separada.
- **TD-09 / storage CAS — OPEN.** Atomicidade real do append linear no storage
  ([`TECH_DEBT.md`](../context/TECH_DEBT.md)).

## Deferred

`rejection_type`; `stale_candidate`; data de retomada (se necessária); estados
`cancelled`/`refunded`/`churned`; devolução automática de autoridade à regra; reconciliação
multi-parent; `reviewed_by`; receita realizada.

## Implementation gate

Implementar somente após:

- este ADR aceito;
- D-G1 e D-G2 respondidos;
- D-G5 e D-G6 esclarecidos para a semântica de venda/reversão;
- DEP-1 disponível (já resolvido);
- semântica de storage definida o suficiente para append linear com CAS.

## Validation

Nenhuma mudança de comportamento em runtime nesta branch; apenas documentação.

## Implementation status

Atualizado em 2026-09-29 na reconciliação de documentação. As seções acima (Context, Decision,
Alternatives, Consequences, Implementation gate) são o registro original da decisão e não foram
reescritas.

- **Structural core — implemented:** as três entidades append-only, elegibilidade, cadeia linear com
  CAS, autoridade humana e `resolve_current_outcome`.
- **Commercial-state composition — implemented:** Call → match atual → Deal → outcome atual, sem
  fallback para `Deal.outcome`.
- **Real-data validation — not done:** nenhum dado real de CRM foi processado.
- **Business/human policy decisions — open:** D-G1, D-G2, D-G5 e D-G6 (e D-G3/D-G4/D-G7/D-G8)
  continuam abertas; a policy comercial real não existe no código.

Evidência por parte:

| Parte | Status | Evidência |
|---|---|---|
| `OutcomeEvidence`, `EvidenceDisposition`, `OutcomeAssessment`, ids determinísticos, elegibilidade, cadeia linear com CAS, autoridade humana, `resolve_current_outcome` | IMPLEMENTED (núcleo estrutural, PR #19) | `src/closer_ai/domain/outcome.py`, `tests/unit/domain/test_outcome.py` |
| Call → match atual → Deal → outcome atual (sem fallback para `Deal.outcome`) | IMPLEMENTED (PR #20) | `src/closer_ai/domain/commercial_state.py`, `tests/unit/domain/test_commercial_state.py` |
| DEP-2 (identidade card ↔ Deal) | IMPLEMENTED como contrato estrutural (PR #21–#23) | [ADR-002](ADR_002-canonical-deal-identity.md) |
| Policy comercial real (sinais → status; proposal §7.3, §9.2–§9.4) | **NOT IMPLEMENTED** — segue bloqueada por D-G1, D-G2, D-G5, D-G6 | `outcome.py` docstring: assessments são construídos por um caller e só validados |
| Atomicidade real do CAS (storage) | **NOT IMPLEMENTED** — TD-09 | nenhuma camada de storage existe |
| Validação com dado real de CRM | **NOT DONE** | nenhum dado real processado |

ADR Accepted ≠ policy real validada ≠ produção validada.
