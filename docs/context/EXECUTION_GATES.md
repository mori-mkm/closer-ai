# Execution Gates

Definition of Done objetiva por camada. Existe para impedir a armadilha de "feature pronta
porque o código passa nos testes sintéticos" — cada gate abaixo exige evidência contra dado
real ou processo real, não só cobertura de teste. Nenhum gate abaixo está fechado hoje
(2026-09-18); ver `docs/context/CURRENT_STATE.md` para o que já está implementado no nível de
código.

## Data acceptance gates (onboarding sequence)

Gates finos que precedem os gates de camada abaixo — a ordem em que os dados reais devem
avançar, do primeiro contato até virar insumo de contrato. Cada linha tem evidência exigida,
se precisa de aprovação humana, e se um agent consegue verificar sozinho.

| Gate | Required evidence | Human approval? | Agent-verifiable? | Output artifact |
|---|---|---|---|---|
| DATASET RECEIVED | Arquivos presentes em `data/raw/<fonte>/`, fora do Git | Não | Sim (checar existência do arquivo local) | Nenhum — é um estado, não um documento |
| DATASET AUTHORIZED | Confirmação registrada de que o uso do dado foi autorizado pelo parceiro | Sim — é a decisão em `docs/context/HUMAN_DECISIONS.md` | Não | Entrada atualizada em `docs/context/OPEN_QUESTIONS.md`/`HUMAN_DECISIONS.md` |
| SOURCE FORMAT UNDERSTOOD | `docs/data/SOURCE_CONTRACT_DIFF_TEMPLATE.md` preenchido para os campos relevantes | Não (revisão opcional) | Sim, uma vez que o dado exista localmente | Diff preenchido + `docs/domain/AGRO_INGESTION_CONTRACT.md` atualizado |
| 5-CALL VALIDATION PASSED | `docs/data/FIRST_CALLS_VALIDATION.md` executado até o passo 20 (quality report), incluindo a confirmação crítica do passo 13 (resolução de `role="lead"` ponta a ponta — sem isso o extractor produz zero objeções silenciosamente) | Sim, passo 21 (review before batch) | Passos 1-20 sim; passo 21 não | Quality report (`docs/data/DATA_QUALITY_REPORT.md`, seção Calls) |
| CRM SEMANTICS VALIDATED | `docs/data/KOMMO_DISCOVERY.md` executado, semântica de stage/outcome confirmada com o negócio | Sim — semântica de negócio não é inferível pelo agent | Só a parte de shape da API; semântica não | Documento de achados do Kommo Discovery |
| MATCHING SIGNALS IDENTIFIED | `docs/data/DATA_ACCESS_MATRIX.md` (tabela de sinais) atualizada com "currently available" real, não mais "unknown until sample" | Não | Sim, uma vez que Agro+Kommo estejam validados | `DATA_ACCESS_MATRIX.md` atualizado |
| GOLDEN SET READY | Ver seção própria abaixo | Sim | Parcial — só a contagem de calls selecionadas e o cálculo do número de agreement são mecânicos; escolha de anotadores, limiar de agreement aceitável, dupla anotação e adjudicação são decisões/trabalho humano (`docs/context/HUMAN_DECISIONS.md`) | `evals/objection_v0/` real (fora do escopo desta task) |

## AGRO REAL READY

- [ ] Formato de origem documentado a partir de uma amostra real (não mais hipótese)
- [ ] 5 calls reais processadas com sucesso pelo pipeline (`parse_agro_call` + `normalize_call`)
- [ ] Nenhum dado bruto commitado no repositório
- [ ] Relatório de qualidade produzido (distribuição de `quality_flags` nas 5 calls reais)
- [ ] Premissas do parser reconciliadas contra o formato real: unidade de `duration_seconds`,
      shape do transcript, disponibilidade de id estável de participante
      (`docs/domain/AGRO_INGESTION_CONTRACT.md` atualizado com achados reais, não mais só
      hipóteses)

## CRM READY

- [ ] Amostra de export/API disponível (Kommo)
- [ ] Campos de `Lead`/`Deal` mapeados do payload real para o contrato existente
      (`src/closer_ai/domain/lead.py`, `deal.py`)
- [ ] Estágios (`Stage`) mapeados do pipeline real para o enum genérico atual
      (`created`/`qualification`/`proposal`/`negotiation`/`other`)
- [ ] Semântica de outcome validada com o negócio (o que conta como `won`/`lost`, loss reasons)
- [ ] Nenhum PII em Git (export real fica fora do repositório, mesmo em fixtures)

## MATCHING READY

- [ ] Geração de candidatos rodando contra Deals/Calls reais
- [ ] Ambiguidade preservada (múltiplas linhas `CallDealMatch(status='ambiguous')`, nunca um
      vencedor escolhido silenciosamente — já é invariante do schema, falta rodar contra dado real)
- [ ] Amostra de revisão humana definida (quantas linhas `manual_review`/`ambiguous` um humano
      revisa antes de confiar no matcher)
- [ ] Qualidade do match medida (taxa de match/ambíguo/não-encontrado na amostra real)

## GOLDEN SET READY

- [ ] 20-30 calls reais selecionadas
- [ ] Amostragem representativa (por operação, estágio, closer — critério definido antes da
      seleção, não depois)
- [ ] Regras de anotação (output da task B1 em `docs/context/NEXT_7_DAYS.md`) cobrem
      explicitamente os casos-limite já identificados no golden set sintético (frase ambígua,
      objeção partida entre segmentos, closer citando o lead) — sem isso, dois anotadores reais
      tendem a divergir justo nesses casos
- [ ] Dupla anotação (dois anotadores independentes por call)
- [ ] Processo de adjudicação de discordância definido e executado
- [ ] Agreement entre anotadores calculado e reportado, com um limiar mínimo aceitável definido
      antes da anotação (não só "calculado e reportado" sem barra de corte)

## EXTRACTOR V1 READY

- [ ] Avaliado contra o Golden Set real (não o sintético atual)
- [ ] Precision/recall/F1 reportados por categoria, com um tamanho mínimo de amostra por
      categoria definido antes da avaliação (categorias raras podem ter poucos exemplos reais
      em 20-30 calls; um resultado por-categoria sem esse piso não é confiável)
- [ ] Grounding medido (evidência `(call_id, segment_id)` resolve para segmento real,
      falado por participante `role="lead"`) — mesma métrica já usada em `evals/objection_v0`,
      agora contra dado real
- [ ] Taxonomia de erro construída (falsos positivos/negativos categorizados, não só contados)
- [ ] Versão do extractor congelada (`schema_version`/tag) antes de virar baseline de produto

## OUTCOME INTELLIGENCE READY

- [ ] Outcomes finalizados (deals fechados, não `open`/`unknown`, na amostra analisada)
- [ ] Join Deal-level completo (`Deal` + `CallDealMatch(matched)` + `ObjectionEvent[]` das
      calls associadas)
- [ ] Amostra suficiente de won/lost para qualquer conclusão estatística (tamanho mínimo a
      definir com Product/RevOps antes da análise, não depois)
- [ ] Deals `open`/`stale` separados explicitamente dos fechados na análise — nunca misturados
      como se fossem "não convertidos"
- [ ] Nenhuma alegação causal a partir de dado observacional — correlação reportada como
      correlação, sem linguagem de causalidade

## BATCH READINESS (antes de processar as 108/35 calls reais)

Checklist antes de rodar o corpus completo — mesmo em execução manual, não só pipeline
automatizado:

- [ ] Autorização confirmada (`docs/context/HUMAN_DECISIONS.md`)
- [ ] Contrato de origem validado (gate SOURCE FORMAT UNDERSTOOD acima)
- [ ] 5 calls passaram na validação (gate 5-CALL VALIDATION PASSED acima)
- [ ] Distribuição de `quality_flags` das 5 calls revisada e aceitável
- [ ] IDs determinísticos verificados (mesmo input produz mesmo `call_id`/`segment_id` — checar
      re-execução idempotente antes do batch)
- [ ] Caminho de dado bruto está no `.gitignore` (`data/raw/**`)
- [ ] Nenhum log/exceção do pipeline imprime PII (mensagens de erro citam só `meeting_id`,
      nunca conteúdo de transcript — ver convenção já em `parse_agro_call()`)
- [ ] Output vai para caminho privado (`data/interim/`/`data/processed/private/`), nunca
      staged para commit
- [ ] Rollback/re-execução é seguro (rodar o batch de novo não duplica nem corrompe nada —
      decorre dos IDs determinísticos, mas confirmar antes)
- [ ] Relatório de qualidade pronto para ser gerado ao final do batch (`docs/data/DATA_QUALITY_REPORT.md`)
