# Open Questions

Perguntas em aberto que afetam decisão técnica futura. Quando respondida, mover a resposta
para o documento relevante (`CURRENT_STATE.md`, uma ADR, ou doc de domínio) e remover daqui.
Reconciliado em 2026-09-18 — perguntas já respondidas pelo trabalho de PR #1-#6 foram
removidas (cardinalidade Call↔Deal, Stage vs. Outcome, forma dos IDs determinísticos).

## DATA ACCESS

- Onde estão as 108 calls Agro/BeefPoint hoje (Drive, storage do parceiro, outro lugar)? Quem
  tem acesso?
- Onde estão as 35 calls Empreende Brazil?
- Como vamos obter export ou acesso de API do Kommo (credencial, escopo, quem solicita)?
- Autorização formal de uso de transcrições e dados de CRM das empresas parceiras: qual o
  formato e prazo esperado? (Já era pergunta aberta no bootstrap; segue sem resposta
  confirmada nesta sessão.)

## SOURCE FORMAT

- Formato real do export Zoom/Agro: JSON de API, `.vtt`/`.srt`, ou outro? (`AgroRawCall` é
  hipótese, não confirmado — `docs/domain/AGRO_INGESTION_CONTRACT.md`.)
- Unidade real de `duration_seconds` — a API do Zoom costuma retornar em minutos; o parser
  assume segundos sem conversão.
- Formato exato de cada entrada de transcript (`speaker`/`start`/`end`/`text` é a hipótese
  atual).
- Existe um id estável de participante na fonte real (Zoom participant UUID, email), ou
  identidade via nome normalizado é o único sinal disponível? Isso define se
  `participant_id_collision` continua sendo uma limitação estrutural ou pode ser resolvida.

## CRM

- Formato real do payload Kommo (API v4 vs. webhook vs. export CSV)?
- Quais pipelines/estágios existem de fato na operação Agro? Como mapeiam para o `Stage`
  genérico já modelado (`created`/`qualification`/`proposal`/`negotiation`/`other`)?
- Quais loss reasons o Kommo registra, e isso deve virar campo estruturado em `Deal` ou ficar
  em `metadata`?
- Histórico de `StageEvent` está disponível via API/export, ou só o estado atual (`current_stage`)?

## MATCHING

- Além de `external_id` (já suportado por `ExactExternalIdMatcher`), quais identificadores
  estarão de fato disponíveis para ligar Call↔Deal (email do lead na call, telefone,
  proximidade nome+data)? `Participant` hoje não carrega email/telefone.
- Confiabilidade real de cada sinal (email/telefone/nome) nesta operação — depende de como o
  Kommo e o Zoom preenchem esses campos na prática.
- Workflow de validação manual para `status='manual_review'`/`'ambiguous'`: quem revisa, com
  que ferramenta?
- Calibração score→`confidence_level` para métodos heurísticos futuros (hoje só existe o
  método determinístico `exact_external_id`).

## AI / GOLDEN SET

- Taxonomia de objeção v1 (além das 4 categorias fechadas do v0): quais categorias adicionais
  o negócio realmente precisa?
- Regras de anotação para o Golden Set real — critério de "o que conta como objeção",
  granularidade de evidência (segmento único ainda basta, ou surge caso de objeção
  multi-segmento?).
- Quantas calls entram no Golden Set real (roadmap assume 20-30) e como a amostragem é
  representativa (por operação, por estágio, por closer)?
- Quem são os anotadores e como funciona adjudicação de discordância?

## AI / GOLDEN SET (continuação)

- `ObjectionEvent` não carrega nenhum campo de resolução (a objeção foi superada antes do
  fechamento do deal, ou não?) — deferido de propósito no contrato v0
  (`src/closer_ai/domain/objection.py`), mas essa lacuna não está referenciada em
  `docs/context/DATA_DEPENDENCIES.md`/`EXECUTION_GATES.md`. Outcome Intelligence vai precisar
  derivar isso de outro lugar (ex.: timing do segmento vs. `StageEvent.occurred_at`) ou de um
  campo futuro — decisão de produto ainda não tomada.

## PRODUCT

- Definição exata de "outcome" para fins de Outcome Intelligence: ganho/perdido é suficiente,
  ou entram métricas intermediárias (ciclo, número de calls até fechar)? (Pergunta do
  bootstrap, ainda sem resposta confirmada — ver `docs/domain/SALES_MODEL.md`.)
- Quais workflows de gestor (manager) o produto precisa suportar primeiro, uma vez que houver
  dado real para mostrar?
- Quais dashboards são realmente necessários no MVP, versus especulação prematura?
- Existe feedback de design partner já coletado que deveria influenciar a Fase "Call
  Intelligence" além do v0 de objeções?

## INFRA

- Branch protection / required status checks no GitHub: configurado de fato? Não verificável
  localmente nesta sessão (sem `gh auth login`) — checar manualmente em Settings → Branches e
  atualizar `docs/context/CURRENT_STATE.md`.
- Provedor de LLM: qual abstração mínima é necessária antes de escolher, e quando essa escolha
  se torna urgente o bastante para virar ADR? (Ainda em aberto — nenhum extractor LLM-backed
  existe; `RuleBasedObjectionExtractor` é 100% determinístico.)
