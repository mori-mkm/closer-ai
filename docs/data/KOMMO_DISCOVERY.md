# Kommo Discovery Protocol

Protocolo de primeira exploração do CRM Kommo quando a amostra (`docs/data/REAL_DATA_REQUEST.md`
Package C) chegar. Não implementa API — é um roteiro de perguntas a responder contra o payload
real, separando **forma da API** (o que o campo se chama, que tipo é) de **semântica de
negócio** (o que o valor significa). `status_id = 142` não diz nada sozinho — precisamos saber
o que esse número representa na operação real antes de mapear para `Deal`/`StageEvent`.

## O que descobrir

1. **Entities disponíveis** — quais objetos a amostra/API expõe (leads, contacts, companies,
   deals/tasks, notes, activities)? Kommo distingue "leads" de "contacts" de forma específica —
   confirmar como isso mapeia para `Lead`/`Deal` deste codebase (não assumir 1:1).
2. **Deal/lead/contact relation** — um deal tem um contato só, ou vários? Um contato pode ter
   vários deals?
3. **Pipelines** — quantos pipelines existem na conta real? Um só, ou um por tipo de produto/
   funil?
4. **Stages** — lista real de stages por pipeline, com o id interno do Kommo e o nome exibido.
   Ver "Business semantics" abaixo antes de mapear para o `Stage` genérico
   (`created`/`qualification`/`proposal`/`negotiation`/`other`,
   `src/closer_ai/domain/deal.py`).
5. **Closed status** — como o Kommo representa "fechado"? Um pipeline_stage_id especial, ou um
   campo `status` separado do stage (nossa hipótese em `DEAL_MODEL.md`, a confirmar)?
6. **Loss reasons** — existe um campo estruturado de motivo de perda, ou é texto livre em nota?
7. **Stage history** — a API/export retorna histórico de mudanças de stage, ou só o estado
   atual? Isso é crítico — sem histórico real, `StageEvent` só pode ser populado com um evento
   sintético no momento da ingestão, não o histórico real.
8. **Responsible user** — como o "dono" do deal é identificado (id numérico, nome, email)?
   Mapeia para `Deal.owner_id`.
9. **Custom fields** — quais campos customizados a operação usa? Podem conter dado relevante
   (ex.: origem do lead) ou PII adicional.
10. **Activities/notes** — formato de notas e atividades — texto livre? Estruturado? Provável
    fonte de PII (nomes, telefones em texto).
11. **Meeting/call references** — existe algum campo ou atividade que referencia uma call
    específica (id de reunião, link de gravação, nota mencionando a call)? Este é o sinal mais
    valioso para matching Call↔Deal, se existir — ver `docs/data/DATA_ACCESS_MATRIX.md`.
12. **Timestamps** — formato (epoch, ISO 8601), e quais eventos têm timestamp (`created_at`,
    `updated_at`, mudança de stage, fechamento)?
13. **Timezone** — os timestamps vêm em UTC, horário local, ou sem timezone explícito?
    `Deal.created_at`/`closed_at`/`StageEvent.occurred_at` exigem tz-aware.
14. **Pagination** — se via API, como a paginação funciona (cursor, offset, limite por
    página)? Relevante só para quando o volume real for maior que a amostra.
15. **Deletion/archive semantics** — deals podem ser arquivados/excluídos? Isso afeta se um
    "deal sumido" é uma exclusão real ou um filtro de visualização.

## Business semantics vs. API shape

Separar explicitamente as duas colunas ao documentar achados:

| Campo/valor da API | API shape (o que é) | Business semantics (o que significa) |
|---|---|---|
| `status_id` (exemplo) | inteiro | preencher só depois de confirmar com o parceiro o que cada valor real representa |
| `pipeline_id` | inteiro | qual funil de negócio isso é (ex.: "vendas novas" vs. "renovação") |
| stage dentro de um pipeline | inteiro/string | em que ponto do processo comercial isso corresponde |

Nunca inferir semântica de negócio só pelo nome do campo da API — confirmar com Product/RevOps
ou com quem opera o CRM no dia a dia.

## Saída esperada

Um documento de achados (não código) descrevendo: entities/relations reais, lista de
pipelines/stages com semântica confirmada, formato de loss reason, disponibilidade real de
stage history, e uma primeira proposta de mapeamento Kommo → `Lead`/`Deal`/`StageEvent` — sem
implementar o adapter ainda. Esse documento alimenta o gate "CRM SEMANTICS VALIDATED"
(`docs/context/EXECUTION_GATES.md`).
