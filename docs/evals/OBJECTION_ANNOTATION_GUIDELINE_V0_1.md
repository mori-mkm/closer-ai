# Objection Annotation Guideline v0.1

Status: **DRAFT — pré-pilot.** Substitui a [v0](OBJECTION_ANNOTATION_GUIDELINE_V0.md) para o pilot D3;
a v0 fica como registro histórico. Nenhum dado real anotado. TAX, D3, D6 e D7 continuam **abertas**.
Todos os exemplos são sintéticos.

> **Classify what the transcript supports, not what probably happened.**

```
evidence (segment_id) → observation (o que foi dito) → classification → optional interpretation (nota INFERIDO)
```

Nunca `interpretation → retroactive fact`. Conhecimento externo (Knowledge Base, frameworks, pesquisa)
**define e explica**; só `segment_id`s da Call **provam ocorrência**.

## Purpose

Instruções operacionais para um humano decidir o que anotar em uma Call para `ObjectionEpisode`, de
modo que duas pessoas cheguem a decisões comparáveis sem adivinhar intenção. Serve ao pilot D3, ao
Golden Set v1 e à futura avaliação de extractors (braços E0/E1/E2 da
[proposta de RAG](../ai/SALES_KNOWLEDGE_RETRIEVAL_RAG_V0_1_PROPOSAL.md)).

Como construir o Golden Set (dupla anotação, adjudicação, versões, métricas):
[`GOLDEN_SET_ANNOTATION_PROTOCOL_V1.md`](GOLDEN_SET_ANNOTATION_PROTOCOL_V1.md) — não repetido aqui.
O que cada categoria **significa** em detalhe: [`docs/knowledge/sales/objections/`](../knowledge/sales/objections/)
(fonte normativa de conhecimento). Esta guideline define **como anotar**.

## Authority and decisions

Ordem: contrato [`ObjectionEpisode`](../domain/OBJECTION_EPISODE_V1_PROPOSAL.md) → protocolo → decisões
humanas registradas → [taxonomy proposal](../domain/CALL_INTELLIGENCE_TAXONOMY_V0_1_PROPOSAL.md) →
Knowledge Base → esta guideline. Em divergência, vale o de cima; registre como dúvida do pilot.

**CIT-O1 — APPROVED (Matheus, 2026-09-28).** O pilot D3 e o Golden Set v1 usam o **label set
experimental** das 8 categorias provisórias + `OTHER`, com os status UNKNOWN e AMBIGUOUS.

> **Annotation label set ≠ domain enum.** O enum do domínio (`price`, `timing_priority`,
> `trust_authority`, `no_need`, `other`), `ObjectionEpisode.category` e `ObjectionEvent` v0 **não
> mudam**. Qualquer mudança de enum, schema ou contrato continua bloqueada por evidência do pilot + **D7**.

## Relationship to ObjectionEpisode

Por episódio o anotador produz os campos do contrato — `category` (aqui: label da v0.1),
`objection_segment_ids` (o primeiro é a âncora), `context_segment_ids`, `resolution_status` — e os
metadados de revisão do protocolo (status do rótulo, notas observado/inferido, ponteiro de justificativa
opcional). Não há campo novo. Resistance type, hesitação, brush-off, tipo de handling e tipo de reação
**não** são campos.

## Sales resistance vs objection

**Sales resistance** (conceito de guideline, não entidade) é qualquer sinal do lead de oposição,
dificuldade, dúvida ou falta de disposição para avançar. **Objection** é o subconjunto que satisfaz a
definição operacional abaixo. O anotador pergunta, nessa ordem:

1. Há algum sinal de resistência?
2. Esse sinal satisfaz a definição operacional de objection?

Só (2) = sim abre `ObjectionEpisode`. **Não** são objection automaticamente:

| Fenômeno | Exemplo sintético | Tratamento |
|---|---|---|
| Pergunta / pedido de informação | "Quanto sai a licença anual?" | NO_OBJECTION |
| Preocupação neutra (sem função impeditiva) | "Tenho um pouco de receio com a migração." | NO_OBJECTION, ou AMBIGUOUS se o contexto sustentar leitura de barreira |
| Comentário neutro | "Hoje usamos planilha para isso." | NO_OBJECTION |
| Hesitação | "Não sei… preciso pensar." | ver Hesitation |
| Brush-off | "Me manda por e-mail que eu te procuro." | ver Brush-off |
| Processo normal de decisão | "Quem assina é a diretoria." | NO_OBJECTION |
| Menção a stakeholder | "Vou mostrar para o meu sócio." | NO_OBJECTION |
| Etapa normal de compras | "Nosso jurídico vai revisar o contrato." | NO_OBJECTION |

## What is an objection?

Uma barreira, preocupação, restrição ou condição **suficientemente explícita** que funciona como
**resistência ao avanço comercial**. Exige evidência observável. Uma objection requer:

- **A. Atribuível ao lead:** dita por um participante com `role="lead"`, com as próprias palavras
  (closer, `other` e `unknown` nunca abrem episódio; resistência só relatada de terceiro não conta — GL-1).
- **B. Relevante nesta call:** posição atual, não lembrança superada nem hipótese.
- **C. Barreira identificável:** dá para dizer **o que** está sendo resistido.
- **D. Afeta o avanço:** o dito liga essa barreira a não avançar, adiar ou condicionar a decisão.

Não bastam: tópico aparecer; interpretação do closer; Outcome posterior; CRM; tom ou sentimento
presumido; ausência de resposta; palavra-chave. Sem fórmula: se A–D não estão todos sustentados pelo
dito, não é PRESENT (ver UNKNOWN vs AMBIGUOUS e NO_OBJECTION).

## Topic ≠ objection

| Tópico mencionado | ≠ | Categoria |
|---|---|---|
| preço | ≠ | `PRICE_BUDGET` |
| stakeholder | ≠ | `AUTHORITY_INTERNAL_BUY_IN` |
| concorrente | ≠ | `COMPETITION_EXISTING_SOLUTION` |
| integração/implantação | ≠ | `IMPLEMENTATION_INTEGRATION` |
| prazo/momento | ≠ | `TIMING_PRIORITY` |
| compras/jurídico/contrato | ≠ | `TERMS_PROCESS` |

"Quanto custa?" não é PRICE_BUDGET. "Vou conversar com meu sócio." não é AUTHORITY_INTERNAL_BUY_IN.
"Também estamos avaliando X." não é COMPETITION_EXISTING_SOLUTION. Signals are contextual cues, not
keyword classifiers.

## Hesitation

Incerteza ou indecisão **sem barreira dita** ("Não sei… preciso pensar.", "Vou ver.").

- Hesitação sozinha **não fornece categoria**. Não inferir TIMING, PRICE, AUTHORITY ou qualquer outra.
- Se no mesmo contexto o lead **diz** a barreira ("preciso pensar, porque o valor passou do que temos"),
  anote a barreira (teste A–D), não a hesitação.
- Sem barreira dita: **não** crie episódio. Se o material sustenta duas leituras plausíveis (objeção sem
  categoria dita × adiamento neutro), marque **AMBIGUOUS** na detecção (GL-2).
- Dentro de um episódio já aberto, "vou pensar" é resposta do objetor e segue as regras de resolução.

## Brush-off

Tentativa de encerrar, adiar ou afastar a conversa **sem barreira concreta** ("Me manda por e-mail e
qualquer coisa eu te procuro.").

- Brush-off genérico: **não** é TIMING_PRIORITY. Sem barreira dita → NO_OBJECTION ou AMBIGUOUS (mesma
  regra da hesitação). Nunca registre "é desculpa" como fato.
- Com motivo concreto dito, anote o motivo: "Me procure em janeiro, porque nosso orçamento só reabre
  dia 2." tem barreira observável de **verba ligada a data** → `PRICE_BUDGET` ou `TIMING_PRIORITY`
  conforme o que o contexto mostra ser resistido; se nada decide, **AMBIGUOUS {PRICE_BUDGET,
  TIMING_PRIORITY}** (fronteira em aberto na KB).
- Não há regra lexical para separar brush-off de timing.

## NO_OBJECTION

Para um trecho candidato (revisão de trecho, rótulos negativos, eval), o resultado pode ser
**NO_OBJECTION**: o trecho foi examinado e **não** é episódio. Não cria `ObjectionEpisode` e não é campo
de schema; é o rótulo negativo "por trecho" já previsto no protocolo (Negative gold). Casos comuns:
pergunta neutra, comentário neutro, pedido de informação, resposta de discovery, descrição de processo,
menção a stakeholder, menção a concorrente, preocupação sem função impeditiva, fala do closer.

Call inteira sem episódios = **ABSENT** call-level (exige revisão completa, protocolo).

## Evidence rules

- Evidência = **`segment_id`s** da Call (contrato §7). Sem trechos de caracteres, sem quote livre como
  verdade, sem timestamps anotados.
- `objection_segment_ids`: segmentos do objetor necessários para entender a objeção (âncora +
  continuação). `context_segment_ids`: os demais necessários para entender o episódio (closer
  respondendo, reações do objetor, falas de terceiros sobre o tema). Uma fala entra em **uma** lista por
  episódio.
- **Forte:** o objetor diz a barreira diretamente — pode sustentar PRESENT sozinha. **Fraca:** só sugere
  ("Vou pensar", "Hmm, entendi") — não sustenta PRESENT sozinha.
- Speaker `unknown` não pode ser âncora (TD-14); não corrija speaker nem papel na anotação.
- **Knowledge Base, frameworks e pesquisa nunca são evidência.** Uma anotação nunca cita knowledge unit
  como prova; aponta `segment_id`s.

## Observed vs inferred

Só o **dito** vira evidência ou valor de campo. Inferência vai para nota marcada "INFERIDO". Se a
inferência é necessária para decidir a categoria, a categoria é UNKNOWN ou AMBIGUOUS.

Exemplo — "Preciso falar com meu sócio.":

| Observado | Não observado (nunca vira campo) |
|---|---|
| existe outro stakeholder; o lead pretende consultá-lo | o lead não tem autoridade; o sócio é o economic buyer; o sócio vai recusar; o lead está usando o sócio como desculpa |

Outros: "Já tivemos problema com outra plataforma." → observado: experiência negativa anterior; não
observado: "não confia no fornecedor atual". "Esse valor aperta o caixa este mês." → observado: aperto
no mês; não observado: "não tem orçamento nenhum".

## Category label set v0.1

Label set experimental (CIT-O1). Detalhe normativo em
[`docs/knowledge/sales/objections/`](../knowledge/sales/objections/); aqui só o necessário para anotar.
Todos PROVISIONAL.

Regras gerais:

- Categorize pelo **que está sendo resistido**, segundo o dito.
- Uma categoria por episódio. Duas barreiras claras de categorias diferentes → dois episódios.
- Dúvida entre categorias → AMBIGUOUS {candidatas}; sem base → UNKNOWN. Nunca "a mais provável".

### PRICE_BUDGET

- **Definition:** o montante, a verba ou a capacidade de pagar funciona como barreira dita.
- **Use when:** preço declarado excessivo para avançar; sem verba; não consegue pagar.
- **Do not use when:** só pergunta preço; barreira dita é retorno/valor (→ NEED_VALUE_FIT); estrutura
  contratual (→ TERMS_PROCESS); preço passado/hipotético.
- **Minimum evidence:** fala do lead ligando custo/verba à dificuldade de avançar.
- **Often confused with:** NEED_VALUE_FIT, TIMING_PRIORITY (ciclo de verba), TERMS_PROCESS (forma de
  pagamento).
- **Positive:** "Gostei, mas não temos verba para isso neste ano." · **Counter:** "Qual é o preço do
  plano básico?"
- **Main inference risk:** ler "não pode pagar" onde só foi dito "é caro".
- **Diagnostic:** o custo/verba está funcionando como barreira ou só sendo discutido?

### TIMING_PRIORITY

- **Definition:** momento ou prioridade atual, com motivo dito, impede ou adia o avanço.
- **Use when:** "outro projeto vem antes", "só no plano do ano que vem", "não é prioridade agora" ligado
  a não seguir.
- **Do not use when:** brush-off sem motivo; verba ligada a data (fronteira com PRICE_BUDGET);
  agendamento normal ("queremos começar em março"); esforço/duração da implantação
  (→ IMPLEMENTATION_INTEGRATION).
- **Minimum evidence:** fala ligando momento/prioridade ao adiamento, com o motivo.
- **Often confused with:** brush-off, PRICE_BUDGET, IMPLEMENTATION_INTEGRATION, TERMS_PROCESS.
- **Positive:** "Este trimestre a equipe inteira está no fechamento contábil; projeto novo só depois." ·
  **Counter:** "Talvez mais para frente." (sem motivo → AMBIGUOUS, não TIMING forçado)
- **Main inference risk:** transformar adiamento vago em timing "com baixa confiança" (não existe
  `confidence`; use AMBIGUOUS).
- **Diagnostic:** há um motivo de momento/prioridade **dito**? A barreira é o momento da compra ou o
  esforço de implantar?

### NEED_VALUE_FIT

**AI CLOSER PROVISIONAL ABSTRACTION** — Need + Value + Fit fundidos por parcimônia; não é consenso nas
fontes. A fusão é avaliada no pilot (registre em nota qual sub-conceito você leu: need, value ou fit).

- **Definition:** o lead diz que não precisa, que o benefício não compensa ou que a solução não serve.
- **Use when:** negação explícita de necessidade, valor ou adequação, ligada a não avançar.
- **Do not use when:** reconhece valor mas não pode pagar (→ PRICE_BUDGET); esforço de implantar
  (→ IMPLEMENTATION_INTEGRATION); receio de dar errado (→ TRUST_RISK); descreve uma necessidade
  (discovery).
- **Minimum evidence:** negação dita de necessidade/utilidade/benefício/adequação.
- **Often confused with:** PRICE_BUDGET, IMPLEMENTATION_INTEGRATION, TRUST_RISK, COMPETITION, TIMING.
- **Positive:** "O que a gente tem hoje já resolve; não vejo razão para trocar." · **Counter:** "Como
  isso ajudaria a nossa equipe comercial?"
- **Main inference risk:** questionar valor ≠ não ter necessidade; "não sei se vale esse preço" é
  AMBIGUOUS {NEED_VALUE_FIT, PRICE_BUDGET}.
- **Diagnostic:** o lead nega necessidade/valor/adequação, ou só pergunta/duvida?

### AUTHORITY_INTERNAL_BUY_IN

- **Definition:** o lead diz que não pode aprovar sozinho, ou que a aprovação/concordância de outra
  pessoa é condição que **impede** avançar.
- **Use when:** falta explícita de alçada; aprovação necessária dita como bloqueio; não consegue
  convencer internamente.
- **Do not use when:** só vai conversar/mostrar a alguém; descreve o processo normal de decisão;
  resistência relatada de terceiro sem assumi-la (GL-1); etapa formal de compras (→ TERMS_PROCESS).
- **Minimum evidence:** restrição de autoridade ou necessidade de aprovação dita como impedimento.
- **Often confused with:** menção a stakeholder, processo normal de decisão, TERMS_PROCESS, TIMING.
- **Positive:** "Eu não tenho alçada para aprovar esse contrato." · **Counter:** "Vou conversar com meu
  sócio." (só prova que há outro stakeholder)
- **Main inference risk:** stakeholder mencionado ≠ bloqueio de autoridade; cargo não prova nada.
- **Diagnostic:** o transcript afirma uma restrição de aprovação ou só menciona outro stakeholder?

### TRUST_RISK

**AI CLOSER PROVISIONAL ABSTRACTION** — trust + risk unidos operacionalmente; não é categoria acadêmica
consolidada.

- **Definition:** receio de resultado negativo ou dúvida sobre a capacidade do fornecedor/solução de
  cumprir, ligado a não avançar.
- **Use when:** "tenho medo de não funcionar no nosso volume e por isso não fecho"; experiência ruim
  anterior dita como razão atual.
- **Do not use when:** pede case/referência/prova; receio do esforço técnico (→ IMPLEMENTATION); "não
  serve pra nós" (→ NEED_VALUE_FIT); experiência ruim relatada sem ligação com a decisão.
- **Minimum evidence:** receio/dúvida dita **ligada** à disposição de avançar.
- **Often confused with:** NEED_VALUE_FIT, IMPLEMENTATION_INTEGRATION, COMPETITION.
- **Positive:** "Da última vez o fornecedor sumiu depois da venda; sem garantia de suporte eu não fecho."
  · **Counter:** "Vocês têm algum cliente do nosso porte?"
- **Main inference risk:** experiência ruim passada ≠ desconfiança atual.
- **Diagnostic:** o receio está ligado, no dito, a não avançar?

### COMPETITION_EXISTING_SOLUTION

- **Definition:** uma alternativa existente (fornecedor atual, concorrente, contrato com outro) é dita
  como razão para não avançar.
- **Use when:** satisfeito com o atual e não troca; já fechou com outro; preso a contrato com outro e
  isso impede.
- **Do not use when:** só informa que avalia outros; pede comparação; alternativa é "fazer como hoje"
  sem fornecedor (provisoriamente → NEED_VALUE_FIT, CIT-O6).
- **Minimum evidence:** a alternativa aparece como motivo para não avançar.
- **Often confused with:** NEED_VALUE_FIT (status quo), TIMING (fim de contrato), TERMS_PROCESS, TRUST_RISK.
- **Positive:** "Estamos satisfeitos com o sistema X e não pretendemos trocar." · **Counter:** "Também
  estamos avaliando X."
- **Main inference risk:** concorrente mencionado ≠ objeção competitiva.
- **Diagnostic:** a solução alternativa impede o avanço ou só foi mencionada?

**Status quo** não é categoria na v0.1: classifique pelo bloqueio dito (fornecedor atual → COMPETITION;
"não precisamos mudar" → NEED_VALUE_FIT; "agora não é hora" → TIMING; sem motivo → AMBIGUOUS/NO_OBJECTION).

### IMPLEMENTATION_INTEGRATION

Provisional e **operation-dependent**: o pilot deve mostrar se é discriminante.

- **Definition:** esforço, viabilidade ou impacto operacional/técnico de pôr a solução em funcionamento
  impede o avanço.
- **Use when:** sem equipe/tempo para implantar; não integra com o sistema do lead e isso impede;
  impacto da implantação inaceitável.
- **Do not use when:** pergunta como funciona a integração; receio sobre o fornecedor (→ TRUST_RISK);
  não resolve o problema (→ NEED_VALUE_FIT); o momento da compra por prioridade (→ TIMING).
- **Minimum evidence:** dificuldade de implementação ligada a não avançar.
- **Often confused with:** TRUST_RISK, NEED_VALUE_FIT, TIMING_PRIORITY.
- **Positive:** "Nosso TI são duas pessoas; não temos braço para essa migração, então não dá." ·
  **Counter:** "Como funciona a integração?"
- **Main inference risk:** pergunta técnica ≠ objeção.
- **Diagnostic:** a dificuldade de implantar é dita como impedimento ou só perguntada?

### TERMS_PROCESS

Provisional e operation-dependent.

- **Definition:** condição comercial/contratual ou processo formal de compra dito como impedimento ou
  condição.
- **Use when:** recusa de termo que impede fechar; regra de compras/jurídico não permite o formato;
  mudança de termo exigida para seguir.
- **Do not use when:** descreve o processo normal; pergunta sobre termos; barreira é o valor
  (→ PRICE_BUDGET); aprovação de uma pessoa (→ AUTHORITY).
- **Minimum evidence:** termo/processo funcionando, no dito, como impedimento ou condição.
- **Often confused with:** PRICE_BUDGET (forma de pagamento), AUTHORITY, TIMING, COMPETITION (contrato
  vigente).
- **Positive:** "Nossas regras de compras não permitem esse formato de contratação." · **Counter:**
  "Nosso jurídico vai revisar."
- **Main inference risk:** processo mencionado ≠ processo como barreira.
- **Diagnostic:** o processo/termo impede ou condiciona o avanço, ou só descreve uma etapa?

### OTHER

Use **somente** quando há objection clara (A–D) e nenhuma das 8 representa o bloqueio. Escreva em nota,
em uma linha, qual é o bloqueio — é o insumo para ADD/MERGE em TAX.

- Candidato sintético: "Eu não fecho nada por vídeo; só pessoalmente." (canal de compra como barreira;
  se você ler TERMS_PROCESS, registre a divergência).
- **OTHER não é "não sei"** (→ UNKNOWN) nem "fica entre duas" (→ AMBIGUOUS). Não use OTHER para fugir de
  uma fronteira difícil entre as 8.

## UNKNOWN vs AMBIGUOUS

| Status | Quando | Exemplo |
|---|---|---|
| **UNKNOWN** | a pergunta se aplica, mas **não há informação suficiente** (ilegível, cortado, speaker incerto, sentido fora da call) | "[inaudível]… não dá desse jeito." — há barreira, categoria indeterminável |
| **AMBIGUOUS** | há informação, mas **duas ou mais leituras seguem plausíveis**; registre as candidatas | "Isso é bastante dinheiro." — comentário, preocupação ou PRICE_BUDGET? Sem contexto: AMBIGUOUS |

Vale para detecção (é objeção?), categoria, fronteira e reação. Na resolução, o **valor** de
`resolution_status` continua sendo um dos quatro do contrato: reação AMBIGUOUS ou UNKNOWN →
`resolution_status = unknown`, com AMBIGUOUS/UNKNOWN registrado como status da anotação e as leituras em
nota. Não converta incerteza em categoria por conveniência. UNKNOWN não é "difícil": se a evidência basta, decida. N/A só quando a pergunta não se
aplica estruturalmente (call ABSENT, call não anotável).

## Episode boundaries

Regras do contrato (§5), inalteradas:

- **Âncora:** primeiro segmento do objetor que faz parte da expressão da objeção; pode ser começo
  incompleto completado pela fala seguinte do objetor, com só falas não substantivas de outros no meio
  (interjeições, logística da call, apartes que não mudam o assunto). Pergunta completa e neutra antes da
  resistência não é âncora.
- **Fim:** o fio fecha quando alguém fala algo substantivo sobre assunto que não é nenhum fio aberto e
  não é nova objeção. Não fecham: interjeições, logística, apartes, falas que servem à resolução do fio
  (ex.: perguntar volume para calcular retorno), adiamento explícito ("vamos voltar nisso" → parked até
  retomada, abandono explícito ou fim da call). Mudar de assunto sem anunciar retorno fecha.
- Leia **até a closure ou o fim da call** antes de fixar fronteira e resolução.
- Na dúvida entre mesmo/novo episódio: mesmo episódio; se não souber a fronteira, AMBIGUOUS + nota.

**Episódio é atômico por categoria (CIT-M2).** "Está caro e não temos time para implementar." com as
duas barreiras claras → episódio A `PRICE_BUDGET` e episódio B `IMPLEMENTATION_INTEGRATION`, **mesma
âncora**. Sem "objeção composta", sem episódio-pai, sem categoria principal/secundária.

Outras regras: mesma categoria duas vezes na mesma fala → um episódio; objetores diferentes → episódios
diferentes; outro lead que concorda abre o próprio episódio; outro lead que discorda é contexto e nunca
resolve o episódio de outro.

## Repeated objections

- **Mesmo objetor + mesma categoria + fio aberto ou parked → mesmo episódio**; a nova fala é reação (em
  `context_segment_ids`).
- **Depois da closure → novo episódio** (recorrência). Recorrência não é reabertura; não decida se é "a
  mesma preocupação".
- Aceitação seguida de reversão sem closure no meio → mesmo episódio.
- Semelhança de palavras não decide nada; decide o estado do fio.

## Seller handling

Handling = **fala do closer dirigida à objeção**, em `context_segment_ids`. Registra-se só presença.
**Não** classifique o tipo de resposta (acknowledge, clarify, probe, reframe…): essa taxonomia foi
**DEFERRED** e fica fora do D3. Não avalie qualidade.

- Adiamento explícito do closer → entra no contexto; fio parked.
- Mudança de assunto sem adiamento → não é handling; fecha o fio se for assunto substantivo fora dele.
- Não é handling: "ok"/"entendi" isolados, repetição da objeção pelo closer, fala de outro participante.
- Ausência de handling **não** torna a resolução `unresolved` nem N/A.

## Prospect reaction

Reação = fala do **objetor** depois da expressão inicial da objeção, sobre o mesmo assunto (contrato
§9.1); pode estar no mesmo segmento (autocorreção). Cada resposta recebe **um** rótulo do contrato
(pensamento de anotação, não campo):

| Rótulo do contrato | Vocabulário da pesquisa que cai aqui |
|---|---|
| ACCEPT | aceita a resposta; avança de forma ligada ao tema ("nesse formato dá, pode mandar o contrato") |
| REJECT | repete a objeção; continua preocupado; rejeita a resposta; pendência declarada |
| MIXED | aceita um aspecto e mantém outro aspecto **da mesma categoria**, na mesma resposta |
| NEUTRAL | só interjeição ("ok", "tá", "uhum", "Hmm… tá") — descartada |
| OFF_CATEGORY | só outro assunto (mudança de tópico sem confirmação) — descartada |
| UNKNOWN | conteúdo sobre o ponto, mas ininterpretável (ilegível, ironia indecidível) |

- Nova objeção de outra categoria → **outro episódio**; não prova que a anterior foi resolvida.
- Silêncio, mudança de assunto e fim da call não são reação.
- Fala de outro participante nunca é reação do objetor.

### OPEN GAP — pedido de clarificação (REQUESTS_CLARIFICATION)

Closer responde; lead: "Como exatamente isso funcionaria?" É reação substantiva sobre o ponto, **não** é
ACCEPT, **não** é REJECT e **não** é resolução. O contrato não tem rótulo que a represente fielmente
(NEUTRAL é "sem conteúdo"; UNKNOWN é "ininterpretável").

**Regra provisória do pilot (GL-3, conservadora):** pedido de clarificação **não sobrescreve** a última
resposta com posição (ACCEPT/REJECT/MIXED/UNKNOWN) e **nunca** a cria. Se for a única resposta → não há
posição → `unknown`. Registre em nota "CLARIFICATION" em toda resposta assim tratada, para o pilot medir
frequência e divergência. Não é mudança de contrato; é OPEN GAP para D6.

**Diagnostic:** a pergunta **pede informação** sobre a resposta do closer, ou **reafirma, em forma de
pergunta, que a barreira continua**?

- **Claramente pede informação** ("E como vocês fariam a migração sem parar o sistema?") → CLARIFICATION
  (GL-3): não implica ACCEPT nem REJECT; se for a única reação substantiva disponível, `resolution_status
  = unknown`.
- **Claramente reafirma a barreira** ("E eu vou pagar isso tudo de novo no ano que vem?", "Vocês acham
  mesmo que a gente consegue pagar isso?") → REJECT; aplique as regras normais de resolução
  (tipicamente `unresolved`, se o mesmo bloqueio permanece).
- **As duas leituras seguem plausíveis** → a **reação/interpretação** é AMBIGUOUS (registre as leituras
  candidatas) e `resolution_status = unknown`.

AMBIGUOUS é status de incerteza da anotação, **nunca** valor de `resolution_status`, que só aceita
`resolved`, `partially_resolved`, `unresolved` ou `unknown`. Nenhum enum novo; D6 continua aberta.

## Resolution

**PROVISIONAL** — valores e regras do contrato (§9); semântica comercial final depende de **D6**.

Valores: `resolved`, `partially_resolved`, `unresolved`, `unknown`. Decida pela **última resposta
substantiva do objetor** sobre o assunto (§9.2); NEUTRAL e OFF_CATEGORY nunca sobrescrevem.

- Seller response ≠ resolution. Silence ≠ acceptance. Topic change ≠ resolved.
- **Deal won ≠ objection resolved.** Não use Outcome, CRM nem calls posteriores.
- Nenhuma resposta substantiva do objetor → `unknown`.
- Reafirmação da preocupação geral ("continua caro", "ainda não cabe") → `unresolved`, mesmo com causa
  nova.

| Situação | Valor |
|---|---|
| "Com esse parcelamento dá, pode seguir." | `resolved` |
| "Continua caro pra mim." | `unresolved` |
| "A mensalidade está ok, mas a taxa de implantação ainda pesa." (mesma resposta) | `partially_resolved` |
| Closer responde; lead "Hmm." e a call acaba | `unknown` |
| Closer responde; lead só pergunta "e como seria isso na prática?" e a call acaba | `unknown` (GL-3) |

### partially_resolved

Extremamente conservador. Só quando **todas** valem (contrato §9.1, MIXED): um aspecto claramente aceito;
**outro aspecto diferente** (satisfazível independentemente) pendente; ambos da **mesma categoria** do
episódio; **na mesma resposta**. Nunca porque o closer "fez progresso", o lead "pareceu menos resistente"
ou uma de duas categorias sumiu — duas categorias são **dois episódios**, cada um com seu status.

### "Ainda preciso verificar se consigo pagar."

**SOURCE-BACKED OPERATIONAL GUIDANCE — NOT D6 CLOSURE.**

| Situação | Como anotar |
|---|---|
| Não há episódio estabelecido; a frase aparece sozinha | é questão de **detecção**, não de resolução. Aplique A–D: se o dito liga explicitamente o avanço à capacidade de pagar, PRESENT `PRICE_BUDGET` (resolução pelas respostas seguintes; sem elas, `unknown`); se é vago, AMBIGUOUS (hesitação × objeção) |
| Episódio `PRICE_BUDGET` estabelecido; após o handling o lead diz a frase | a barreira continua ativa → REJECT → `unresolved`, salvo evidência posterior |
| Na mesma resposta o lead aceita outro aspecto **do mesmo episódio** ("o valor total está ok; ainda preciso ver se consigo pagar a entrada") | MIXED → `partially_resolved` |
| O lead aceita algo de **outra categoria** ("agora vejo o retorno; ainda preciso ver se consigo pagar") | dois episódios (ex.: NEED_VALUE_FIT `resolved`, PRICE_BUDGET `unresolved`) — não `partially_resolved` |

## Resolution vs DealOutcome

Resolução da objeção ≠ Outcome do Deal. O anotador **não vê** o Outcome e nunca usa o resultado para
interpretar a call.

## External knowledge and RAG boundary

- A Knowledge Base pode ajudar a entender definição, quando usar, quando não usar e confusões.
- A anotação aponta **`segment_id`s**; nunca cita knowledge unit, framework ou pesquisa como evidência.
- Frameworks não são labels: Economic Buyer existir ≠ AUTHORITY; budget discutido ≠ PRICE_BUDGET.
- **RAG/model suggestion ≠ gold.** Mesmo no futuro: sugestão de modelo → revisão humana → gold adjudicado.
  Nunca predição → gold automático. No pilot D3, anotadores A/B **não** veem sugestão de modelo/RAG.

## Blindness

Durante a anotação **não** mostrar: DealOutcome, WON/LOST, stage do CRM, predição de modelo, outra
anotação, sugestão de RAG, score de vendedor. O anotador vê: transcript + esta guideline + (quando
aplicável) a Knowledge Base como referência. Outcome só entra depois, em Outcome Intelligence.

## Golden Set label set

- **Gold Annotation v0.1** usa as 8 categorias + `OTHER`, com status UNKNOWN e AMBIGUOUS.
- O manifest registra `guideline_version = v0.1` e `taxonomy_version = CIT v0.1 (provisional)`.
- Esse gold **não** é serializado como `ObjectionEpisode` de produção enquanto D7 estiver aberto (o
  campo `category` do contrato só aceita o enum v0). Não derive `episode_id` de produção com esses
  labels; o matching de eval (§12.2) não precisa dele.
- Não há mapeamento determinístico label v0.1 → enum v0 (`trust_authority` se divide).

## Annotation workflow v0.1

Leia a call inteira primeiro. Para cada trecho candidato:

1. Há sinal de resistência?
2. Satisfaz A–D (objection operacional)?
3. Não → **NO_OBJECTION** (ou AMBIGUOUS se duas leituras seguem plausíveis).
4. Sim → âncora e `objection_segment_ids`.
5. Categoria pelo que é resistido.
6. Categoria incerta → UNKNOWN / AMBIGUOUS {candidatas}.
7. Handling do closer → `context_segment_ids` (só presença).
8. Respostas substantivas do objetor → `context_segment_ids`; rótulo de cada uma.
9. `resolution_status` só pelo que a evidência sustenta.
10. Caso que o contrato não representa → nota "OPEN ISSUE" para o pilot.

## Annotation checklist

1. Li a call inteira antes de fixar episódios e resoluções?
2. O speaker é `role="lead"`?
3. A–D estão sustentados pelo dito — ou é pergunta, comentário, hipótese, passado, hesitação, brush-off?
4. Estou classificando tópico em vez de barreira?
5. Qual `segment_id` é a âncora; quais completam a objeção; quais são contexto?
6. Duas barreiras de categorias diferentes → dois episódios?
7. Qual a última resposta substantiva do objetor? Algum pedido de clarificação (GL-3)?
8. A resolução é observável na call, sem Outcome?
9. Estou inferindo algo não dito? Isso foi para nota INFERIDO?
10. Se marquei ABSENT, revisei a call inteira?

## Adjudication checklist

1. Todos os `segment_id`s existem e a âncora é do objetor?
2. Âncora pela §5.3; closure/parked pela §5.1?
3. Categoria sustentada pelo dito, não por tópico/palavra-chave?
4. Handling: só falas do closer dirigidas à objeção?
5. Reação: só falas do objetor; GL-3 aplicada igual pelos dois?
6. Resolução pela última resposta substantiva, sem Outcome?
7. Tipo da divergência (DETECTION, BOUNDARY, CATEGORY, HANDLING, RESOLUTION, APPLICABILITY)?
8. Algum lado usou inferência ou conhecimento externo como evidência?
9. O gold deve continuar AMBIGUOUS ou UNKNOWN?
10. A divergência revela falha desta guideline ou de uma categoria (KEEP/MERGE/SPLIT/REMOVE/ADD)?

Não escolha a anotação "mais detalhada" por ser mais detalhada.

## Adversarial examples

| # | Trecho (sintético) | Decisão |
|---|---|---|
| A1 | Lead: "Caro mesmo é o frete que pagamos hoje; o de vocês está ok." | NO_OBJECTION (não resiste à oferta) |
| A2 | Closer: "Muita gente acha caro no início…" | NO_OBJECTION (closer) |
| A3 | Lead: "Ano passado achei caro, mas hoje o preço não é problema." | NO_OBJECTION (não ativa) |
| A4 | Lead: "Meu sócio vai reclamar do preço, mas quem decide sou eu e eu topo." | NO_OBJECTION (GL-1) |
| A5 | Lead: "Qual é a multa se cancelarmos?" | NO_OBJECTION, salvo resistência explícita |
| A6 | Lead: "Está caro." Closer: "Parcelamos." Lead: "Ok, dá." … (assunto de negócio fora do fio) … Lead: "Voltando: ainda acho caro." | dois episódios `PRICE_BUDGET`; o primeiro `resolved` |
| A7 | Lead: "Fechado, esse desconto resolve." Lead (logo depois): "Espera, com imposto fica caro." | mesmo episódio; `unresolved` |
| A8 | Lead: "Claro, super barato… metade do nosso faturamento." | PRESENT `PRICE_BUDGET` porque a barreira é dita literalmente; só a ironia → AMBIGUOUS |
| A9 | Lead: "Vou falar com meu sócio e te retorno." | NO_OBJECTION (stakeholder mencionado; **corrige o exemplo 4 da v0**) |
| A10 | Lead: "Também estamos conversando com outra empresa." | NO_OBJECTION (informação competitiva) |
| A11 | Lead: "Me manda a proposta por e-mail que depois eu vejo." | NO_OBJECTION ou AMBIGUOUS; nunca TIMING |

## Synthetic examples

Formato: trecho (`sN` = segmento) · decisão · por quê · erro comum.

1. **Positivo claro** — s1 Lead: "Esse valor está acima do que podemos gastar agora." · `PRICE_BUDGET`,
   âncora s1 · barreira de verba dita · erro: TIMING por causa de "agora".
2. **Duas barreiras** — s1 Lead: "Está caro e não temos time para implementar." · dois episódios
   (`PRICE_BUDGET`, `IMPLEMENTATION_INTEGRATION`), âncora s1 · erro: um episódio só, ou `partially_resolved`
   depois.
3. **Autoridade real** — s1 Lead: "Gostei, mas acima de 10 mil eu não assino; sem o diretor não sai." ·
   `AUTHORITY_INTERNAL_BUY_IN` · restrição dita · erro: exigir mais que isso.
4. **Stakeholder só mencionado** — s1 Lead: "Está caro, e ainda vou mostrar para a minha sócia." · um
   episódio `PRICE_BUDGET`; a sócia é OBSERVADO em nota · erro: segundo episódio de autoridade.
5. **Hesitação** — s1 Lead: "Não sei… preciso pensar." (nada mais) · sem episódio; AMBIGUOUS na detecção
   se houver leitura de barreira · erro: TIMING por hábito.
6. **Hesitação com barreira** — s1 Lead: "Preciso pensar, porque o valor passou do que separamos." ·
   `PRICE_BUDGET` · a barreira foi dita · erro: tratar como só hesitação.
7. **Repetida no mesmo fio** — s1 Lead: "Está caro." s2 Closer: "Parcelamos em 12x." s3 Lead: "Mesmo assim
   acho caro." · um episódio; `unresolved` · erro: novo episódio em s3.
8. **Clarificação final** — s1 Lead: "Não temos equipe para migrar." s2 Closer: "A migração é feita por
   nós." s3 Lead: "E como vocês fariam isso sem parar nosso sistema?" (call termina) ·
   `IMPLEMENTATION_INTEGRATION`, `unknown` (GL-3, nota CLARIFICATION) · erro: `resolved`.
9. **Categoria ambígua** — s1 Lead: "Não sei se vale o que vocês estão cobrando." · AMBIGUOUS
   {`NEED_VALUE_FIT`, `PRICE_BUDGET`} · erro: escolher uma.
10. **Unknown** — s1 Lead: "Está caro." s2 Closer: "Temos desconto à vista." s3 Lead: "[inaudível]" ·
    `PRICE_BUDGET`, `unknown` · erro: `unresolved`.
11. **Parcial** — s1 Lead: "O total está ok, mas a entrada ainda pesa." (última resposta após handling) ·
    `partially_resolved` · mesmo episódio, dois aspectos · erro: `resolved`.
12. **Closer citando** — s1 Closer: "Você disse que estava caro, certo?" · não é âncora · erro: abrir
    episódio no closer.

## Calibration Kit impact

**Não editado nesta branch.** Depois do merge da v0.1, revisar `docs/evals/calibration/`:

| Item | Por quê |
|---|---|
| `ANNOTATION_TEMPLATE_V0.md` / `ADJUDICATION_TEMPLATE_V0.md` | campo Category diz "valor do enum v0" → label set v0.1; nota CLARIFICATION (GL-3) |
| CAL01 (referência `price`) | re-rotular para o label set v0.1; a barreira é a forma de pagamento → fronteira PRICE_BUDGET × TERMS_PROCESS a decidir na referência; `S010` é pedido de clarificação no meio do fio (não é a última resposta) |
| CAL02 (ABSENT, adversarial) | continua válido; já exercita NO_OBJECTION (pergunta, passado, hipótese, terceiro). Não exercita menção a stakeholder/concorrente nem brush-off |
| CAL03 (referência `timing_priority`) | re-rotular: a barreira é a **duração da implantação** diante de um evento → fronteira TIMING_PRIORITY × IMPLEMENTATION_INTEGRATION (possível AMBIGUOUS); `S017` "vou pensar" dentro do episódio (hesitação como resposta) |
| Lacunas | nenhum caso de AUTHORITY real × stakeholder, TRUST_RISK, COMPETITION, brush-off, UNKNOWN de categoria, OTHER |

A revisão deve ser feita por quem **não** escreveu esta guideline, com frases novas (sem copiar exemplos
daqui), para não medir memória.

## Pilot instructions

D3: **3–5 calls reais autorizadas**.

- A e B anotam **às cegas**, sozinhos; o adjudicador é uma terceira pessoa.
- Leia a call inteira primeiro; depois anote.
- Registre: dúvidas, trechos em que a guideline não decidiu, tempo por call, notas de sub-conceito
  (NEED/VALUE/FIT), notas CLARIFICATION, OTHER com descrição, e (na adjudicação) o tipo de cada
  divergência.
- **Não altere a guideline no meio de uma call nem da rodada.** Correções viram nova versão.

## What annotators must not do

- Usar Outcome, CRM, `current_stage` ou procurar venda posterior.
- Usar nome do cliente ou dados fora da call.
- Inferir emoção, intenção ou "desculpa" sem fala que sustente.
- Completar trechos do transcript.
- Assumir silêncio = aceitação ou resposta do closer = resolução.
- Marcar categoria por tópico ou palavra-chave.
- Citar Knowledge Base, framework ou pesquisa como evidência.
- Usar modelo/LLM/RAG para decidir qualquer rótulo.
- Ver a anotação do outro anotador antes de enviar a sua.
- Corrigir speaker ou papel dos participantes.

## Open decisions

| # | Estado | Nota |
|---|---|---|
| CIT-O1 | **APPROVED** (Matheus, 2026-09-28) | D3 e Golden Set v1 usam o label set v0.1; enum do domínio inalterado |
| D3 | OPEN | esta guideline prepara o pilot; não prova agreement, utilidade das categorias, completude da taxonomia nem desempenho em dado real |
| TAX | OPEN | as 8 são PROVISIONAL LABEL SET; resultados possíveis pós-pilot: KEEP / MERGE / SPLIT / REMOVE / ADD — não antecipados |
| D6 | OPEN | orientação operacional melhorada; nenhuma recomendação de pesquisa vira decisão comercial/canônica |
| D7 | OPEN (gate) | qualquer mudança de enum, schema ou contrato. **Annotation label set ≠ domain enum** |
| GS-1..GS-3 | OPEN | ver protocolo |
| GL-1 | OPEN | resistência atribuída a terceiro — validar fronteira no pilot |
| GL-2 | OPEN | hesitação/adiamento vago isolado: frequência e se precisa regra própria |
| GL-3 | OPEN GAP (nova) | pedido de clarificação como resposta: regra provisória "não sobrescreve"; contrato sem rótulo fiel |
| CIT-O2..O6 | OPEN | fusões NEED/VALUE/FIT e TRUST/RISK; concern × objection; operation-dependence; solução interna |

## Changes from v0

- **Sales resistance separado de objection**; checklist A–D.
- **Label set experimental de 8 categorias** + OTHER (CIT-O1 APPROVED), no lugar do enum v0 — só em
  anotação/eval; enum do domínio inalterado.
- Regra explícita **topic ≠ objection** e **NO_OBJECTION** por trecho.
- **Hesitation** e **brush-off** operacionalizados (sem virar campo).
- **Autoridade** exige restrição dita; exemplo "sócio" da v0 (exemplo 4, "Multiple objections")
  corrigido (A9, exemplo 4 novo).
- Cadeia **evidence → observation → classification → interpretation**.
- **Fronteira RAG/evidência** e sugestão de modelo ≠ gold.
- Resolução: mapeamento do vocabulário de reação para os rótulos do contrato; **GL-3** (clarificação);
  guia de "ainda preciso verificar se consigo pagar"; `partially_resolved` restrito a MIXED.
- Seção de impacto no Calibration Kit.
