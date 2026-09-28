# Sales Knowledge Base v0.1

Status: **v0.1 — PROVISIONAL.** 8 knowledge units de categorias de objeção candidatas. Nenhum RAG,
retriever, embedding ou índice existe. Nenhum enum do domínio muda.

## Purpose

Conhecimento comercial versionado, para uso futuro em:

- orientação de anotação (complementa a guideline, não a substitui);
- explicação de uma classificação para humanos;
- retrieval e classificação assistida por RAG;
- suporte a revisão/adjudicação humana.

## What this is

Conhecimento comercial **rastreável a fontes** ([`SOURCES.md`](SOURCES.md)), comprimido em uma unidade
por conceito: definição, quando usar, quando não usar, evidência mínima, confusões comuns, exemplos
sintéticos e força da fonte. Regras que são do AI Closer, e não da literatura, são marcadas **AC**.

## What this is not

- **evidência de transcript** — não prova nada sobre nenhuma call;
- **Golden Set** — exemplos daqui não são gold nem casos de eval;
- **schema de domínio** — o enum vigente continua `price`, `timing_priority`, `trust_authority`,
  `no_need`, `other` (`src/closer_ai/domain/objection.py`);
- **prompt** nem **model output**;
- **verdade de negócio** — categorias ainda não validadas no pilot (D3) nem pela operação;
- **ciência causal de vendas** — nenhuma fonte aqui sustenta "fazer X causa ganhar o deal".

## Evidence boundary

```
Knowledge   → define / explica / orienta a classificação
Transcript  → prova que algo aconteceu (segment_id da Call)
```

A base pode responder "o que é PRICE_BUDGET?", "quando usar?", "com o que se confunde?", "o que as
fontes dizem?". Ela **nunca** responde sozinha "esta call contém PRICE_BUDGET". Fonte externa nunca é
evidência de ocorrência. Um sistema que usar esta base cita conhecimento como justificativa de
**definição** e `segment_id`s como justificativa de **ocorrência**
([proposal, Evidence boundary](../../domain/CALL_INTELLIGENCE_TAXONOMY_V0_1_PROPOSAL.md#evidence-boundary)).

## Princípios comuns às 8 unidades

- **Objeção = resistência que funciona como barreira a avançar**, dita pelo lead. A noção ampla de
  resistência vem de `SRC_HUNT_BASHAW` (S1); a definição operacional ("preocupação que impede comprar ou
  avançar") de `SRC_HUBSPOT_OBJECTIONS` (S4). Tópico mencionado ≠ objeção.
- **Signals are contextual cues, not keyword classifiers.** Nenhuma palavra ("caro", "sócio",
  "contrato", "integração") decide categoria sozinha.
- **Categorize pelo que foi dito**, não pela causa provável. Se a causa só é inferível, a categoria é
  AMBIGUOUS/UNKNOWN (guideline).
- **Leia em sequência.** Resistência pode ficar clara (ou desaparecer) nas falas seguintes
  (`SRC_CLARK_PINCH`, S1). Por isso AMBIGUOUS é resposta legítima.
- Indecisão sem barreira dita ("preciso pensar") **não** tem categoria (`SRC_SCHURR` trata buyer
  indecision como algo a entender antes de responder; tratá-la como não-categoria é AC).
- Frameworks (BANT, Sandler, MEDDPICC, SPIN) ajudam a nomear dimensões; **dimensão de framework ≠
  objeção**.

## Como usar junto da guideline

| Pergunta | Onde |
|---|---|
| O que significa a categoria? Com o que se confunde? | esta base |
| É objeção? Quais segmentos? Âncora, fronteira, resolução? Como marcar AMBIGUOUS/UNKNOWN? | [`OBJECTION_ANNOTATION_GUIDELINE_V0.md`](../../evals/OBJECTION_ANNOTATION_GUIDELINE_V0.md) e [`ObjectionEpisode`](../../domain/OBJECTION_EPISODE_V1_PROPOSAL.md) |
| Dupla anotação, adjudicação, métricas | [`GOLDEN_SET_ANNOTATION_PROTOCOL_V1.md`](../../evals/GOLDEN_SET_ANNOTATION_PROTOCOL_V1.md) |

Em divergência, vale o contrato, depois o proposal, depois a guideline; esta base não corrige nenhum
deles.

## Index

Sources = sufixo do `source_id` em [`SOURCES.md`](SOURCES.md) (ex.: HUBSPOT = `SRC_HUBSPOT_OBJECTIONS`).

| Concept | Status | Main confusion | Sources |
|---|---|---|---|
| [PRICE_BUDGET](objections/PRICE_BUDGET.md) | PROVISIONAL | NEED_VALUE_FIT ("não sei se vale") · TIMING (ciclo de verba) | HUBSPOT, SCHURR, GONG, SANDLER |
| [TIMING_PRIORITY](objections/TIMING_PRIORITY.md) | PROVISIONAL | brush-off · PRICE_BUDGET (ciclo de verba) | HUBSPOT, GONG |
| [NEED_VALUE_FIT](objections/NEED_VALUE_FIT.md) | PROVISIONAL (fusão AC) | PRICE_BUDGET · IMPLEMENTATION | HUBSPOT, SPIN, AC |
| [AUTHORITY_INTERNAL_BUY_IN](objections/AUTHORITY_INTERNAL_BUY_IN.md) | PROVISIONAL | stakeholder mencionado · processo normal de decisão | HUBSPOT, GONG, MEDDPICC, SANDLER |
| [TRUST_RISK](objections/TRUST_RISK.md) | PROVISIONAL (fusão AC) | pedido de prova/case · IMPLEMENTATION · NEED_VALUE_FIT | HUBSPOT, AC |
| [COMPETITION_EXISTING_SOLUTION](objections/COMPETITION_EXISTING_SOLUTION.md) | PROVISIONAL | concorrente mencionado · NEED_VALUE_FIT (status quo) | HUBSPOT, MEDDPICC |
| [IMPLEMENTATION_INTEGRATION](objections/IMPLEMENTATION_INTEGRATION.md) | PROVISIONAL (operation-dependent) | pergunta técnica · TRUST_RISK | HUBSPOT |
| [TERMS_PROCESS](objections/TERMS_PROCESS.md) | PROVISIONAL (operation-dependent) | processo normal de compra · PRICE_BUDGET (forma de pagamento) | HUBSPOT, MEDDPICC |

## Knowledge unit format

Todos os arquivos em `objections/` têm as mesmas seções, na mesma ordem:

```
Metadata · Definition · Use when · Do not use when · Minimum transcript evidence · Positive signals ·
Negative / falsifying signals · Often confused with · Positive examples · Counterexamples ·
Ambiguous examples · Observed vs inferred risks · Framework mappings · Source-backed notes ·
Sources · Open questions
```

Metadata (Markdown puro, sem frontmatter): `concept_id` (`objection_category.<NAME>`; o prefixo dá o
tipo), `version`, `status`, `source_strength` (níveis que sustentam o conceito; nunca média). Todos os
exemplos são **sintéticos**, curtos e sem PII.

**Uma unidade = um arquivo Markdown** (~100 linhas). É coeso o bastante para um retriever futuro
recuperar o arquivo inteiro ou chunkar por seção (`##`). Nenhum chunker, índice ou schema é criado
agora. As seções "Do not use when", "Counterexamples" e "Often confused with" existem para que
retrieval traga também a **desambiguação**, não só o match positivo (ex.: "prospect asks how
integration works" deve cair em IMPLEMENTATION_INTEGRATION **e** ler que pergunta neutra não é
objeção).

## Not categories in v0.1

- **STATUS_QUO** — não é categoria independente (proposal: fontes não dão critério discriminante).
  Classifique pelo bloqueio observável: fornecedor atual → COMPETITION_EXISTING_SOLUTION; "não precisamos
  mudar" → NEED_VALUE_FIT; "agora não é hora" → TIMING_PRIORITY; sem motivo dito → AMBIGUOUS.
- **OTHER / UNKNOWN / AMBIGUOUS** — estados de classificação, não conceitos comerciais: `OTHER` = objeção
  clara fora das 8; UNKNOWN/AMBIGUOUS = status de anotação (ver guideline). Sem knowledge unit.
- Fora do escopo v0.1: seller response, prospect reaction, resistance types, PRODUCT, PROCUREMENT,
  RISK separado de TRUST, VALUE separado de NEED/FIT.

## Known divergences (registradas, não corrigidas)

- As 8 categorias são **candidatas provisórias** (CIT-M3). A guideline v0 ainda usa o enum v0 para o
  pilot; qual label set o pilot usa é CIT-O1 (aberta).
- Enum v0 `trust_authority` junta o que aqui são duas unidades (AUTHORITY_INTERNAL_BUY_IN e TRUST_RISK).
  Não há mapeamento determinístico.
- A guideline v0 usa "Está caro e preciso falar com meu sócio" como exemplo inequívoco de
  `trust_authority`; esta base (seguindo a pesquisa e o proposal) trata a mera consulta a sócio como
  insuficiente para AUTHORITY. Item da guideline v0.1.

## Versioning

Knowledge Base **v0.1**. Mudanças futuras entram por PR (revisáveis no diff) e incrementam `version`
nas unidades afetadas. Git é o registro de versões; nenhum registry ou serviço. Quando houver runs que
usem esta base, a versão usada entra na proveniência do run (D4), nunca no episódio.
