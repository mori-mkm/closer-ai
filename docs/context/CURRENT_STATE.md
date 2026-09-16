# Current State

_Atualizar somente quando o estado real do sistema mudar. Não é diário, não registra commits._

## Current phase

Bootstrap do repositório e do harness de colaboração humano + agents. Nenhuma funcionalidade
de produto implementada ainda.

## What works

- Estrutura de repositório, documentação em funil, política de branches/PR, `.gitignore`
  defensivo.

## In progress

- Nada em código ainda. Próximo passo real é o schema canônico de calls (ver "Next technical
  steps").

## Blockers

- Autorização formal de uso de dados reais (transcrições e exports de CRM) das empresas
  parceiras ainda não confirmada — enquanto isso, nenhum dado bruto entra no projeto.

## Recent decisions

- Sem banco de dados, storage, provedor de LLM ou arquitetura de matching definidos ainda —
  decisão adiada de propósito (evitar arquitetura prematura).
- Realtime Copilot (Cortex) adiado até validação analítica das fases anteriores.
- Push direto em `main` proibido a partir do bootstrap inicial; todo trabalho via PR.

## Next technical steps

1. Definir e implementar o schema canônico das calls (`normalization/`).
2. Definir Golden Set + taxonomia inicial de objeções/momentos.
3. Levantar viabilidade de matching Call ↔ Deal (com dado sintético/amostra, não corpus real).

## Corpus disponível (referência, não versionado)

- 108 calls Beefpoint/AgroTalento
- 35 calls Empreende Brazil
- Total: 143 transcrições reais — **nenhuma entra neste repositório**.
