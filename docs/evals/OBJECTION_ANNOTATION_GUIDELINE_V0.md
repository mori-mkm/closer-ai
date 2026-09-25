# Objection Annotation Guideline v0

Status: **DRAFT — pré-pilot.** Não usada em dado real ainda. D3, D6 e a taxonomia final continuam
abertas. Todos os exemplos são sintéticos.

## Purpose

Instruções operacionais para um humano decidir **o que anotar em uma Call** para `ObjectionEpisode`,
de forma que duas pessoas cheguem a decisões comparáveis. O *como construir o Golden Set* (dupla
anotação, adjudicação, versões, métricas) está no
[`GOLDEN_SET_ANNOTATION_PROTOCOL_V1.md`](GOLDEN_SET_ANNOTATION_PROTOCOL_V1.md) e não é repetido.

## Scope

- Dentro: o que é e não é objeção, evidência, fronteiras, múltiplas e repetidas, handling, reação,
  resolução provisória, categoria, AMBIGUOUS/UNKNOWN/N/A, rótulos negativos, checklists, pilot.
- Fora: taxonomia final (TAX), semântica comercial final de `resolution_status` (D6), thresholds
  (D3), ferramentas, schema executável, prompt de produção.

## Relationship to ObjectionEpisode

A guideline ensina a preencher o contrato
([`OBJECTION_EPISODE_V1_PROPOSAL.md`](../domain/OBJECTION_EPISODE_V1_PROPOSAL.md)); não cria outro.
Por episódio o anotador produz: `category`, `objection_segment_ids` (o primeiro é a âncora),
`context_segment_ids`, `resolution_status`, e os metadados de revisão do protocolo (status do rótulo,
notas observado/inferido, ponteiro de justificativa opcional). Quando esta guideline e o contrato
divergirem, **vale o contrato**; registre a divergência como dúvida do pilot.

Categorias provisórias para o pilot: o enum v0 que já existe no domínio — `price`,
`timing_priority`, `trust_authority`, `no_need`, `other` (`src/closer_ai/domain/objection.py`).
Podem mudar depois do workshop de taxonomia (TAX).

## What is an objection?

Marque um episódio quando **um participante com papel de lead** (o objetor), **com as próprias
palavras**, expressa **agora, nesta call**, uma **resistência a avançar com a oferta**: uma barreira,
discordância, condição ainda não atendida ou preocupação que ele próprio levanta como impedindo ou
dificultando seguir em frente.

Os quatro testes, todos observáveis:

1. **Quem:** o speaker tem `role="lead"` na Call. Closer, `other` e `unknown` nunca abrem episódio.
2. **Palavras próprias:** a resistência é dita pelo objetor, não atribuída a ele por outra pessoa.
3. **Agora:** é uma posição atual, não uma lembrança de algo já superado nem uma hipótese.
4. **Contra avançar:** a fala resiste à oferta, ao preço, ao momento, à decisão ou à necessidade —
   não é só um pedido de informação.

Não use motivos psicológicos ("parece desconfiado") como critério. Julgue o que foi dito.

## What is not an objection?

| Situação | Por que não | Exemplo sintético |
|---|---|---|
| Pergunta neutra / pedido de informação | pede dado, não resiste | "Quanto custa o plano anual?" |
| Dúvida operacional | quer entender o processo | "O contrato é assinado por e-mail?" |
| Comentário sem resistência | observação, sem barreira | "Interessante, não conhecia essa função." |
| Small talk | fora da oferta | "Hoje o trânsito estava pesado." |
| Fala do closer | objetor é sempre lead | Closer: "O preço ficou alto pra você?" |
| Objeção hipotética | não é posição atual | "Se fosse o dobro, aí sim seria caro." |
| Objeção passada já resolvida | não está ativa agora | "No começo achei caro, mas depois de ver o ROI fez sentido." |
| Resistência atribuída a terceiro sem que o lead a assuma | não é do objetor (ver GL-1) | "Meu sócio talvez ache caro, mas eu acho justo." |

## Evidence rules

- Evidência = **`segment_id`s** da Call (contrato §7). Sem trechos de caracteres, sem quote livre
  como verdade. Timestamps vêm do segmento; não anote timestamps.
- `objection_segment_ids`: segmentos **do objetor** necessários para entender a objeção (âncora +
  continuação). `context_segment_ids`: os segmentos adicionais necessários para entender o
  episódio (closer respondendo, reações do objetor, falas de terceiros sobre o tema). Uma fala
  entra em **uma** lista por episódio.
- **Evidência forte:** o objetor diz diretamente a barreira ("Está acima do que conseguimos pagar").
  Pode sustentar PRESENT sozinha.
- **Evidência fraca:** algo que só sugere objeção e exige inferência ("Vou pensar", "Hmm, entendi").
  Não sustenta PRESENT sozinha. Procure no contexto uma fala forte; sem ela, marque AMBIGUOUS (duas
  leituras plausíveis) ou não anote (nenhuma leitura de objeção sustentada).
- O speaker de cada segmento é o registrado na Call. Se o speaker é `unknown`, o segmento não pode
  ser âncora (TD-14); não corrija o speaker na anotação.

## Observed vs inferred

Só o **dito** vira evidência ou valor de campo. Inferências vão para nota marcada "INFERIDO".

| Dito (pode ser evidência) | Inferência (só nota) |
|---|---|
| "Preciso falar com meu sócio antes de decidir." | "Não tem poder de decisão." |
| "Agora estamos focados na safra." | "Não é prioridade para eles." |
| "Já tentamos uma ferramenta assim e não funcionou." | "Não confia no fornecedor." |
| "Esse valor aperta nosso caixa este mês." | "Não tem orçamento nenhum." |

Se a inferência é necessária para decidir a categoria, a categoria é UNKNOWN ou AMBIGUOUS, não o
valor inferido.

## Episode boundaries

Regras do contrato (§5): âncora, closure, parked, recorrência.

- **Âncora:** o **primeiro** segmento do objetor que faz parte da expressão da objeção. Pode ser um
  começo incompleto ("Sobre o preço…") se a fala seguinte do objetor o completa e entre elas só há
  falas **não substantivas** de outros — interjeições, logística da call ou apartes de terceiros que
  não mudam o assunto, as mesmas da regra de fim abaixo (§5.3, conjunto definido em §5.1). Pergunta completa e neutra antes da resistência **não** é âncora.
- **Contexto anterior:** não entra. O episódio começa na âncora.
- **Handling e reação:** segmentos posteriores à âncora, em `context_segment_ids`.
- **Fim:** o fio fecha quando alguém fala algo substantivo sobre um assunto que não é nenhum fio
  aberto e que não é nova objeção (§5.1). **Não fecham** o fio: interjeições ("ok", "tá",
  "uhum"), logística da call — a **mecânica da reunião** (áudio, tela, pausa, "só um minuto"), não
  assuntos de negócio —, apartes de terceiros que não mudam o
  assunto, falas que servem para resolver a objeção (ex.: perguntar volume para calcular o
  retorno) e adiamento explícito ("vamos voltar nisso depois" → o fio fica parked até ser retomado,
  abandonado explicitamente ou até o fim da call). **Mudar de assunto sem anunciar retorno não é
  adiamento:** o fio fecha.
- Leia **até a closure ou o fim da call** antes de fixar fronteira e resolução.

Casos:

| # | Caso | Como anotar |
|---|---|---|
| 1 | Objeção numa fala só | âncora = essa fala; `objection_segment_ids` = [essa fala] |
| 2 | Objeção espalhada em duas falas do objetor | as duas em `objection_segment_ids`, âncora = a primeira |
| 3 | Closer interrompe e o objetor completa | falas do objetor em `objection_segment_ids`; a interrupção do closer em `context_segment_ids` |
| 4 | Duas objeções na mesma fala | ver "Multiple objections" |
| 5 | A objeção volta mais tarde | ver "Repeated objections" |
| 6 | Mesma categoria, conteúdo diferente | fio aberto → mesmo episódio; fio fechado → novo episódio |

Não junte nem separe episódios por conveniência. Se não souber onde está a fronteira, marque
AMBIGUOUS e explique.

## Multiple objections

Regra v0 (contrato §5, regra 5):

- **Categorias diferentes na mesma fala → dois episódios** com a **mesma âncora**. Ex.: "Está caro
  e eu ainda preciso falar com meu sócio." → um episódio `price` e um `trust_authority`, ambos
  ancorados nesse segmento. Não existe "objeção composta" nem "principal e secundária" em v0.
- **Mesma categoria duas vezes na mesma fala → um episódio.**
- **Objetores diferentes → episódios diferentes**, mesmo com a mesma categoria. Um participante
  nunca resolve a objeção de outro (§5.4). Outro lead que **concorda** com a objeção ("Concordo, está caro")
  abre o **próprio** episódio; outro lead que **discorda** ("Pra mim o preço está ok") é só contexto.
- Se não der para dizer se há uma ou duas categorias, anote um episódio com categoria AMBIGUOUS
  (candidatas listadas).

## Repeated objections

Regra do contrato (§5.1, §5.2), que prevalece sobre qualquer intuição de "novo ciclo":

- **Mesmo objetor + mesma categoria enquanto o fio está aberto ou parked → mesmo episódio**, mesmo
  que o closer já tenha respondido e o objetor volte a resistir. A nova fala do objetor é uma
  **reação** (em `context_segment_ids`), não uma nova âncora.
- **Depois da closure → novo episódio** (recorrência).
- **Recorrência não é reabertura.** A guideline não pede para decidir se é "a mesma preocupação
  voltando"; isso não é representado em v0.
- Aceitação seguida de reversão sem closure no meio ("Esse desconto resolve." … "Na verdade, com
  imposto ainda fica caro.") é o **mesmo episódio**.

## Handling

Handling = **fala do closer dirigida à objeção**. Entra em `context_segment_ids`. A guideline só
registra presença; **não avalia qualidade**.

| Tipo | Exemplo sintético | Anotação |
|---|---|---|
| Handling claro | Lead: "Está caro." Closer: "Dá para parcelar em 12x sem juros." | fala do closer no contexto |
| Adiamento explícito | Lead: "Está caro." Closer: "Entendo. Vamos ver a demo e depois voltamos ao preço?" | a fala do closer entra no contexto (é o adiamento; o fio fica parked); a resposta ao preço, quando vier, também entra |
| Mudança de assunto sem adiamento | Lead: "Está caro." Closer: "Entendo. Vamos ver a demo?" | não é handling; se a demo é assunto substantivo fora do fio, o fio fecha ali (closure) |
| Sem handling | Lead: "Está caro." Closer: "Ok." (e muda de assunto) | nenhuma fala do closer no contexto; handling ABSENT |

**Não é handling:** mudança de assunto, "entendi"/"ok" isolados, repetição da objeção pelo closer
sem resposta, pergunta que não trata da objeção, fala de outro participante.

Ausência de handling **não** torna a resolução `unresolved` nem N/A: a resolução depende do objetor.

## Lead reaction

Reação = **fala do objetor depois da expressão da objeção** sobre o mesmo assunto (contrato §9.1).
Pode estar no mesmo segmento da objeção (autocorreção) ou em segmentos seguintes. Rótulos para
pensar (não são campos): aceita, rejeita/reitera, aceita parte e mantém outra parte, só interjeição,
fala de outro assunto, ininteligível.

- Não infira satisfação. "Legal." isolado não é aceitação.
- Silêncio, mudança de assunto ou fim da call **não** são reação. O efeito disso aparece na
  resolução (tipicamente `unknown`).
- Fala de outro participante (outro lead, sócio) é contexto; nunca é reação do objetor.

## Resolution

**PROVISIONAL RESOLUTION ANNOTATION** — os valores e regras existem no contrato (§9); a semântica
comercial final depende de D6.

Valores: `resolved`, `partially_resolved`, `unresolved`, `unknown`.

- Observe **só o que aconteceu na call**. Não use Outcome do Deal, CRM nem calls posteriores.
- Decida pela **última resposta substantiva do objetor sobre o assunto** (§9.2). Interjeições
  depois de uma aceitação não a desfazem.
- "Prospect parou de falar" **não** é `resolved`. "Closer respondeu" **não** é `resolved`.
- **Parcial vs não resolvido (§9.1).** Um *aspecto* é uma parte da preocupação que pode ser
  satisfeita independentemente de outra (mensalidade × taxa de setup; valor total × entrada; prazo
  × multa de cancelamento). `partially_resolved` só quando, **na mesma resposta**, um aspecto é
  claramente aceito e **outro aspecto diferente** continua pendente. Se o objetor **reafirma a
  preocupação geral** ("continua caro", "ainda não cabe no orçamento"), é `unresolved`, **mesmo que
  cite uma causa nova**: "O desconto ajuda, mas ainda não cabe no orçamento" → `unresolved`;
  "O prazo de 24 meses está ok, mas a multa de cancelamento me preocupa" → `partially_resolved`.
- Nenhuma resposta substantiva do objetor → `unknown`.

| Situação | Valor |
|---|---|
| "Com esse parcelamento dá, pode seguir." | `resolved` |
| "Continua caro pra mim." | `unresolved` |
| "O valor total está ok, mas a entrada ainda pesa." | `partially_resolved` (aceita um aspecto, mantém outro) |
| Closer responde, lead diz "Hmm." e a call acaba | `unknown` |
| "Ainda preciso ver se consigo pagar." | `unresolved` (regra provisória do contrato; pergunta aberta em D6) |

"Reopened" não é um valor. Uma objeção que volta depois da closure é **outro episódio**; o
anterior mantém sua resolução.

## Resolution vs DealOutcome

**Resolução da objeção ≠ Outcome do Deal.** Uma objeção pode ser `resolved` na call e o Deal
terminar rejeitado; pode continuar `unresolved` e o Deal ser ganho. O anotador **não vê** o Outcome
durante a anotação e nunca usa o resultado para interpretar a call.

## Category assignment

- Categorize pelo **significado** da resistência, não por palavra-chave. "Caro" não basta; "não
  temos orçamento este trimestre" pode ser `price` ou `timing_priority` conforme o que está sendo
  resistido.
- Evidência primeiro: a categoria precisa ser sustentada pelo dito.
- Duas categorias plausíveis e o material não decide → **AMBIGUOUS** com as candidatas.
- Não dá para saber a categoria (ex.: objeção vaga, "não sei se é pra agora…" sem mais nada) →
  **UNKNOWN**.
- `other` é para objeção clara que não cabe em nenhuma categoria. Não use `other` no lugar de
  UNKNOWN ou AMBIGUOUS.

**EXTERNAL TAXONOMY REFERENCES — EXTERNAL_REFERENCE_ONLY.** Pricing, timing, authority, need,
competition, risk, status quo, integration aparecem em projetos externos
([`OPEN_SOURCE_REUSE_AUDIT.md`](../references/OPEN_SOURCE_REUSE_AUDIT.md)). São só sementes para o
workshop de taxonomia. **Não** são categorias deste domínio e não devem ser usadas na anotação.

### Positive and negative signals

- **Positive signal:** evidência que sustenta a categoria (o lead diz o que resiste).
- **Negative signal:** evidência que parece compatível mas **impede** a categoria. Ex.: "Eu achei
  caro no começo, mas agora entendi o valor." contém "caro" e **não** é objeção de preço ativa. Casos
  assim viram falsifying expectations do Golden Set.

## Ambiguous

Marque AMBIGUOUS quando o material sustenta **mais de uma** leitura:

- duas categorias plausíveis;
- não dá para saber se é objeção ou pergunta;
- a fronteira entre dois episódios não é clara;
- a reação sustenta duas leituras de resolução.

Registre as candidatas e o motivo. **Não** use AMBIGUOUS quando você não leu direito, quando o
transcript está ilegível ou quando a informação não existe (isso é UNKNOWN ou call não anotável).

## Unknown

Marque UNKNOWN quando a pergunta se aplica, mas o material não permite responder:

- trecho ilegível ou transcrição cortada;
- speaker do trecho incerto (`unknown`);
- reação não registrada (call acaba, lead não responde);
- sentido depende de contexto que não está na call.

UNKNOWN **não** é "difícil". Se a evidência é suficiente, decida.

## N/A

Só quando a pergunta **não se aplica estruturalmente**:

- Call ABSENT (sem objeções): categoria, handling, reação e resolução são N/A.
- Call não anotável: tudo N/A, com o motivo.

**Não** use N/A para "não houve handling" (é handling ABSENT e a resolução continua aplicável) nem
para "não sei" (UNKNOWN). O contrato não tem campos de detalhe de handling, então não há N/A de
"detalhe de handling".

## Negative labels

- **Call-level:** "não houve nenhuma objeção nesta call" só depois de revisar **a call inteira**.
  Um trecho ilegível impede esse rótulo (marque UNKNOWN para o trecho).
- **Category-level:** "não houve objeção da categoria X" só quando a taxonomia existir e a call
  tiver sido revisada com esse objetivo.
- **Trecho adversarial:** registre trechos que parecem objeção e não são ("closer citando a
  objeção", "objeção passada resolvida"), como "não deve ser episódio".
- "Não vi" **não** é ausência.

## Adversarial examples

| # | Trecho | Decisão |
|---|---|---|
| A1 | Lead: "Caro mesmo é o frete que pagamos hoje; o de vocês está ok." | não é objeção de preço à oferta |
| A2 | Closer: "Muita gente acha caro no início…" | não é episódio (closer) |
| A3 | Lead: "Ano passado achei caro, mas hoje o preço não é problema." | não é objeção ativa |
| A4 | Lead: "Meu sócio vai reclamar do preço, mas quem decide sou eu e eu topo." | não é objeção do lead (GL-1) |
| A5 | Lead: "Qual é a multa se cancelarmos?" | pergunta neutra, salvo resistência explícita |
| A6 | Lead: "Está caro." Closer: "Parcelamos." Lead: "Ok, dá." … (várias falas sobre o cronograma de treinamento) … Lead: "Voltando: ainda acho caro." | o treinamento é assunto de negócio fora do fio → closure → novo episódio `price` (recorrência); o primeiro fica `resolved` |
| A7 | Lead: "Fechado, esse desconto resolve." Lead (logo depois): "Espera, com imposto fica caro." | mesmo episódio; `unresolved` |
| A8 | Lead: "Claro, super barato… metade do nosso faturamento." | PRESENT `price`, **porque** "metade do nosso faturamento" diz a barreira literalmente. A ironia em si nunca é evidência: sem uma fala literal da barreira (ex.: só "Claro, super barato."), marque AMBIGUOUS |

## Annotation checklist

1. Li a call inteira antes de fixar episódios e resoluções?
2. Quem falou? É `role="lead"`?
3. Há resistência dita agora, com palavras do objetor — ou é pergunta/comentário/hipótese/passado?
4. Qual `segment_id` é a âncora (primeiro segmento da expressão)?
5. Quais segmentos completam a objeção e quais são contexto?
6. Houve handling do closer? Quais segmentos?
7. Houve reação do objetor? Qual a última resposta substantiva?
8. A resolução é observável na call, sem usar Outcome?
9. A categoria é determinável pelo dito? Senão, AMBIGUOUS ou UNKNOWN?
10. O fio fechou ou continua (repetição = mesmo episódio)?
11. Estou inferindo algo que não foi dito?
12. Se marco a call sem objeções, revisei a call inteira?

## Adjudication checklist

1. Evidência: todos os `segment_id`s existem e a âncora é do objetor?
2. Fronteira: âncora pela §5.3; closure/parked pela §5.1?
3. Categoria: sustentada pelo dito, não por palavra-chave?
4. Handling: só falas do closer dirigidas à objeção?
5. Reação: só falas do objetor?
6. Resolução: pela última resposta substantiva, sem Outcome?
7. Tipo da divergência (DETECTION, BOUNDARY, CATEGORY, HANDLING, RESOLUTION, APPLICABILITY)?
8. Algum lado usou inferência como evidência?
9. O gold deve continuar AMBIGUOUS ou UNKNOWN?
10. A divergência revela falha desta guideline? Registre para a próxima versão.

Não escolha a anotação "mais detalhada" por ser mais detalhada.

## Synthetic examples

Formato: trecho (`sN` = segmento) · decisão · por quê · erro comum.

1. **Positivo claro** — s1 Lead: "Esse valor está acima do que podemos pagar agora." · episódio
   `price`, âncora s1 · resistência dita, agora · erro: marcar `timing_priority` por causa de "agora".
2. **Negativo claro** — s1 Lead: "Quanto fica o plano anual?" · não é episódio · pede informação ·
   erro: anotar `price` pela palavra "fica".
3. **Espalhada em duas falas** — s1 Lead: "Sobre o preço…" s2 Closer: "Sim?" s3 Lead: "…ficou acima
   do orçamento." · episódio `price`, `objection_segment_ids` = [s1, s3], contexto = [s2] · s1 é
   começo incompleto completado por s3 · erro: âncora em s3.
4. **Duas objeções** — s1 Lead: "Está caro e preciso falar com meu sócio." · dois episódios (`price`
   e `trust_authority`), âncora s1 · categorias diferentes na mesma fala · erro: um episódio só.
5. **Repetida no mesmo fio** — s1 Lead: "Está caro." s2 Closer: "Parcelamos em 12x." s3 Lead:
   "Mesmo assim acho caro." · um episódio; s2, s3 no contexto; `unresolved` · fio não fechou · erro:
   novo episódio em s3.
6. **Recorrência** — s1 Lead: "Está caro." s2 Closer: "Parcelamos." s3 Lead: "Ok, dá." (s4–s9 sobre
   implantação) s10 Lead: "A taxa de setup está alta." · dois episódios `price`; o primeiro
   `resolved`, o segundo novo · o fio fechou na implantação · erro: juntar num só.
7. **Handling claro** — s1 Lead: "Não é prioridade este mês." s2 Closer: "Podemos começar em
   março." · s2 no contexto · resposta dirigida · erro: marcar `resolved` só porque o closer
   respondeu.
8. **Sem handling** — s1 Lead: "Está caro." s2 Closer: "Ok. Vamos para a agenda de treinamento." ·
   contexto vazio; handling ABSENT; resolução `unknown` (se o lead não volta ao tema) · erro: N/A na
   resolução.
9. **Ambiguous (objeção ou adiamento)** — s1 Lead: "Vou pensar." (e nada mais) · AMBIGUOUS (objeção
   vs adiamento neutro) · evidência fraca · erro: anotar `trust_authority` por hábito.
10. **Unknown (reação)** — s1 Lead: "Está caro." s2 Closer: "Temos desconto à vista." s3 Lead:
    "[inaudível]" (call termina) · episódio `price`; resolução `unknown` · reação ilegível · erro:
    `unresolved`.
11. **Unknown (categoria)** — s1 Lead: "Não sei se isso encaixa agora pra gente." · episódio com
    categoria UNKNOWN (preço? momento? necessidade?) se nada no contexto decide; AMBIGUOUS se o
    contexto sustenta duas leituras específicas · erro: escolher uma.
12. **N/A** — call inteira sem nenhuma objeção · call ABSENT; demais perguntas N/A · revisão
    completa feita · erro: ABSENT sem ler a call toda.
13. **Parcial** — s1 Lead: "O total está ok, mas a entrada pesa." · `partially_resolved` se for a
    última resposta substantiva após o handling · aceita um aspecto e mantém outro · erro:
    `resolved`.
14. **Closer citando** — s1 Closer: "Você disse que estava caro, certo?" · não é âncora; se houver
    episódio aberto, é contexto · erro: abrir episódio no closer.
15. **Speaker incerto** — s1 [speaker unknown]: "Isso está caro." · não pode ancorar; registrar
    UNKNOWN para o trecho · erro: assumir que é o lead.
16. **Adiado e retomado** — s1 Lead: "O preço está alto." s2 Closer: "Vamos olhar a implantação
    primeiro e depois volto no preço." (s3–s8 sobre implantação) s9 Closer: "Voltando ao preço,
    podemos parcelar." s10 Lead: "Com esse parcelamento dá." · um episódio `price`: objeção [s1],
    contexto [s2, s9, s10], `resolved`; s3–s8 não entram · s2 é adiamento explícito (fio parked), não
    closure · erro: fechar o fio em s3 e abrir outro em s9.
17. **Aparte de terceiro no meio da objeção** — s1 Lead: "Sobre o preço…" s2 Outro participante:
    "Preciso sair às 15h." s3 Lead: "…ficou acima do orçamento." · âncora s1, objeção [s1, s3] · s2
    é aparte que não muda o assunto · erro: âncora em s3.

## Future category template

Um arquivo/seção por categoria, preenchido **depois** do workshop de taxonomia:

```
## CATEGORY_NAME

Definition:
Positive signals:
Negative signals:
Often confused with:
Strong example (sintético):
Negative example (sintético):
Ambiguous example (sintético):
Notes:
```

## Pilot instructions

D3: **3–5 calls reais autorizadas**.

- A e B anotam **às cegas**, cada um sozinho, sem ver a anotação do outro, o Outcome, o CRM ou
  qualquer output de modelo. O adjudicador é uma terceira pessoa.
- Leia a call inteira primeiro; depois anote.
- Durante o pilot registre: dúvidas, trechos em que a guideline não decidiu, campos difíceis,
  tempo por call, e (na adjudicação) o tipo de cada divergência e propostas de mudança.
- **Não altere a guideline no meio de uma call nem da rodada.** Correções viram uma nova versão
  (v0.1, …) registrada, aplicada à rodada seguinte.

## What annotators must not do

- Usar Outcome do CRM, `current_stage` ou procurar venda posterior.
- Usar nome do cliente ou dados fora da call.
- Inferir emoção ou intenção sem fala que sustente.
- Completar trechos do transcript.
- Assumir que silêncio = aceitação ou que resposta do closer = resolução.
- Marcar categoria por palavra-chave.
- Usar modelo/LLM para decidir qualquer rótulo.
- Ver a anotação do outro anotador antes de enviar a sua.
- Corrigir speaker ou papel dos participantes na anotação.

## Open decisions

| # | Decisão |
|---|---|
| D3 | pilot de dupla anotação; thresholds só depois |
| D6 | semântica comercial final de `resolution_status` (inclui "ainda preciso ver se consigo pagar") |
| TAX | taxonomia final; enum v0 é provisório |
| GS-1 | como pontuar episódios gold AMBIGUOUS em detection |
| GS-2 | detection particionada por categoria antes da taxonomia |
| GS-3 | ponteiro de justificativa de resolução: obrigatório ou opcional |
| GL-1 | resistência que o lead atribui a terceiro ("meu sócio vai achar caro"): quando o lead a assume como barreira dele, é PRESENT; quando só relata ou discorda, não é. A fronteira precisa ser validada no pilot |
| GL-2 | adiamentos vagos ("vou pensar", "vou ver") sem outra fala: v0 marca AMBIGUOUS; o pilot deve dizer se isso é frequente e se precisa de regra própria |
