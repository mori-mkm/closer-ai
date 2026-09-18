# Execution Gates

Definition of Done objetiva por camada. Existe para impedir a armadilha de "feature pronta
porque o código passa nos testes sintéticos" — cada gate abaixo exige evidência contra dado
real ou processo real, não só cobertura de teste. Nenhum gate abaixo está fechado hoje
(2026-09-18); ver `docs/context/CURRENT_STATE.md` para o que já está implementado no nível de
código.

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
