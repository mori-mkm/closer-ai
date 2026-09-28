# Sales Knowledge Retrieval & RAG v0.1 — Proposal

Status: **PROPOSAL — não implementado.** Nenhum código, dependência, índice, embedding, vector DB,
prompt ou chamada de LLM é criado por este documento. Nenhum contrato de domínio muda.

## Purpose

Responder, com o menor sistema possível:

> Como o AI Closer deve levar conhecimento da Sales Knowledge Base a um LLM que classifica
> ObjectionEpisodes, sem transformar conhecimento externo em evidência, sem forçar classificação e sem
> infraestrutura que ainda não provou utilidade?

E deixar desenhado o experimento que decide se retrieval ajuda:

```
E0 transcript only  vs  E1 + taxonomy/guideline  vs  E2 + knowledge (full)  vs  E3 + knowledge (selected)  [vs E4 semantic, só se justificado]
```

Resposta curta: **v0.1 não precisa de retrieval semântico, embeddings nem vector DB.** Com 8 unidades
pequenas, a menor solução é **carregar todas as 8 em forma de "cartão de classificação"** (seções
selecionadas por heading). Seleção determinística (E3) é um experimento de economia de tokens, não um
pré-requisito. Semântico/híbrido fica DEFER até existir corpus maior ou evidência de que E2/E3 falham.

## Current state

| Item | Estado | Onde |
|---|---|---|
| Sales Knowledge Base v0.1 | 8 units PROVISIONAL + `SOURCES.md` | `docs/knowledge/sales/` |
| Categorias | 8 **candidatas** (CIT-M3); enum do domínio = v0 (`price`, `timing_priority`, `trust_authority`, `no_need`, `other`) | proposal de taxonomia; `src/closer_ai/domain/objection.py` |
| `ObjectionEpisode` v1 | proposta, não implementada (D7 BLOCKED até D3 + D6) | `docs/domain/OBJECTION_EPISODE_V1_PROPOSAL.md` |
| Extractor | só `RuleBasedObjectionExtractor` (keyword v0) atrás do Protocol `ObjectionExtractor` | `src/closer_ai/ai/objection_extraction.py` |
| Golden Set real | não existe (pilot D3 depende de dado autorizado) | protocolo v1 |
| RAG / retrieval / LLM extractor | inexistentes | — |

## Constraints

- Evidência = `segment_id` da Call (contrato §7); proveniência no run, não no episódio (D4).
- `unknown` / AMBIGUOUS / N/A são respostas legítimas; nada vira default silencioso.
- Sem `confidence` no contrato (§13).
- Call Intelligence é cega a Deal/Outcome/CRM (protocolo, ADR-001).
- Audit: RAG/vector DB fora de escopo até necessidade; ferramentas (promptfoo, Instructor, Langfuse,
  Label Studio) adiadas; nada de "decida e siga", nada de score forçado.
- Dado real: privado, nunca no Git; LLM em nuvem com transcript real depende de autorização registrada.

## Evidence boundary

```
knowledge defines          transcript proves occurrence
```

- A Knowledge Base responde "o que é PRICE_BUDGET, quando não usar, com o que se confunde".
- Ela **nunca** responde "esta call contém PRICE_BUDGET". Ocorrência só se afirma com `segment_id`s da
  Call.
- **Retrieval candidate ≠ classification result.** Estar no contexto não é voto a favor da categoria.
- Garantia estrutural (não só instrução de prompt): o campo de evidência da saída só aceita `segment_id`s
  que existem na Call; o validator rejeita qualquer outra coisa (grounding §12.1). Conhecimento não tem
  `segment_id`, portanto **não pode** ocupar o lugar de evidência.

## Corpus characteristics

Medido em `main@a586348`:

- 8 knowledge units, 97–116 linhas cada, ~36 KB de Markdown no total (bytes; tokens **não medidos** —
  dependem do tokenizer).
- Mesma estrutura em todas: 16 seções `##` fixas, 4 campos de metadata.
- Conteúdo em PT-BR com termos EN embutidos nas definições.
- Crescimento previsto: nenhum comprometido. Seller response / prospect reaction estão fora da v0.1.
- Taxa de mudança: baixa, por PR.

Consequência: o "corpus" cabe inteiro num contexto de LLM comum; o problema de recall de retrieval
**não existe** se tudo for carregado.

## Do we need RAG?

Dois desenhos de classificador são possíveis, e a resposta depende deles:

| Desenho | Como funciona | Precisa de query de retrieval? |
|---|---|---|
| **S — single-pass por call** | o LLM lê a call inteira e produz episódios (detecção + fronteira + categoria + resolução) | não: o modelo precisa de **todas** as categorias para detectar; não há span antes da detecção |
| **T — two-stage** | estágio 1 detecta candidatos (âncora + segmentos); estágio 2 categoriza cada candidato com conhecimento seletivo | sim: o candidato é a query |

Dois argumentos distintos:

1. **Detecção precisa de todas as categorias.** Decidir se um trecho é objeção (e não pergunta neutra)
   exige as regras negativas de todas as categorias; antes da detecção não existe span para servir de
   query. Isso vale para S e para o estágio 1 de T.
2. **Fronteira e resolução são call-level** (closure, parked, recorrência e resolução dependem de
   segmentos posteriores, §5.1/§9). Isso **não** impede T — o estágio 1 também pode ler a call inteira
   —, mas significa que T ainda faz uma passada call-level com conhecimento completo, e só a
   categorização do estágio 2 poderia usar conhecimento seletivo.

Logo, retrieval seletivo só economiza no estágio 2 de T, ao custo de uma segunda chamada. Para v0.1:
**S**; T só se a eval mostrar que categorização precisa de contexto focado ou que o custo de S é
inaceitável (RAG-O3).

**Conclusão (RAG-M1):** "RAG" v0.1 = **injeção determinística de conhecimento curado** (augmentation sem
retrieval semântico). Retrieval seletivo é experimento (E3), semântico é DEFER.

## Retrieval approaches considered

| Critério | A — Full context (8 cartões) | B — Determinístico/lexical | C — Semântico (embeddings) | D — Híbrido |
|---|---|---|---|---|
| Implementação | ler 8 arquivos, projetar seções | A + listas de pistas por unit + regra de seleção | A + modelo de embedding + índice | B + C + fusão de ranking |
| Complexidade | mínima | baixa | média | a maior |
| Token cost | fixo, o maior dos quatro para o bloco de conhecimento | menor, variável | menor, variável | menor, variável |
| Recall do conhecimento necessário | **100% por construção** | depende das pistas; risco com paráfrase | depende do modelo; risco com PT-BR coloquial | melhor de B/C, não garantido |
| Precision do contexto | baixa (tudo entra) | média | média | média |
| Risco de perder conhecimento importante | nenhum | real (miss silencioso se não houver fallback) | real | real |
| Determinismo | total | total | depende de modelo/versão do embedding | parcial |
| Facilidade de eval | trivial (não há retrieval a avaliar) | Recall@selected simples | exige benchmark de embedding | o mais difícil |
| Manutenção | nenhuma além da KB | manter pistas em sincronia com a KB | reindexar a cada mudança; versionar modelo | ambos |
| Dependências | nenhuma | nenhuma (stdlib) | modelo de embedding + lib | idem |
| Infraestrutura | nenhuma | nenhuma | índice (em memória basta) | idem |
| Adequação a 8 unidades | **alta** | média (economia pequena, risco novo) | baixa | baixa |

"Signals are contextual cues, not keyword classifiers" continua valendo em B: pistas lexicais servem só
para **selecionar conhecimento** (orientado a recall), nunca para decidir categoria.

## Query unit

Só existe query em E3/T. Avaliação:

| Query | Prós | Contras | Decisão |
|---|---|---|---|
| transcript inteiro | nada se perde | ruído máximo; seleciona tudo | não (equivale a A, mais caro) |
| só o texto da objeção | compacto | perde o que distingue preço×valor, timing×brush-off, autoridade×menção, pergunta×objeção (o que vem depois decide) | não |
| âncora + `objection_segment_ids` + `context_segment_ids` do candidato | é a unidade do contrato; contém a continuação e a reação | depende de o estágio 1 ter fronteira boa | **sim (proposta)** |
| observação estruturada ("lead diz X sobre Y") | curta | é saída de outro modelo; inferência antes da evidência | não em v0.1 |

**Query shape conceitual (RAG-M2):** texto dos segmentos do candidato **em ordem de `segment_index`**,
cada um com `segment_id` e papel do speaker, mais uma janela curta de segmentos vizinhos se o estágio 1
não fechou a fronteira. Tamanho da janela = parâmetro de eval, não constante escolhida agora. Sem schema.

## Retrieval unit

**Documento inteiro = unidade de conceito; o que entra no prompt é uma projeção por seção** (RAG-M3):

- Não há chunking em v0.1: cada arquivo tem um conceito, ~4–5 KB, e o que importa (regras negativas)
  fica **no mesmo arquivo** que o positivo. Chunking automático separaria "Use when" de "Do not use when"
  — exatamente o que causaria RAG positive-only.
- Projeção = escolher seções pelo nome do heading `##` (determinístico, sem parser novo além de dividir
  por heading).

Cartão de classificação (seções incluídas):

| Seção | No cartão? | Por quê |
|---|---|---|
| Metadata: `concept_id`, `status` | sim | identidade; PROVISIONAL visível |
| Metadata: `version`, `source_strength` | não no prompt; sim no run | proveniência, não ajuda a classificar |
| Definition | sim | |
| Use when / Do not use when | sim | fronteira positiva e negativa |
| Minimum transcript evidence | sim | o que precisa estar dito |
| Negative / falsifying signals | sim | conhecimento negativo |
| Often confused with | sim | rivais explícitos |
| Ambiguous examples | sim | ensina abstenção |
| Observed vs inferred risks | sim | o que **não** afirmar |
| Positive examples / Counterexamples | **variável de eval** | podem ajudar ou induzir cópia lexical; testar com/sem |
| Positive signals | **variável de eval** | risco de virar keyword list para o modelo |
| Framework mappings, Source-backed notes, Sources, Open questions | não | referência humana; custo sem ganho de classificação |

## Negative knowledge

Regra: **nenhum cartão entra sem suas seções negativas.** "Do not use when", "Negative / falsifying
signals", "Ambiguous examples" e "Observed vs inferred risks" são obrigatórias no cartão; unit sem elas
é **malformed** (ver Failure behavior).

Exemplo: "Quanto custa?" → o cartão PRICE_BUDGET traz, junto da definição, "pergunta de preço ≠ objeção".
Além dos cartões, o bloco de regras traz os princípios globais da KB/guideline (tópico ≠ objeção; sinais
não são keywords; status quo não é categoria; OTHER/UNKNOWN/AMBIGUOUS/NO_OBJECTION).

## Confusion-aware retrieval

Só relevante em E3. Estratégias:

| Estratégia | Como | Avaliação |
|---|---|---|
| 1. vizinhos por similaridade | o retriever devolve o que for "parecido" | rivais aparecem por acaso; exige C/D |
| 2. candidato primário + vizinhos explícitos | seleção lexical dá candidatos; adiciona-se cada categoria listada em "Often confused with" deles | determinístico; usa conhecimento curado; listas já são simétricas na KB |

**Proposta (RAG-M5): estratégia 2**, sem grafo — a lista de "Often confused with" de cada arquivo basta.
Observação: com 8 unidades e listas de 3–6 vizinhos, "primário + vizinhos" frequentemente cobre 4–7
categorias. Se na eval o conjunto médio ficar perto de 8, E3 não economiza nada e **A vence**.

## Top-k / candidate strategy

- **E2 (padrão):** todas as 8 — não há k.
- **E3:** **sem k fixo.** Conjunto = (units cujas pistas casam com a query) ∪ (seus vizinhos de
  confusão). Top-1 é rejeitado por construção: esconderia ambiguidade ("não temos orçamento agora,
  talvez no próximo trimestre" precisa de PRICE_BUDGET **e** TIMING_PRIORITY).
- **Conjunto vazio → fallback para as 8**, registrado no run (não é erro silencioso nem abstenção
  automática).
- Como avaliar depois (RAG-M4): Recall@selected e distribuição do tamanho do conjunto por episódio gold;
  comparar E2 × E3 no mesmo gold. k (ou cap) só vira parâmetro se houver motivo medido.

## Context assembly

Forma conceitual (não é o prompt):

```
[TASK RULES]                 ← guideline/contrato: o que é objeção, âncora, listas, resolução,
                               abstenção, "knowledge não é evidência"
[FACTS FROM CALL]            ← transcript: segmentos com segment_id, índice e papel do speaker
                               (única fonte de ocorrência)
[EXTERNAL KNOWLEDGE — NOT FROM THIS CALL]
   knowledge_version: <digest>
   CARD objection_category.PRICE_BUDGET (PROVISIONAL)
     definition / use_when / do_not_use_when / minimum_evidence /
     falsifying_signals / often_confused_with / ambiguous_examples / inferred_risks
   CARD ...
[OUTPUT REQUIREMENTS]        ← evidência só por segment_id; abstenção permitida; formato
```

- Os blocos são delimitados e rotulados; exemplos da KB são marcados **sintéticos** para não serem
  confundidos com falas da call.
- Ordem estável (regras e conhecimento antes do transcript) favorece prompt caching do provedor, se
  existir; não é requisito.
- **Proibido no contexto:** Deal, Outcome, stage, dados de CRM, resultado de outras calls (ver Leakage).

## Abstention

Requisitos:

1. A saída admite, por candidato: uma categoria (8 candidatas ou `OTHER`), **AMBIGUOUS** (com as
   candidatas), **UNKNOWN**; e, por call, **NO_OBJECTION** (nenhum episódio).
2. **Retrieval candidate ≠ classification result**: estar no contexto nunca obriga escolher a categoria;
   E2 injeta as 8 justamente para não sugerir nenhuma.
3. Ausência de conhecimento relevante (E3 vazio) → fallback, nunca "escolha a mais próxima".
4. Abstenção excessiva também é erro: é medida (ver Evaluation plan), não otimizada por instrução.
5. Sem `confidence` numérico (contrato §13); AMBIGUOUS com candidatas é a forma de expressar dúvida.

## Provenance

Output conceitual por candidato (**não** altera `ObjectionEpisode`):

| Item | Onde vive | Nota |
|---|---|---|
| categoria ou status (AMBIGUOUS/UNKNOWN) + candidatas | predição no run | o contrato não tem AMBIGUOUS no enum; a forma de representá-lo em predição + GS-1 (como pontuar) fica aberta |
| `objection_segment_ids`, `context_segment_ids` | predição → `ObjectionEpisode` quando D7 existir | única evidência |
| `resolution_status` | idem | regras do contrato; D6 aberta |
| reasoning summary | **artefato privado do run**, opcional | texto livre pode conter trecho de transcript → nunca no Git; nunca evidência |
| `knowledge_refs` (concept_ids no contexto) | **run** (por predição ou por run) | D4: proveniência no run, **não** no episódio |
| knowledge version / digest, prompt, modelo, `segment_sequence_hash` | **run** | D4 + contrato §11 |

Label set: o classificador que usa os cartões produz labels **da taxonomia v0.1 candidata**, que não é o
enum do domínio. Até D7, essas predições vivem só em runs de eval, comparadas a um gold anotado **no mesmo
label set** (depende de CIT-O1). Não há mapeamento determinístico 8 → enum v0 (`trust_authority` se
divide).

## Versioning

Registrar no run, sem registry (RAG-M6):

- `knowledge_commit_sha` — commit do repo de onde a KB foi lida (rastreabilidade humana);
- `knowledge_context_digest` — sha256 do bloco de conhecimento exatamente como montado (reprodutibilidade:
  cobre projeção de seções e seleção);
- `concept_id`s + `version` de cada cartão incluído.

Regra: working tree da KB **sujo** no momento do run → run recusado (o SHA não descreveria o conteúdo).
"Prediction A foi produzida com Knowledge Base commit X, contexto de digest Y."

## Failure behavior

Preferência: **falhar explícito em vez de classificar em silêncio.**

| Estado | Comportamento |
|---|---|
| Nenhum conhecimento relevante (E3 vazio) | fallback para as 8; flag no run; classificação segue com abstenção permitida |
| Vários conceitos igualmente plausíveis | todos entram; a saída pode ser AMBIGUOUS; nunca desempate por ranking de retrieval |
| Knowledge unit malformed (seção obrigatória ausente, metadata faltando) | **run abortado** antes do LLM, com o arquivo e a seção |
| Source reference ausente/inválida (`source_id` fora de `SOURCES.md`) | run abortado (check barato; a KB é versionada, corrigir por PR) |
| Versão desatualizada / tree sujo / digest diferente do esperado num re-run | run recusado; comparação entre runs com digests diferentes é explícita, nunca silenciosa |
| Knowledge indisponível (arquivo ausente) | run abortado; **nunca** cair para "sem conhecimento" silenciosamente (seria outro braço do experimento) |

## Caching

Não é necessário: 8 arquivos locais pequenos, leitura trivial. Sem cache de aplicação, sem Redis.
Prompt caching do provedor (audit A6, "cached system blocks") é opcional e compatível com a ordem estável
do contexto; decidir quando houver runs em lote.

## Vector DB decision

| Opção | Precisa? |
|---|---|
| plain files lidos por run | **sim — é o v0.1** |
| in-memory (estruturas simples) | só o necessário para montar o contexto |
| lookup lexical simples | só em E3 |
| embeddings em memória | DEFER (E4) |
| FAISS / pgvector / vector DB gerenciado | **DEFER** — nenhum requisito; 8 documentos não justificam índice |

**RAG-M7: sem vector DB no v0.1.**

## Embedding decision

Nenhum modelo escolhido (semântico não justificado). Se E4 for aberto, critérios:

- qualidade em **PT-BR coloquial/comercial** (medida no gold, não em benchmark genérico);
- local × cloud (privacidade: embedding da **query** contém transcript; cloud exige autorização);
- custo; latência;
- **reprodutibilidade/versionamento**: modelo pinado, versão registrada no run, reindexação a cada troca;
- ganho de Recall@selected sobre E3 no mesmo gold.

## Local/cloud model compatibility

A arquitetura é **agnóstica ao modelo**: contexto em texto plano + saída estruturada validada
deterministicamente, atrás do Protocol `ObjectionExtractor` já existente (audit A6). Diferença prática:
modelos locais tendem a ter janelas e capacidade menores → o custo fixo de E2 pesa mais e E3 pode virar
necessário. Isso é resultado de eval, não motivo para adotar retrieval agora. Nenhum modelo/runtime
selecionado.

## Token budget

Onde os tokens vão (qualitativo, sem preços):

| Parte | Tamanho | Observação |
|---|---|---|
| transcript | provavelmente **dominante** em S (call inteira); tamanho real das calls desconhecido até o dado real | não reduzível por retrieval de conhecimento |
| task rules (guideline/contrato) | fixo, médio | igual em E1–E4 |
| conhecimento | E2: 8 cartões (subconjunto dos ~36 KB); E3: menos | a única parte que retrieval reduz |
| output | pequeno por episódio | |

Estratégia testável: medir tokens por braço no mesmo gold; E3 só compensa se (a) reduz tokens de forma
relevante **e** (b) Recall@selected não perde nada que E2 acerta. Se o transcript dominar, a economia de
E3 é marginal e A fica.

## Security boundary

- KB: conhecimento sintético/público → pode ficar no Git.
- Transcripts reais: privados; retrieval de conhecimento externo **não muda** nenhuma regra de privacidade.
- Enviar transcript real a LLM (ou embedding) em nuvem continua dependendo de autorização registrada
  (`docs/context/HUMAN_DECISIONS.md`). Nenhum upload de dado real é sugerido aqui.
- Artefatos de run com texto livre (reasoning, respostas brutas) são privados, como a anotação real.

## Knowledge leakage

- Inputs permitidos do Context Builder: segmentos da Call, cartões da KB, regras da guideline. **Nada
  mais.** Deal, Outcome, `current_stage`, CRM e outras calls não entram — nem como "contexto".
- O classificador nunca usa "Deal ganhou" para decidir `resolved`; resolução é in-call (contrato §9).
- A KB não pode ganhar conteúdo derivado de outcome ("categoria X correlaciona com perda") enquanto for
  usada para classificação: isso reintroduziria leakage pelo conhecimento. Outcome Intelligence acontece
  depois, sobre episódios já classificados.

## Golden Set boundary

- Predição de RAG **nunca** vira gold nem RAW annotation por cópia (protocolo).
- Anotadores A/B **não veem** saídas de modelo; RAG-assisted pre-annotation está fora do pilot.
- A KB em si é documento humano de referência (como a guideline). Quem escreveu KB/prompt não anota o gold
  que avalia o classificador baseado nela; se a equipe acumular papéis, registrar no manifest (protocolo,
  Roles and leakage prevention).
- Casos sintéticos (KB, calibration kit) não servem de eval de desempenho: só de teste de encanamento.

## Evaluation plan

Braços (mesmo gold, mesmo modelo, mesmo prompt exceto o bloco de conhecimento — ablação pareada):

| Braço | Contexto |
|---|---|
| E0 | task rules mínimas + transcript |
| E1 | E0 + guideline + lista de categorias com definição de uma linha |
| E2 | E1 + 8 cartões completos (Full context) |
| E3 | E1 + cartões selecionados (lexical + vizinhos de confusão, fallback para 8) |
| E4 | E1 + seleção semântica/híbrida — **só se** E3 perder recall ou E2 for caro demais |

E0→E1 mede o valor das **regras da guideline + nomes/definições curtas** (agrupados de propósito:
é o nível "taxonomy/guideline only" pedido; separá-los é variável secundária opcional); E1→E2 mede o
**valor do conhecimento**; E2→E3 mede o **custo/risco da seleção**; E3→E4 mede o valor do
semântico. Variáveis secundárias de E2: com/sem exemplos positivos; com/sem positive signals.

Métricas, **reportadas separadamente, sem score composto e sem threshold antes dos dados**:

1. **Detection** — P/R/F1 de episódios pelo matching do contrato (§12.2–12.6), micro, N/A regras.
2. **Category** — matriz de confusão e P/R por categoria, com contagens; gold UNKNOWN/AMBIGUOUS contado à
   parte.
3. **Evidence grounding** — validity rate (§12.1, §12.1.1); run INVALID → métricas canônicas N/A.
4. **Abstention quality** — gold definido × predição abstém (sub-confiança); gold UNKNOWN/AMBIGUOUS ×
   predição definida (excesso de confiança); NO_OBJECTION correto em calls ABSENT.
5. **Confusion errors** — erros restritos aos pares de "Often confused with" (ex.: PRICE×NEED_VALUE_FIT,
   TIMING×brush-off, AUTHORITY×menção a stakeholder, IMPLEMENTATION×pergunta técnica).
6. **Retrieval recall** — ver Retrieval metrics (E3/E4).
7. **Irrelevant-context rate** — ver Retrieval metrics.
8. **Knowledge-as-evidence violations** — contagem de saídas que tentam citar algo que não é `segment_id`
   da Call (deve ser 0 por construção do validator; reportar mesmo assim).

Pré-condição: **Golden Set real**, anotado no mesmo label set (CIT-O1), com D3 feito e autorização de
dados. Antes disso, só testes de encanamento com sintéticos. Amostra pequena → reportar contagens, sem
alegar significância.

## Retrieval metrics

Para E3/E4, por episódio gold:

- **Recall@selected** — a categoria gold está no conjunto? (gold AMBIGUOUS: todas as candidatas estão?)
- **Precision@selected** — fração do conjunto que é a categoria gold ou um vizinho de confusão listado.
- **Set size** — distribuição do tamanho do conjunto (se ≈ 8, E3 não se paga).
- **Confusion coverage** — quando o gold tem um rival listado, o rival também foi trazido?
- **Negative knowledge coverage** — as seções negativas da categoria gold **e** da categoria predita
  (quando errada) estavam no contexto? (Em E2 = 100% por construção.)
- **Irrelevant-context rate** — units no contexto que não são gold nem vizinhos do gold.
- **Fallback rate** — quantas vezes E3 caiu para as 8.

Nenhum target definido.

## Proposed v0.1 architecture

```
Canonical Call (segmentos com segment_id)          docs/knowledge/sales/objections/*.md @ commit X
            │                                                      │
            │                                   Context Builder: valida units, projeta cartões,
            │                                   (E3: seleciona + vizinhos), calcula digest
            └──────────────────────┬───────────────────────────────┘
                                   ▼
                     LLM classifier (single-pass por call; Protocol existente)
                                   ▼
                     Validator: grounding §12.1, label set, abstenção, run INVALID
                                   ▼
                     Predições no run (+ proveniência: modelo, prompt, KB sha/digest, concept_ids)
                                   ▼
                     Eval harness vs Golden Set humano  (nunca vira gold)
```

## Component boundaries

| Componente | Responsabilidade | Existe? |
|---|---|---|
| **Context Builder** | ler a KB, checar forma, projetar cartões, montar blocos rotulados, calcular digest; em E3, a seleção é uma função dele — **não há "Retriever" separado em v0.1** | novo (futuro) |
| **Classifier** | LLM atrás de `ObjectionExtractor`; recebe contexto pronto; não lê KB nem Deal | seam existe |
| **Validator** | grounding e ordem (§12.1), label set, abstenção bem-formada; nunca corrige | exigido pelo contrato |
| **Eval Harness** | braços E0–E4, métricas acima, N/A e INVALID | `evals/` existe para v0; v1 futuro |

Sem framework, sem serviço, sem classes antes do experimento.

## Decisions

| ID | Pergunta | Proposta |
|---|---|---|
| RAG-M1 | v0.1 precisa de retrieval semântico? | **Não.** Full context (8 cartões) é o padrão; semântico DEFER |
| RAG-M2 | Qual é a query? | Não há query em E2. Em E3/T: segmentos do candidato (âncora + listas, em ordem, com `segment_id`) + janela curta |
| RAG-M3 | Unidade de retrieval? | Arquivo inteiro como conceito; cartão = projeção por heading; **sem chunking** |
| RAG-M4 | Quantos conceitos? | E2: todos. E3: pistas ∪ vizinhos, sem k, fallback para 8; avaliado por Recall@selected e set size |
| RAG-M5 | Vizinhos de confusão participam? | Sim em E3, pela lista "Often confused with" (sem grafo) |
| RAG-M6 | Como registrar proveniência de conhecimento? | No run: commit SHA + digest do contexto + concept_ids/versions; nunca no episódio (D4) |
| RAG-M7 | Vector DB no v0.1? | **Não** |
| RAG-M8 | O que implementar primeiro? | Context Builder de E2 + checks de forma da KB, e os braços E0/E1 para comparação — só quando houver extractor LLM e gold (ver phases) |

Todas PROPOSED, para revisão humana.

## Open questions

| ID | Pergunta |
|---|---|
| RAG-O1 | Label set do experimento = gold do pilot (CIT-O1: 8 candidatas ou enum v0?). Se o gold usar o enum v0, os cartões v0.1 não mapeiam 1:1 |
| RAG-O2 | Como a predição representa AMBIGUOUS/UNKNOWN sem campo no contrato, e como pontuar (GS-1) |
| RAG-O3 | Single-pass (S) × two-stage (T): decidido pela eval de E2 |
| RAG-O4 | Exemplos positivos e positive signals no cartão ajudam ou induzem keyword matching? |
| RAG-O5 | Tamanho real das calls (dominância do transcript no custo) — só com dado real |
| RAG-O6 | Reasoning summary: guardar no run privado ou não produzir? |

## Implementation phases

Ajustado ao corpus atual (8 units) e aos bloqueios reais:

| Fase | Conteúdo | Gate |
|---|---|---|
| 0 | Check de forma da KB (seções obrigatórias, `source_id`s válidos) como teste pequeno; nenhum LLM | pode vir cedo; opcional |
| 1 | Extractor LLM single-pass (task própria, contrato `ObjectionEpisode`) com braços E0/E1/E2 via Context Builder | D7 (D3 + D6) e decisão de provedor/modelo |
| 2 | Eval pareada E0/E1/E2 no Golden Set real | gold real (D3, autorização) |
| 3 | E3 (seleção determinística + vizinhos) **só se** E2 for caro/limitado (ex.: modelo local) | resultado da fase 2 |
| 4 | E4 semântico/híbrido **só se** E3 perder recall de forma medida ou o corpus crescer muito | resultado da fase 3 |

Diferença para a sequência sugerida: full context **é** o sistema v0.1, não só um baseline, e retrieval
determinístico vem depois da eval, não antes — com 8 unidades não há o que otimizar antes de medir.

## Explicitly deferred

Retrieval semântico/híbrido; embeddings e escolha de modelo; vector DB (FAISS, pgvector, gerenciado);
chunking; cache de aplicação/Redis; frameworks (LangChain, LlamaIndex, Instructor, Promptfoo, Langfuse);
prompt final; seleção de LLM/provedor/modelo local; two-stage (T); RAG para seller response/prospect
reaction; RAG-assisted pre-annotation; qualquer mudança em `ObjectionEpisode`, enum ou schema.

## Recommended next task

Não implementar retrieval. Próximos passos que destravam o experimento:

1. Objection Annotation Guideline v0.1 (decidir CIT-O1 = label set do gold e do classificador).
2. Dry run do calibration kit → pilot D3 → D6.
3. Depois de D7: extractor LLM `ObjectionEpisode` com Context Builder E2 e braços E0/E1/E2.

Opcional e barato a qualquer momento: Fase 0 (check de forma da KB).
