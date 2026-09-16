# Integrations (inventário, sem implementação)

Lista de sistemas externos relevantes ao domínio, para orientar `src/closer_ai/integrations/`
quando a implementação real começar. Nenhuma integração está implementada nesta fase.

## CRM

- Kommo (API v4 + webhook) — usado por uma das operações do corpus.
- Pipedrive — usado pela outra operação do corpus.

## Mensageria

- WhatsApp (via CRM/webhook) — canal principal de contato com lead.

## Transcrição

- Fonte de transcrição a definir — não decidir provedor aqui, isso é ADR quando a fase de
  ingestão começar.

## Princípio

Toda integração deve ser abstraída atrás de uma interface em `domain/` ou `integrations/`,
para que trocar de provedor (CRM, LLM, storage) não exija reescrever `ai/` ou `analytics/`.
Não implementar a abstração antes de haver uma segunda integração real que a justifique.
