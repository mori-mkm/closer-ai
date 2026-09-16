# Architecture Decision Records

ADRs registram decisões arquiteturais importantes e por quê — não decisões triviais.

## Quando criar uma ADR

- Escolha de banco/storage.
- Arquitetura de matching Call ↔ Deal.
- Abstração de provedor de LLM.
- Arquitetura de realtime.
- Contratos principais entre módulos.
- Qualquer decisão de segurança/privacidade de dado.

## Quando NÃO criar

Decisão local, reversível, sem impacto em outro módulo (nome de função, escolha de lib de
teste, formatação). Isso é code review normal, não ADR.

## Como criar

Copie [`ADR_TEMPLATE.md`](ADR_TEMPLATE.md) para `ADR_NNN-titulo-curto.md` neste diretório,
usando o próximo número sequencial.
