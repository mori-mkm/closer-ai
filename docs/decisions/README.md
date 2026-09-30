# Architecture Decision Records

ADRs registram decisões arquiteturais **duráveis** e o porquê — não decisões triviais nem cada
implementação. O ADR guarda o **porquê** e as consequências; o contrato detalhado (**como**) fica no
doc de domínio/AI citado por ele.

## Index

| ADR | Title | Status | Summary |
|---|---|---|---|
| [ADR-001](ADR_001-outcome-contract-v0.md) | Canonical Outcome Contract v0 | Accepted | Estado bruto do CRM ≠ outcome comercial canônico; evidência/disposição/avaliação append-only; autoridade humana; `Deal.outcome` é projeção legada. Núcleo estrutural implementado; policy real bloqueada por D-G1/D-G2/D-G5/D-G6 |
| [ADR-002](ADR_002-canonical-deal-identity.md) | Canonical Deal Identity | Proposed (aguarda DI-M3: validação de Gabriel) | Source record do CRM ≠ Deal; ligação por decisão de identidade linear; só o self-link de fundação é automático |
| [ADR-003](ADR_003-authoritative-call-deal-matching.md) | Authoritative Call ↔ Deal Matching | Accepted | `CallDealMatch` = candidato; a relação atual vem só de `MatchDecision` + `resolve_current_match` |
| [ADR-004](ADR_004-real-data-privacy-boundary.md) | Real-Data Privacy and Storage Boundary | Accepted | Dado real nunca no Git; autorização explícita; perímetro local/OCI privado; artifacts privacy-first |
| [ADR-005](ADR_005-classification-provider-boundary.md) | Classification Provider Boundary | Accepted | Classifier → `ClassificationProvider` → implementação; Ollama local-only; sem reparo/retry |

ADR-003, ADR-004 e ADR-005 foram aceitos formalmente na reconciliação de 2026-09-29 (as decisões já
governavam a implementação). ADR-002 continua Proposed: DI-M3 exige validação de Gabriel e DI-G1–G4
estão abertas. **ADR Accepted ≠ produção validada:** os blockers humanos e de dado real continuam
registrados em cada ADR e em [`CURRENT_STATE.md`](../context/CURRENT_STATE.md).

## Quando criar uma ADR

Crie uma ADR quando a mudança introduz ou altera, de forma durável:

- identidade canônica (o que é "o mesmo" Deal, Call, pessoa);
- regra de autoridade (quem/qual registro decide o estado atual);
- contrato entre módulos (o que um módulo pode assumir do outro);
- fronteira de provider (LLM, CRM, transcrição, storage);
- decisão de storage persistente;
- política de privacidade/segurança de dado;
- decisão de infraestrutura cara ou difícil de reverter;
- arquitetura de realtime.

## Quando NÃO criar

Decisão local, reversível, sem impacto em outro módulo: nome de função, lib de teste, formatação,
parâmetros de um componente experimental. Braços experimentais (E0/E1/E2), o Context Builder e o
Experiment Runner são documentados em `docs/ai/`, não em ADR, enquanto forem experimento. Se um
deles virar arquitetura de produto, aí sim cabe uma ADR.

## Como criar

1. Copie [`ADR_TEMPLATE.md`](ADR_TEMPLATE.md) para `ADR_NNN-titulo-curto.md`, com o próximo número.
2. Status inicial `Proposed`; só um humano muda para `Accepted`.
3. Adicione a linha no índice acima.
4. No PR, responda à seção "Architecture decision impact" do template
   (`.github/pull_request_template.md`).
5. Quando a implementação chegar depois, atualize só a seção "Implementation status". Não reescreva
   o contexto nem a decisão original.
