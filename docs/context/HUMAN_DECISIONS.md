# Human Decisions Required

Decisões que agents não podem tomar sozinhos — precisam de uma pessoa. Complementa
`docs/context/OPEN_QUESTIONS.md` (perguntas técnicas em aberto); este documento é
especificamente sobre decisões de dado real/onboarding que bloqueiam trabalho de agent até
serem resolvidas.

| Decision | Why it needs a human | Blocks |
|---|---|---|
| Autorização de uso das calls Agro/BeefPoint | Consentimento/contrato com o parceiro, não uma questão técnica | Todo processamento real do corpus Agro |
| Autorização de uso das calls Empreende Brazil | Idem | Todo processamento real do corpus Empreende |
| Autorização de uso do CRM (Kommo) | Idem — dado comercial e PII de terceiros | Toda ingestão Kommo real |
| Onde o dado real pode ser armazenado (fora do Git) | Decisão de infraestrutura/segurança da operação, não só do repositório | Definir se `data/raw/` local basta ou se precisa de um storage mais controlado |
| Se o dado bruto pode sair do ambiente do parceiro | Pode ser restrição contratual/legal do parceiro | Todo o fluxo de `docs/data/REAL_DATA_REQUEST.md` |
| Quem anota o Golden Set | Escolha de pessoas/processo, não código | `docs/evals/GOLDEN_SET_SAMPLING.md` — anotação real não pode começar sem anotadores definidos |
| Definição de negócio de WON/LOST | Semântica comercial da operação, não inferível do schema | `docs/domain/SALES_MODEL.md`, Outcome Intelligence |
| Significado real dos stages do Kommo | Só quem opera o CRM sabe o que cada stage representa na prática | `docs/data/KOMMO_DISCOVERY.md`, mapeamento para `Stage` |
| Quem adjudica matches ambíguos (`status='ambiguous'`/`manual_review`) | Processo humano de revisão, não uma regra que o matcher pode aplicar sozinho | Gate "MATCHING READY" (`docs/context/EXECUTION_GATES.md`) |
| Limiar mínimo de agreement entre anotadores | Decisão de qualidade aceitável, não um número que se deriva do código | Gate "GOLDEN SET READY" |
| Tamanho mínimo de amostra por categoria de objeção para reportar F1 | Decisão estatística de produto | Gate "EXTRACTOR V1 READY" |

## Regra

Nenhum agent (Domain Agent, AI Engineer, Evaluator, Reviewer, ou o Lead) decide qualquer item
desta lista sozinho. Quando um agent encontra uma dessas decisões pendente durante o trabalho,
o comportamento correto é parar e reportar o blocker (`AGENTS.md`), não assumir um valor
default.
