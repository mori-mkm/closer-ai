# Golden Set & Annotation Protocol v1

Status: **DRAFT — pré-pilot.** Nenhum dado real anotado; nenhuma ferramenta, schema executável ou
dependência adotados. Decisões abertas (D3, D6, taxonomia) não são resolvidas aqui.

## Purpose

Responder: *qual é o gabarito humano confiável contra o qual a futura IA de Call Intelligence será
medida?* Primeiro alvo: `ObjectionEpisode`
([`OBJECTION_EPISODE_V1_PROPOSAL.md`](../domain/OBJECTION_EPISODE_V1_PROPOSAL.md)).

Princípios (vêm do contrato do AI Closer e do
[`OPEN_SOURCE_REUSE_AUDIT.md`](../references/OPEN_SOURCE_REUSE_AUDIT.md)): evidência verificável
por `segment_id`; `unknown`, `ambiguous` e N/A são respostas legítimas; rótulos negativos
explícitos; dito ≠ inferido; métricas por camada, nunca um score único.

## Scope

- **Dentro:** unidade de anotação, semântica de rótulos, evidência, dupla anotação, adjudicação,
  proveniência, privacidade, versionamento, camadas de avaliação, pilot.
- **Fora:** taxonomia final de objeções, valores finais de `resolution_status` (D6), thresholds de
  agreement (D3), ferramentas, schema executável, extractor, dados reais.
- Amostragem de calls: [`GOLDEN_SET_SAMPLING.md`](GOLDEN_SET_SAMPLING.md) (este protocolo não a
  repete).

## Definitions

- **Golden Set:** conjunto de calls anotadas por humanos **e adjudicadas**, usado como ground truth
  para medir sistemas de Call Intelligence.
- **Não é:** dado de treino de prompt por padrão; verdade de CRM; coleção de outputs de LLM;
  benchmark só sintético; dataset de Outcome.

Três artefatos que **nunca** se misturam:

| Artefato | O que é | Quem produz | É gold? |
|---|---|---|---|
| **RAW ANNOTATION** | leitura independente de um anotador | anotador A ou B | não |
| **ADJUDICATED GOLD** | resposta canônica de uma versão do dataset | adjudicador | **sim** |
| **MODEL PREDICTION** | saída de um extractor | run de modelo (com proveniência, D4) | não |

Uma model prediction nunca vira raw annotation nem gold por cópia. Uma raw annotation nunca é gold
sem adjudicação (mesmo quando A e B concordam, o adjudicador confirma).

## Relationship to ObjectionEpisode

O protocolo **não cria contrato novo**. A anotação produz, para cada episódio, os campos do
contrato — `category`, `objection_segment_ids` (âncora = `[0]`), `context_segment_ids`,
`resolution_status` (§6) — seguindo as regras dele: definição e objetor (§4, §5.4), closure e
recorrência (§5.1, §5.2), âncora (§5.3), listas como grounding (§7.2), resposta substantiva e
precedência (§9). Em cima disso, a anotação acrescenta só metadados de revisão: status do rótulo
(abaixo), notas observado/inferido e ponteiros de justificativa. Esses metadados **não** são campos
do `ObjectionEpisode`.

## Annotation unit

```
Call (uma call canônica, segmentação fixada)
 ├── call-level: anotável? escopo revisado, tier, rótulos negativos
 └── zero ou mais ObjectionEpisodes
```

Para cada call o anotador responde:

| # | Pergunta | Resposta (contrato + status) |
|---|---|---|
| 0 | A call é anotável? | não, se sem `role="lead"` (`unresolved_lead`, TD-14) ou transcript ilegível → registrar motivo; fica fora das métricas |
| 1 | Existe objeção? | episódios PRESENT; ou ABSENT (call sem episódios, após revisão completa); trechos AMBIGUOUS; trechos UNKNOWN (ininteligíveis — impedem ABSENT da call inteira) |
| 2 | Onde começa? | âncora (`objection_segment_ids[0]`), regra §5.3 |
| 3 | Evidência da existência | `objection_segment_ids` |
| 4 | Categoria | valor da taxonomia vigente, ou UNKNOWN / AMBIGUOUS |
| 5 | Houve resposta do closer? | segmentos do closer em `context_segment_ids`; nenhum → handling ABSENT |
| 6 | Onde está? | `context_segment_ids` |
| 7 | Houve reação do objetor? | segmentos do objetor em contexto |
| 8 | Onde está? | `context_segment_ids` (e ponteiro de justificativa, opcional) |
| 9 | `resolution_status` determinável? | valor pelo §9, ou `unknown` |
| 10 | Informação insuficiente / ambígua? | status UNKNOWN / AMBIGUOUS + nota |

## Label semantics

Cada pergunta recebe **um** status. O status é da anotação, não do contrato.

### Present
Há evidência positiva suficiente de que o fenômeno ocorreu. **Exige evidência** (`segment_id`s).
Sem evidência, não é PRESENT.

### Absent
O anotador **revisou o escopo relevante** e concluiu que o fenômeno **não** ocorreu. É um
**rótulo negativo**. Toda ABSENT declara o escopo revisado (ver "Full-call review"). ABSENT ≠
UNKNOWN: ausência de evidência sem revisão do escopo não é ABSENT.

### Unknown
A pergunta se aplica, mas o material não permite responder. Ex.: a objeção existe, a reação do
objetor é ininteligível → `resolution_status = unknown` (contrato §9.2). **Nunca** convertido em
negativo, `resolved`, 0 ou false.

### N/A
A pergunta não se aplica estruturalmente. Dentro do contrato atual: se a call é ABSENT para
objeções, categoria, handling e resolução são N/A (não há episódio). Uma call não anotável é N/A
para tudo. **Não** usar N/A para "closer não respondeu": isso é handling ABSENT, e a resolução
continua aplicável (depende do objetor, contrato §9.2).

### Ambiguous
Mais de uma interpretação plausível é sustentada pelo material. O anotador **não escolhe**:
registra as candidatas e a razão. Ex.: um trecho que pode ou não ser objeção; uma objeção que cabe
em duas categorias. Ambiguous é resposta final legítima, também no gold.

## Observed vs inferred

- **OBSERVED/SAID:** o que está no transcript. Só isso vira evidência canônica
  (`objection_segment_ids`, `context_segment_ids`).
- **INFERRED:** leitura do anotador além do dito. Fica em nota marcada como inferência, nunca como
  evidência nem como valor de campo.
- Ex.: "Vou conversar com meu sócio" sustenta que há outro stakeholder; **não** sustenta "o prospect
  não tem poder de decisão".

## Evidence rules

- **Unidade:** `segment_id` do `TranscriptSegment`, como no contrato (§7). Sem char spans, sem
  quote em texto livre como evidência. Timestamps (`start_ts`/`end_ts`) são derivados do segmento,
  não anotados.
- **Verificação determinística:** todo `segment_id` citado existe na Call; a âncora é do objetor
  (`role="lead"`); ordem e regras do contrato §12.1. A anotação registra o
  `segment_sequence_hash` da segmentação usada (contrato §11); segmentação diferente = anotação
  inválida para aquela Call (contrato §12.0).
- **Evidência de objeção** = `objection_segment_ids`. **Handling e reação** = segmentos de
  `context_segment_ids` (função por papel e julgamento, contrato §7.2) — sem novas listas.
- **Ponteiro de justificativa (opcional):** para `resolution_status`, o anotador pode apontar os
  `segment_id`s da resposta substantiva decisiva (§9.1). É metadado de revisão, para adjudicar
  divergências de resolução; não é campo do contrato.

## Full-call review

Assimetria:

- **PRESENT** pode ser demonstrado por evidência localizada: basta o trecho.
- **ABSENT** exige ter revisado **todo o escopo relevante** — para "a call não tem objeções", a call
  inteira. Um anotador que leu só parte da call não pode declarar ABSENT; declara o escopo revisado
  ou UNKNOWN.
- Resolução depende de segmentos posteriores (closure, reversão, §5.1/§9): leia até a closure do
  fio ou o fim da call antes de fixar `resolution_status`.
- Regra v1: **toda call do Golden Set é revisada por inteiro** pelos dois anotadores. Isso torna
  toda ABSENT de call-level válida.

## Double annotation workflow

```
Call ──► Anotador A ──► RAW A ─┐
Call ──► Anotador B ──► RAW B ─┴─► comparação ─► concordância / divergência ─► adjudicação ─► GOLD
```

- A e B trabalham **independentemente**; nenhum vê a anotação do outro antes de submeter.
- Nenhum dos dois vê o Outcome do Deal, o estado do CRM nem outputs de modelo (ver "Outcome
  interaction").
- Submissão é final para a RAW; correções depois viram nova RAW, não edição.
- **Comparação RAW A × RAW B:** pareia episódios **só por sobreposição de `objection_segment_ids`
  dentro da mesma call** — sem particionar por categoria, para que divergências de categoria e
  episódios de categoria AMBIGUOUS/UNKNOWN sejam pareados e classificados como CATEGORY, não como
  DETECTION. O objetor não depende de julgamento (é o speaker da âncora). Episódio sem par =
  divergência DETECTION; mais de um par = BOUNDARY. Depois compara campo a campo e classifica
  (abaixo). Pode ser feita manualmente no pilot. (O matching particionado do contrato §12.2 é para
  avaliar modelo contra gold, não para comparar anotadores.)

## Adjudication

- **Recebe:** a Call (segmentos), RAW A, RAW B, a lista de divergências com tipo, e o motivo de cada
  anotador quando houver.
- **Pode:** aceitar A; aceitar B; produzir uma terceira leitura; marcar UNKNOWN, AMBIGUOUS ou N/A.
- **Não é** "escolher quem acertou"; não há voto majoritário automático nesta fase.
- Concordância entre A e B **também** passa pelo adjudicador (confirmação), porque dois anotadores
  podem concordar num erro de guideline.
- **Saída:** o gold canônico daquela Call para aquela versão do dataset, com o motivo de cada decisão
  divergente. Divergências que revelam falha de guideline viram item de revisão da guideline.

## Disagreement taxonomy

| Tipo | Quando |
|---|---|
| **DETECTION** | um anotador tem o episódio, o outro não (inclui PRESENT × AMBIGUOUS) |
| **BOUNDARY** | ambos têm o episódio; divergem em âncora, `objection_segment_ids` ou `context_segment_ids` (inclui split/merge, contrato §12.4) |
| **CATEGORY** | divergem na categoria (inclui valor × UNKNOWN × AMBIGUOUS) |
| **HANDLING** | divergem sobre quais segmentos do closer respondem à objeção |
| **RESOLUTION** | divergem em `resolution_status` |
| **APPLICABILITY** | divergem entre PRESENT / ABSENT / UNKNOWN / N/A (inclui "call anotável?") |

Uma divergência pode ter mais de um tipo. Os tipos servem para achar onde a guideline falha.

## Case tiers

Metadado por call (ou por episódio), atribuído na adjudicação. **Não altera o gold.**

| Tier | Significado |
|---|---|
| `happy_path` | evidência clara |
| `missing_context` | informação incompleta (call truncada, reação ilegível, fio que continua fora da call) |
| `ambiguous` | múltiplas leituras plausíveis |
| `adversarial` | parece um evento/categoria superficialmente, mas não deve ser rotulado assim |

Sem percentuais mínimos por tier.

## Negative gold

O gold registra também **ausências conhecidas**, para medir falsos positivos/alucinação:

- **Call-level:** "nenhum episódio de objeção" (ABSENT, após revisão completa).
- **Por categoria (quando houver taxonomia):** `expected_absent` com as categorias que a call foi
  revisada para e não contém.
- **Por trecho (adversarial):** segmentos que parecem objeção e não são (ex.: closer citando a
  objeção — nunca âncora, contrato §12.1 regra 2 e §14; objeção de terceiro, §5.4), registrados como "não deve ser
  episódio".

Estrutura de capacidade, não schema final: o formato do `expected_absent` por categoria depende da
taxonomia.

## Falsifying expectations

Toda categoria ou regra importante tem ao menos um caso que derruba uma implementação superficial:
um caso em que o sinal superficial está presente e o rótulo correto é outro. Ex.: um detector
lexical de preço precisa encarar uma fala que menciona preço mas **não** expressa objeção ativa
naquele momento ("antes eu achava caro, mas…"). Outros alvos naturais do contrato: closer citando a
objeção, objeção de outro participante (§5.4), recorrência vs reabertura (§5.2), reversão imediata
(§5.1), interjeição após aceitação (§9.2). Esses casos entram como tier `adversarial` e quase
sempre carregam rótulos negativos.

## Roles and leakage prevention

| Papel | Faz |
|---|---|
| **GUIDELINE_AUTHOR** | escreve e revisa a guideline/taxonomia |
| **ANNOTATOR** | produz RAW (A ou B) |
| **ADJUDICATOR** | produz o GOLD |
| **MODEL_AUTHOR** | escreve prompt/extractor e roda avaliações |

- **Regras rígidas (não são riscos registráveis):**
  - A e B são pessoas diferentes;
  - o ADJUDICATOR de uma call **não** é o anotador A nem B daquela call.
- **Escala mínima do pilot: 3 pessoas** (A, B, adjudicador). GUIDELINE_AUTHOR pode acumular com
  ADJUDICATOR (registrado no manifest).
- A mesma pessoa não deve ser, **para o mesmo dataset**, MODEL_AUTHOR e ANNOTATOR/ADJUDICATOR, nem
  escrever os exemplos e o gabarito que avaliam o próprio modelo.
- Se a equipe for pequena e alguém acumular papéis, **registrar no manifest** como risco do
  dataset (ex.: "adjudicator = guideline author"), nunca omitir.
- Casos sintéticos nunca são maioria do gold, e quem escreve prompt/guideline não escreve o gold
  sintético que avalia seu próprio trabalho.

## Dataset provenance

Cada versão registra (manifest simples, sem PII, no padrão de `data/manifests/`):

- `dataset_version`, `annotation_protocol_version`, `guideline_version`, `taxonomy_version`;
- por call: `call_id`, `segment_sequence_hash`, `normalizer_version` (contrato §11), tier, se
  anotável (e motivo), ids das RAW A/B e da adjudicação, pseudônimos dos anotadores/adjudicador e
  seus papéis, datas de anotação/adjudicação;
- sobreposição de papéis e outros riscos conhecidos;
- quantidade de casos sintéticos vs reais.

Sem serviço de proveniência: um arquivo versionado por versão do dataset.

## Privacy and data handling

| Onde | O que |
|---|---|
| **Armazenamento privado autorizado** (ex.: OCI, [`OCI_SHARED_STORAGE.md`](../data/OCI_SHARED_STORAGE.md)) | transcripts reais, áudio, RAW A/B e GOLD de calls reais (contêm notas em texto livre, que podem ter PII) |
| **Git** | este protocolo, guidelines, schemas futuros, exemplos **sintéticos**, manifests sem PII |
| **Nunca no Git** | transcript real, áudio, PII, notas de anotação de calls reais — mesmo com o repositório privado |

Referências a dado real no Git usam só ids/fingerprints (`call_id`, `segment_sequence_hash`), nunca
conteúdo. Segue [`PRIVACY_BOUNDARY.md`](../data/PRIVACY_BOUNDARY.md). Nenhuma anotação real começa
sem a autorização registrada em `docs/context/HUMAN_DECISIONS.md`.

## Versioning

- `v0-pilot` (calls do pilot D3), depois `v1`, `v1.1`, …
- Gold adjudicado é **imutável** dentro de uma versão. Qualquer correção gera nova versão (ou
  revision) com changelog curto; o gold antigo não é sobrescrito.
- Mudança de guideline, taxonomia ou protocolo que altere rótulos = nova versão do dataset.
- Mudança na segmentação de uma Call invalida a anotação daquela Call até reanotação (contrato
  §12.0).
- Toda avaliação cita a `dataset_version` usada.

## Evaluation layers

Métricas reportadas **separadamente**. **Não há score composto** ("AI Closer Score = 87"). Um
agregado só existirá se houver motivo comercial claro, e nunca substituindo as camadas.

Estas camadas avaliam um **extractor futuro** contra o gold. **Nenhuma é calculada no pilot** nem
faz parte dos critérios de saída do pilot; Category espera a taxonomia e Handling/resolution
espera D6.

### Structural
Parse válido, campos obrigatórios, ids re-derivados, todos os `segment_id` existentes (contrato
§12.1). Run com qualquer saída inválida é INVALID para métricas canônicas (contrato §12.1.1).

### Detection
Precision/recall/F1 de episódios com o matching do contrato (§12.2: partição por call, categoria e
objetor; candidato exige sobreposição de `objection_segment_ids`; atribuição maximum-cardinality),
TP/FP/FN convencionais (§12.3), split/merge como diagnóstico (§12.4), N/A e agregação micro
(§12.6). **OPEN:** como tratar episódios gold AMBIGUOUS (proposta: predições que caem neles não são
TP nem FP e são contadas à parte) e a partição por categoria enquanto a taxonomia não existe
(proposta: detectar sem particionar por categoria no pilot). Validar no pilot.

### Category
Quando a taxonomia existir: matriz de confusão e P/R/F1 **por categoria**, com contagens. Médias
macro/micro só como complemento, nunca escondendo classes pequenas. Episódios com categoria gold
UNKNOWN ou AMBIGUOUS ficam fora e são contados à parte.

### Grounding
A evidência predita aponta para evidência gold/verificável? Candidatos: igualdade exata de âncora,
sobreposição de segmentos (Jaccard de `objection_segment_ids` e do episódio inteiro, contrato
§12.5). **Sem threshold antes do pilot.**

### Handling / resolution
Só depois de D6. Separada de detection: matriz de confusão de `resolution_status` sobre os TPs
(contrato §12.5), com kappa **N/A** quando indefinido.

### Negative cases
Taxa de falsos positivos / achados sem suporte nos rótulos negativos explícitos (calls ABSENT,
`expected_absent`, trechos adversariais).

### Uncertainty
O sistema preserva `unknown`, AMBIGUOUS e N/A quando o gold os tem? Reporte simples: contagem de
casos em que o gold é UNKNOWN/AMBIGUOUS e a predição afirma um valor definido (excesso de
confiança), e o inverso.

## Pilot protocol

D3 do contrato: **~3–5 calls reais autorizadas**, dupla anotação completa, adjudicação.

- **Objetivo:** validar o protocolo, não medir o modelo. Descobrir: se a guideline é aplicável,
  categorias confusas, campos impossíveis de anotar, tipos de divergência dominantes, se a
  adjudicação funciona e se a evidência por `segment_id` é suficiente.
- **Pré-condições:** autorização de dados registrada; calls "ready for annotation"
  ([`REAL_CALL_VALIDATION_KIT.md`](../data/REAL_CALL_VALIDATION_KIT.md)); guideline v0 escrita;
  papéis atribuídos e sobreposições registradas.
- **Durante:** registrar tempo por call, dúvidas dos anotadores e cada divergência com tipo.
- **Sem thresholds** de agreement ou de qualidade.

## Golden Set growth

Depois do pilot, crescer por **cobertura**, não por contagem: positivos claros, negativos claros,
ambíguos, contexto faltante, adversariais, as categorias da taxonomia, e (quando relevante para
Outcome Intelligence) calls de Deals com outcomes diferentes — sempre anotadas às cegas. O plano de
amostragem existente ([`GOLDEN_SET_SAMPLING.md`](GOLDEN_SET_SAMPLING.md)) cita um alvo inicial;
este protocolo não fixa um número final.

## Outcome interaction

- Call Intelligence é anotada **às cegas** ao Deal: sem WON/REJECTED, sem estado do CRM, sem
  `current_stage`. Anotar sabendo o resultado cria leakage ("explicar" a call pelo resultado).
- O Outcome canônico ([ADR-001](../decisions/ADR_001-outcome-contract-v0.md)) é associado **depois**,
  na análise, pelo caminho canônico Call → `resolve_current_match` → Deal → `resolve_current_outcome`.
- `resolution_status` é in-call e **não** é outcome. UNKNOWN de Outcome nunca vira LOST/REJECTED.

## Future extractor contract

```
Canonical Transcript → LLM extractor → ObjectionEpisodes preditos → validação determinística → comparação com o Golden Set
```

O extractor deverá: devolver referências de evidência (`segment_id`s), não texto; preservar
`unknown` e não inventar categoria; registrar proveniência no run (modelo, prompt, versões,
`segment_sequence_hash` — contrato §11, D4); falhar explicitamente quando a saída for truncada;
nunca silenciar erros de validação (run INVALID, §12.1.1). Structured output é requisito
conceitual; nenhum framework escolhido.

## Deferred tooling

Label Studio, Instructor, Promptfoo, DeepEval, Langfuse: **adiados**. Cada um será avaliado contra
uma necessidade concreta deste protocolo (ex.: se o pilot mostrar que planilha/arquivo não bastam
para dupla anotação por segmento, avaliar Label Studio). O protocolo não se adapta à ferramenta.

## Machine-readable schema

Decisão: **A — só o schema conceitual agora.** JSON Schema/Pydantic (opção B) depois de D3/D6,
porque o pilot pode mudar campos (status por pergunta, ponteiros de justificativa, formato de
AMBIGUOUS e de `expected_absent`) e D6 pode mudar `resolution_status`. A opção C (manifest) já está
coberta pelo template existente em `data/manifests/`; não há ganho em um schema novo agora.

## Open decisions

| # | Decisão | Dono (ver contratos) |
|---|---|---|
| D3 | pilot de dupla anotação; thresholds de agreement só depois | contrato `ObjectionEpisode` §19 |
| D6 | semântica final de `resolution_status` | contrato §19 |
| TAX | taxonomia final de objeções (externas são só referência) | contrato §19 / guideline author |
| GS-1 | como pontuar episódios gold AMBIGUOUS em detection | a validar no pilot |
| GS-2 | detection particionada por categoria antes da taxonomia existir | a validar no pilot |
| GS-3 | ponteiro de justificativa de resolução: obrigatório ou opcional | a validar no pilot |
| GS-4 | quem ocupa cada papel e quais sobreposições são aceitáveis | equipe |
| DATA | autorização de dados reais para o pilot | `docs/context/HUMAN_DECISIONS.md` |

## Exit criteria for pilot

O pilot termina quando for possível responder, com os registros do pilot:

- Os anotadores conseguem aplicar a guideline sem improvisar regras?
- A evidência pode ser marcada deterministicamente por `segment_id`?
- Quais tipos de divergência dominam, e quais são falha de guideline?
- Quais campos/status precisam mudar (GS-1..GS-3)?
- D3 produziu informação suficiente para estabilizar o schema?
- D6 foi resolvida ou continua explicitamente bloqueante?
- Anotação e adjudicação podem ser repetidas de forma consistente por outras pessoas?

Nenhum threshold numérico (ex.: kappa > X) nesta fase.

## Next steps

1. Registrar autorização de dados e selecionar 3–5 calls do pilot (sampling plan).
2. GUIDELINE_AUTHOR escreve a guideline v0 no formato de entrada por código (reuse audit, ADAPT A3):
   definição, sinais positivos/negativos, confusões comuns, exemplos fraco × forte, dito × inferido.
3. Rodar o pilot, adjudicar, registrar divergências.
4. Revisar este protocolo e o contrato; só então JSON Schema/Pydantic e harness de avaliação.
