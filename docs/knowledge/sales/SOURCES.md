# Sales Knowledge Base — Sources

Registry das fontes usadas pela Knowledge Base v0.1. Knowledge units citam só o `source_id`.

Todos os dados abaixo vêm da pesquisa externa
`closer-ai-references/research/CALL_INTELLIGENCE_TAXONOMY_RESEARCH_V0_1.md` (sha256 `e50d7cad…6fd52`,
seções "Source traceability" e "References"). **Nenhuma fonte foi relida nem reverificada nesta task.**
Campo ausente na pesquisa = `not recorded` (não inventar ano, DOI, autor ou página).

Níveis de força (definidos em
[`CALL_INTELLIGENCE_TAXONOMY_V0_1_PROPOSAL.md`](../../domain/CALL_INTELLIGENCE_TAXONOMY_V0_1_PROPOSAL.md#source-strength)):
**S1** peer-reviewed research · **S2** research-derived methodology · **S3** proprietary observational ·
**S4** practitioner guide · **S5** commercial framework · **AC** abstração do AI Closer (sem fonte).
Níveis nunca são somados nem convertidos em score.

| source_id | title | author/org | type | strength | link | concepts_used_for |
|---|---|---|---|---|---|---|
| `SRC_HUNT_BASHAW` | A New Classification of Sales Resistance | Kenneth A. Hunt, R. Edward Bashaw (*Industrial Marketing Management*; ano not recorded) | peer-reviewed article | S1 | https://www.sciencedirect.com/science/article/pii/S0019850197000989 | README: objeção como forma de resistência que impede avançar |
| `SRC_CLARK_PINCH` | Recontextualising Sales Resistance | Colin Clark, Trevor Pinch (*Industrial Marketing Management*; ano not recorded) | peer-reviewed article (encontros reais de venda) | S1 | https://www.sciencedirect.com/science/article/pii/S0019850100001036 | README: resistência lida em sequência; preservar AMBIGUOUS |
| `SRC_SCHURR` | Effective Selling Approaches to Buyers' Objections | "Schurr et al." — lista completa de autores not recorded (*Industrial Marketing Management*; ano not recorded) | peer-reviewed article (escopo: venda industrial, poucos tipos de objeção) | S1 | https://www.sciencedirect.com/science/article/pii/0019850185900380 | PRICE_BUDGET (objeções de preço estudadas); README (indecisão ≠ categoria) |
| `SRC_SPIN` | SPIN Methodology | Huthwaite International (tradição Neil Rackham/Huthwaite) | research-derived commercial methodology; **não é taxonomia de objeções** | S2 | https://www.huthwaiteinternational.com/spin-methodology | NEED_VALUE_FIT (necessidade implícita × explícita; necessidade dita ≠ objeção) |
| `SRC_MEDDPICC` | MEDDPICC Sales Methodology and Process | MEDDICC | commercial qualification framework | S5 | https://meddicc.com/meddpicc-sales-methodology-and-process | framework mapping: AUTHORITY (Economic Buyer, Decision Process), COMPETITION, TERMS_PROCESS (Paper Process) |
| `SRC_SANDLER` | The Sandler Selling System | Sandler | commercial sales methodology | S5 | https://sandler.com/sandler-selling-system/ | framework mapping: PRICE_BUDGET (Budget), AUTHORITY (Decision) |
| `SRC_HUBSPOT_OBJECTIONS` | How to Handle Sales Objections | HubSpot | practitioner guide | S4 | https://blog.hubspot.com/sales/handling-common-sales-objections | maior fonte das definições das 8 categorias; BANT como agrupamento de objeções; brush-off × timing |
| `SRC_GONG_OBJECTIONS` | Handling Sales Objections | Gong (Gong Labs) | vendor article reportando análise observacional proprietária (67.149 demos, número como reportado pela pesquisa) | **S3** para achados do dataset; **S4** quando usado como descrição de categorias | https://www.gong.io/blog/handling-sales-objections | PRICE_BUDGET, TIMING_PRIORITY, AUTHORITY (internal buy-in) como temas recorrentes de objeção |

Notas:

- **BANT** não tem fonte primária própria nesta v0.1: aparece via `SRC_HUBSPOT_OBJECTIONS`, que reaproveita
  a sigla de qualificação como agrupamento de objeções. Qualificação ≠ objeção.
- A pesquisa também lista `https://www.gong.io/blog/objection-handling-techniques` ("Objection Handling
  Techniques"), mas não atribui a ele nenhuma afirmação usada aqui (é fonte de seller response, fora do
  escopo v0.1). **Não registrado.**
- A pesquisa diz "Gong" sem sempre indicar qual dos dois artigos sustenta a afirmação sobre categorias;
  aqui essas afirmações são atribuídas a `SRC_GONG_OBJECTIONS` e lidas como S4.
- Achados da Gong são observacionais e proprietários: **não estabelecem causalidade**.
- Challenger, Solution Selling e GAP Selling: sem fonte suficiente na pesquisa → não usados.
