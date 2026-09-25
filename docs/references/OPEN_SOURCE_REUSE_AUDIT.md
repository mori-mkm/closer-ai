# Open Source Reuse Audit

Status: **referência para tasks futuras.** Nenhum código externo foi copiado, nenhuma dependência
foi adicionada, nenhum repositório externo foi modificado.

## Scope

Pergunta: *qual parte comprovadamente útil de dois projetos externos reduz trabalho nas próximas
fases do AI Closer **sem** destruir os contratos já construídos?* Não: "qual projeto copiar".

Fases avaliadas: Golden Set, Annotation Guidelines, Objection Taxonomy, ObjectionEpisode Extractor,
evidence-span validation, Call Behavior Extraction, LLM evals, prompt/model experimentation, batch
processing, LLM observability, Outcome Intelligence, evidence viewer. Fora de escopo: realtime,
copilot, RAG, vector DB, multi-agent, dashboard, auth, multi-tenancy, CRM ingestion, streaming.

Classificação: **REUSE** (código isolado, compatível, licenciado para uso direto) · **ADAPT**
(padrão/schema/rubrica útil, reescrito no nosso domínio) · **IDEA_ONLY** (referência conceitual) ·
**IGNORE** (sem valor ou contradiz invariantes).

## Reference snapshots

Ambos lidos só localmente, read-only, em `C:\Users\mathe\Documents\projects\closer-ai-references\`.

### Attention GTM Superintelligence

| Campo | Valor |
|---|---|
| repo | https://github.com/attentiontech/gtm-superintelligence |
| path | `closer-ai-references\gtm-superintelligence` |
| commit | `15d60c01293721c39e0b8937fe9cbf09fcb21cc4` |
| license | **Apache-2.0** (arquivo `LICENSE`; `pyproject.toml` declara o mesmo). Sem arquivo `NOTICE`; sem cabeçalhos de copyright em `src/` |
| linguagem | Python ≥ 3.10; runtime deps `pyyaml`, `pydantic>=2.6`; extras `anthropic`, `requests` |
| estrutura relevante | `src/gtmsi/` (~3.8k linhas: `models.py`, `pipeline.py`, `llm.py`, `adapters/`, `scoring/`), `schemas/*.json`, `scorecards/*.yaml`, `rubrics/`, `frameworks/`, `prompts/*.md`, `evals/`, `tests/` |

### Zime GTM Skills

| Campo | Valor |
|---|---|
| repo | https://github.com/zime-ai/zime-gtm-skills |
| path | `closer-ai-references\zime-gtm-skills` |
| commit | `4f134175badd08302f070c77449822c48403eeb1` |
| license | **MIT**, "Copyright (c) 2026 Zime" (arquivo `LICENSE`) |
| linguagem | Markdown (41 skills em `skills/*/`), scripts Python stdlib e bash em `evals/framework/`, `promptfoo` como runner |
| estrutura relevante | `EVALS.md`, `evals/` (`SCORECARD.md`, `gold/`, `framework/`, `promptfooconfig.yaml`, `cases.example.yaml`), `skills/<skill>/{SKILL.md, references/rubric.md, assets/, evals/evals.json}` |

## AI Closer constraints (autoridade)

Os contratos do AI Closer vencem qualquer ideia externa:

- Evidência = `segment_id` de `TranscriptSegment` (hash determinístico), sem texto copiado, sem
  char spans (`OBJECTION_EPISODE_V1_PROPOSAL.md` §7).
- `unknown`/`ambiguous`/revisão humana são estados legítimos; ausência nunca vira 0 nem negativo;
  `role="unknown"` nunca é inferido (TD-14).
- Call outcome ≠ Deal outcome; outcome canônico só via `OutcomeAssessment` (ADR-001).
- Autoridade humana persiste; regra automática não a remove.
- Proveniência de runs (humano/regra/LLM, versão de prompt/modelo/schema) fica no run (D4).
- Métricas com conjunto vazio ou kappa indefinido = N/A, nunca número silencioso.

## Attention findings

### Transcript model
`Transcript → turns: list[Turn]` com `speaker` (string livre), `side`
(rep/prospect/customer/partner/internal/unknown), `text`, `start_seconds`/`end_seconds` opcionais
(`src/gtmsi/models.py:18-78`, `schemas/transcript.schema.json`). **Turns não têm id nem índice**;
o prompt recebe `[mm:ss] Speaker (side): text` (`models.py:46-59`). `side` é inferido por regex
(`adapters/base.py:61-69`, aplicado em `:83`) — **viola "unknown nunca inferido"**.
Nosso modelo (segment_id + segment_index + speaker_id referencial) é mais forte.

- **IDEA_ONLY:** renderizar o transcript para o LLM com prefixo de id curto por segmento
  (ex. `[S0042 02:13] closer: …`) e pedir de volta **só ids** — melhora direta sobre o layout deles
  e casa com nossa evidência por `segment_id`.
- **IDEA_ONLY:** proveniência de adapter (`source{recorder, adapter}`) — já temos `Call.source`;
  útil só quando houver múltiplos adapters.
- **IGNORE:** adapters VTT/SRT/Gong/etc. (CRM/recorder ingestion fora de escopo); inferência de
  `side` por regex.

### Evidence grounding
`Quote{speaker, text, timestamp_seconds?}` (`models.py:164-167`), descrito como "verbatim (or
near-verbatim)" (`schemas/coaching_report.schema.json:107-114`). **Não existe validação de quote
contra transcript em lugar nenhum**; grounding é só instrução de prompt (`prompts/system.md:6-9`).
`evidence=[]` é válido — score sem evidência passa.

- **IGNORE** o mecanismo (texto livre, sem validação).
- **IDEA_ONLY (aviso):** é exatamente a lacuna que nossa validação por `segment_id` (grounding de
  `ObjectionEpisode` §12.1) fecha. Nenhum validador reutilizável aqui.

### Scorecards / rubrics
YAML separado do código, validado por JSON Schema e CI (`schemas/scorecard.schema.json`,
`rubric.schema.json`, `framework.schema.json`; `.github/scripts/validate_schemas.py`). Campos de
critério: `id, name, weight, intent, framework_refs, what_great_looks_like, what_poor_looks_like,
evidence_cues, coaching_prompts` (`models.py:114-123`; exemplo `scorecards/discovery.yaml:23-60`).
Taxonomia de call type com `positive_signals`, `negative_signals`, `often_confused_with`
(`config/call_types.yaml`).

- **ADAPT:** formato de entrada de taxonomia/guideline como arquivo versionado + schema + check de
  CI, com campos `definition`, `positive_cues`, `negative_cues`, `often_confused_with`, `examples`.
  **Não transportar** `weight`, bandas de score nem `coaching_prompts` (sem ground truth ainda).
- **IDEA_ONLY:** lista de 10 categorias de objeção em
  `agents/sales-enablement/objection-catcher.builds/claude-agent.py:25-27` — **EXTERNAL_REFERENCE_ONLY**,
  semente para o workshop com Gabriel/Otávio.

### Structured schemas
Pydantic espelhando JSON Schema (`models.py`, `schemas/*.json`); `Literal` enums; `OutcomeResult.status`
tem `unknown` (`models.py:181`); `Classification` com `confidence` + `alternatives`
(`models.py:170-175`).

- **ADAPT:** Pydantic como contrato espelhado por JSON Schema para a saída do LLM (já é nossa prática
  com Pydantic).
- **IGNORE:** `CriterionScore.score` obrigatório 0–100 (`models.py:188`), sem estado N/A.

### Pipeline
2 chamadas por transcript (`pipeline.py:1-9`): `classify` + `coach` monolítico. Seam de provider:
`LLMLike` Protocol com um método `complete_json(...)` (`pipeline.py:25-26`), única implementação
`AnthropicCoach` (`llm.py:39-121`), testes injetam fake. Prompt caching (`cache_control: ephemeral`,
`llm.py:67-80`). Parse por heurística de fence/chaves (`llm.py:124-139`). Uma retry com orçamento
dobrado se `stop_reason == "max_tokens"` e erro tipado indicando truncamento (`llm.py:83-111`). Batch
= loop sequencial com erro por arquivo (`cli.py:137-170`). Sem observabilidade.

- **ADAPT:** seam de provider como Protocol mínimo + fake nos testes — **já temos** o mesmo padrão
  em `ObjectionExtractor` (`src/closer_ai/ai/objection_extraction.py`); confirma a escolha.
- **ADAPT:** retry consciente de truncamento de *saída* (detecta `max_tokens`, erro tipado) +
  persistir resposta bruta; cached system blocks para batch.
- **IDEA_ONLY:** preferir structured output/tool-use nativo à extração de JSON por heurística.

### Evals
Um harness (`evals/run_evals.py`, casos em `evals/cases/classification.yaml`, 4 transcripts):
acurácia de call type + confusões contra API real. Nada avalia evidência, outcome ou consistência.

- **ADAPT:** formato "casos YAML + rótulo esperado + matriz de confusão" para evals de categoria de
  objeção e `resolution_status`. Fino demais para reusar.

### Useful patterns
Conhecimento de domínio (rubricas/taxonomias) em arquivos versionados validados por schema; seam de
LLM injetável; retry tipado de truncamento de saída; casos de eval em YAML.

### Patterns to avoid
| Anti-pattern | Onde | Nosso invariante violado |
|---|---|---|
| score ausente → 0 e banda "poor", travado por teste | `pipeline.py:123-126`; `scoring/__init__.py:105`; `tests/test_pipeline.py:87-104` | ausência nunca vira 0 |
| truncar transcript em 60k chars com marcador só no texto, relatório não sinaliza | `pipeline.py:21-22,47-51` | nada silencioso; falhar alto ou chunkar |
| inferência de `side` por regex; `phase` sobrescrito sem flag | `adapters/base.py:61-69`; `pipeline.py:69-72` | unknown nunca inferido |
| quotes "near-verbatim" sem validação | `prompts/system.md:7` | evidência verificável |
| classificação forçada a um tipo; todo critério forçado a 0–100 | `prompts/classifier.md:3`; `models.py:188` | ambiguidade preservada |
| relatório monolítico (outcomes + scores + coaching numa chamada) | `pipeline.py:77-129`; `prompts/coaching.md` | extração separada por contrato |
| coaching/scoring sem ground truth rotulado | `prompts/coaching.md`, `scorecards/*` | Golden Set antes de coaching |
| deal score = rollup de scores de call; objeção ponderada por won/lost do CRM | `scoring/__init__.py:17-37`; `objection-catcher.builds/claude-agent.py:28-30` | Call outcome ≠ Deal outcome; CRM ≠ outcome canônico |

## Zime findings

> Aviso do próprio repo: **nenhuma skill foi medida** com ground truth independente
> (`evals/SCORECARD.md:9-22`); resultados "illustrative" foram escritos, rodados e julgados pelo
> mesmo autor (`SCORECARD.md:40-48`). Tudo abaixo é design, não prática validada.

### Skill architecture
`skills/<skill>/SKILL.md` (frontmatter, passos ordenados, formato de saída, "Do not") +
`references/rubric.md` + `assets/sample-transcript.txt` (sintético) + `evals/evals.json`
(ex. `skills/pain-finder/`). **Sem versão por skill/rubrica**; a única versão é
`RUBRIC_VERSION` do judge (`evals/framework/judge.py:32`). Rubricas reusam umas às outras
explicitamente (`skills/mutual-action-plan/references/rubric.md:3-6`). Amendments de rubrica em
ledger append-only JSONL com ids e status, citados em commits (`evals/framework/README.md:114-137`).

- **ADAPT:** guidelines/taxonomia/rubricas como arquivos versionados; toda extração e todo veredito
  de judge carregam `rubric_version` + `prompt_version` + `model_id` (no run, D4); mudanças de
  rubrica num ledger append-only ligado a eval runs.
- **IGNORE:** o empacotamento como Claude skill (somos pipeline Python).

### Evidence-first methodology
- "Finding sem citação não entra" (`README.md:19-22`); "sem quote, sem pain point", inferência só em
  Notes marcada como inferida (`skills/pain-finder/references/rubric.md:51-53`).
- "Unclear em vez de chutar"; trecho inaudível/truncado = Unclear
  (`skills/negotiation-closing/SKILL.md:39-40,52-54`).
- heard vs inferred: `inferred` cita o mais próximo dito e nomeia o elemento faltante
  (`skills/mutual-action-plan/references/rubric.md:17-31`).
- Confiança vem das palavras do falante (específico, repetido, quantificado), não do quão plausível
  é a categoria (`skills/pain-finder/references/rubric.md:21-47`).
- Escopo: "não inferir budget de calls anteriores", "não inferir autoridade só pelo cargo"
  (`skills/negotiation-closing/SKILL.md:73-74`; `skills/meeting-to-qualify/SKILL.md`, seção Do not).

- **ADAPT (para Annotation Guidelines / extractor):** distinção explícita dito × inferido; só
  evidência dita, com `segment_id` validado, vira canônica; inferido nunca canônico (vai para
  revisão). Nossa regra é **mais estrita** que a deles (eles mantêm inferidos em Notes/linhas de plano).
- **IGNORE:** quote de texto livre como evidência.

### Taxonomies — EXTERNAL_REFERENCE_ONLY
- Pain: operational friction; risk exposure; cost/headcount pressure; growth/scale pressure;
  leadership/stakeholder pressure (`skills/pain-finder/references/rubric.md:5-19`). O próprio run
  deles re-rotulou categorias livremente (`evals/illustrative/README-pain-finder.md`) → instáveis.
- Highlight types incluindo objection (price, timeline, fit, internal buy-in, anything else) e
  buying signal (`skills/deal-highlights/references/rubric.md:3-21`).
- Objeções por persona; **"nenhuma objeção surgiu → Unclear, não assumir"**
  (`skills/persona-based-discovery/references/rubric.md:70-84`).
- Next step: ação específica + data/gatilho verificável + dono dos dois lados; Real/Weak/No
  (`skills/next-step-commitment/references/rubric.md:1-50`).

**IDEA_ONLY** como sementes para o workshop de taxonomia; o teste de três elementos de next step é
**ADAPT** candidato para um futuro contrato de Commitment (não para `resolution_status`).

### Eval methodology (o achado mais valioso)
- **Duas métricas, nunca misturadas:** format compliance × insight recall/precision
  (`EVALS.md:27-38`), motivadas por um benchmark anterior inflado por checks de formato
  (`EVALS.md:15-25`).
- **Formato de gold label** (`EVALS.md:91-100`, `evals/gold/BRIEFS.md:47-65`): achados obrigatórios
  ranqueados; "o que um rep fraco perde"; **dimensões que legitimamente não se aplicam (N/A)**;
  **"não presente — reportar é alucinação" (rótulos negativos)**.
- **Construção de ground truth** (`EVALS.md:106-131`, `evals/gold/BRIEFS.md:1-19`): transcripts
  escritos às cegas a partir de persona brief, nunca pelo autor da rubrica; cada um contém um item
  fora das categorias, uma dimensão que não se aplica, um sinal minimizado; toda eval tem ao menos
  uma **"falsifying expectation"** que uma saída bem formatada porém rasa falharia.
- **Armadilha sintética admitida:** mesmo autor de brief/gold/grader = "anedotas correlacionadas";
  trap plantado passou e a mesma forma não plantada falhou (`SCORECARD.md:40-48,92-93`) → Golden Set
  precisa ser majoritariamente real.
- **Tiers de caso:** `happy-path | missing-context | ambiguous | adversarial`
  (`evals/cases.example.yaml:18`).
- **Judge** (`evals/framework/judge.py`): N=3 amostras isoladas, voto majoritário por campo, flag de
  baixa concordância, embaralha ordem dos campos do gold, judge não vê o prompt da skill; vereditos
  `present | missing | wrong | extra` + `derivable` (`:34-47`). Falhas: sem modelo fixado (`:188`),
  "extra" (alucinação) subcontado porque o judge enumera campos do gold (`:36-38,176`), `derivable`
  é `any()` e não maioria (`:162`), assertion sempre passa (`:197`), `/tmp` hardcoded (`:121`) e
  invoca o CLI com `--dangerously-skip-permissions` (`:71`).
- **Calibração judge × humano:** Cohen's kappa em `evals/framework/calibrate.py:22-31` (stdlib).
  Retorna **1.0 quando `pe >= 1`** — conflita com nossa regra "kappa indefinido = N/A".
- **promptfoo:** `evals/promptfooconfig.yaml` usa provider `exec:` para shell e assertion Python;
  paths relativos ao config e glob errado casa nada em silêncio (`:23-28`). Dados reais gitignored
  (`evals/framework/README.md:159-172`).

Comparação com nosso Golden Set: eles **não** têm dupla anotação, agreement, rótulos de resolução/
outcome nem evidência por segmento. Nosso plano é metodologicamente à frente; o que vale trazer são
os rótulos negativos e N/A, os tiers, as falsifying expectations e o gate de calibração do judge.

### Prompt patterns
- Passos ordenados: ler o transcript inteiro antes de extrair (sinais tardios mudam a leitura),
  extrair nas palavras do falante, depois classificar e anexar evidência
  (`skills/pain-finder/SKILL.md:53-63`) → **ADAPT** (resolução depende de segmentos posteriores).
- Entrada de rubrica "o que é / coberto vs perdido / exemplo fraco vs forte"
  (`skills/negotiation-closing/references/rubric.md:6-17`) → **ADAPT** para entradas de guideline.
- Listas "Do not": não inventar seções, não misturar dimensões num score, não descartar itens de
  baixa confiança, não "inflar" itens minimizados, não completar até uma contagem
  (`skills/deal-highlights/references/rubric.md:36-41`) → **ADAPT** como instruções negativas.
- Confiança em 3 níveis com âncoras verbais + Unclear/N-A → **ADAPT** só amarrando confiança a
  características da evidência, não a probabilidade autodeclarada.

### Useful patterns
Métricas separadas; gold com negativos e N/A; tiers; falsifying expectations; judge com amostras
isoladas e calibração contra humano; dito × inferido; "Unclear em vez de chutar"; rubricas
versionadas com ledger de mudanças.

### Patterns to avoid
| Anti-pattern | Onde | Por quê |
|---|---|---|
| "Não pare para perguntar como ler um momento ambíguo — decida, anote a suposição e siga" (~53 ocorrências) | `skills/pain-finder/SKILL.md:33-35`; `deep-discovery/SKILL.md:36`; `meddicc/SKILL.md:40`; `next-step-commitment/SKILL.md:36-37` | força leitura única; contradiz `unknown`/`ambiguous`/revisão |
| itens `inferred` mantidos como linhas do resultado | `skills/mutual-action-plan/references/rubric.md:17-43` | inferido nunca canônico |
| "reads-well-too check" que afrouxa a leitura quando uma call boa sai mal | `skills/negotiation-closing/references/rubric.md:88-90` | empurra inferência generosa; só serve como **caso de eval** |
| evals em linguagem natural julgadas por LLM, 37/41 com `files: []` | `skills/*/evals/evals.json`; `SCORECARD.md:33-38` | preferir checks tipados determinísticos |
| judge sem modelo fixado, alucinação subcontada, assertion sempre verdadeira, `--dangerously-skip-permissions` | `evals/framework/judge.py:71,162,176,188,197` | não reprodutível; inseguro |

## Feature mapping

| AI Closer Feature | External Source | Component/Idea | Decision | Why | Risk |
|---|---|---|---|---|---|
| Golden Set | Zime | gold com negativos ("não presente") e N/A; tiers de caso; falsifying expectations; majoritariamente real | ADAPT | mede alucinação e N/A explicitamente | sintético correlacionado se o mesmo autor escrever brief e gold |
| Annotation Guidelines | Zime + Attention | entrada "definição / cues positivos / negativos / often_confused_with / exemplo fraco×forte"; dito × inferido; Unclear | ADAPT | acelera redação das guidelines | importar categorias comerciais deles sem validar |
| Objection Taxonomy | Attention + Zime | listas de categorias | IDEA_ONLY (EXTERNAL_REFERENCE_ONLY) | só semente para workshop | virar taxonomia sem Gabriel/Otávio e dados reais |
| Objection Taxonomy (formato) | Attention | taxonomia em arquivo versionado + schema + CI | ADAPT | mudança de taxonomia auditável | framework de YAML maior que o necessário |
| ObjectionEpisode Extractor | Attention | Protocol de provider + fake; render com id de segmento; retry por truncamento de saída | ADAPT / IDEA_ONLY | já temos o seam; ids fecham grounding | truncamento silencioso de entrada |
| ObjectionEpisode Extractor | Zime | ler tudo antes de extrair; "Do not"; Unclear | ADAPT | resolução depende de segmentos tardios | "decida e siga" (IGNORE) |
| Evidence Validation | ambos | — (nenhum validador existe) | IGNORE | nosso grounding por `segment_id` já é superior | — |
| Call Behavior Extractor | Attention | critério com `intent`/cues/great×poor | IDEA_ONLY | inspiração de campos | scores 0–100 forçados |
| LLM Evals | Zime | duas métricas nunca misturadas; P/R de insight contra gold humano | ADAPT | alinha com nossas métricas de matching | — |
| LLM Evals (judge) | Zime | amostras isoladas, voto por campo, calibração judge×humano com kappa | ADAPT (reescrever) | útil se usarmos LLM-as-judge | código tem falhas conhecidas |
| Prompt Experimentation | Zime + Attention | versão de rubrica/prompt/modelo em cada run; ledger de amendments; promptfoo matrix | ADAPT / IDEA_ONLY | reprodutibilidade (D4) | adotar promptfoo cedo demais |
| Batch Processing | Attention | loop com erro por arquivo; cached system blocks | IDEA_ONLY / ADAPT | pouco a aprender além de caching | sem resume/idempotência lá |
| Observability | nenhum | — | IGNORE | nenhum dos dois tem | — |
| Outcome Intelligence | Attention | rollup de scores de call para deal; objeção ponderada por won/lost do CRM | IGNORE | viola Call ≠ Deal outcome e CRM ≠ canônico | — |
| Evidence Viewer | Attention | render `[mm:ss] speaker: text` | IDEA_ONLY | layout de leitura com id + tempo | — |

## REUSE candidates

**Nenhum código recomendado para cópia agora.** Os dois candidatos considerados foram rebaixados:

| Candidato | Repo / path | Licença | Deps | Tamanho | Por que não REUSE |
|---|---|---|---|---|---|
| `cohens_kappa` | Zime `evals/framework/calibrate.py:22-31` | MIT | stdlib | ~10 linhas | devolve 1.0 quando `pe >= 1`; precisamos N/A → reescrever (ADAPT) |
| `looks_like_speaker` + stoplist | Attention `src/gtmsi/adapters/base.py:27-50` | Apache-2.0 | stdlib | ~25 linhas | só serve para ingestão de texto puro, fora do escopo atual (IDEA_ONLY; reavaliar se surgir) |

Se algum dia copiarmos: ver "Licensing notes". Nenhum dos dois repos é dependência instalável útil
para nós (Attention é app CLI; Zime é conteúdo + scripts).

## ADAPT candidates

| # | Problema | Conceito externo | No AI Closer | Autoridade que permanece nossa | Não transportar |
|---|---|---|---|---|---|
| A1 | Golden Set que não mede alucinação nem N/A | gold com seções "não presente" e "não se aplica"; tiers; falsifying expectation (Zime `EVALS.md:91-131`, `evals/gold/BRIEFS.md`) | cada call anotada ganha rótulos negativos (objeções plausíveis ausentes), N/A por dimensão, `tier`, e ≥ 1 expectativa que saída rasa falharia | `ObjectionEpisode`, matching §12 de AC-47, dupla anotação | gold escrito pelo mesmo autor do prompt; skills em Markdown |
| A2 | Métricas infladas por formato | "duas métricas nunca misturadas" (Zime `EVALS.md:27-38`) | reportar separadamente schema validity, grounding rate e P/R substantivo (já é nosso §12; tornar regra do harness) | runs INVALID de §12.1.1 | score único combinado |
| A3 | Guidelines difíceis de aplicar | entrada "definição / cues + / cues − / often_confused_with / exemplo fraco×forte" (Attention `scorecards/discovery.yaml:23-60`, `config/call_types.yaml`; Zime `negotiation-closing/references/rubric.md:6-17`) | um arquivo versionado por código de taxonomia e por valor de `resolution_status` | taxonomia validada por Gabriel/Otávio | pesos, bandas, coaching prompts |
| A4 | Taxonomia/guideline mudando sem rastro | arquivos versionados + schema + CI (Attention); ledger append-only de amendments (Zime `evals/framework/README.md:114-137`) | `version` no arquivo + versão registrada no run (D4) + ledger ligado a eval runs | proveniência no run | Claude-skill packaging |
| A5 | Evidência inferida contaminando canônico | dito × inferido; "Unclear em vez de chutar" (Zime) | guidelines e extractor distinguem dito/inferido; só dito com `segment_id` validado vira evidência; inferido → revisão | grounding por `segment_id` | inferidos no output final |
| A6 | Extractor robusto a falhas do provider | Protocol mínimo + fake; retry tipado em `max_tokens`; cached system blocks (Attention `pipeline.py:25-26`, `llm.py:67-111`) | manter `ObjectionExtractor` Protocol; o LLM extractor detecta truncamento de saída, falha tipado, persiste resposta bruta | proveniência no run; nunca truncar entrada em silêncio | parse por heurística de chaves; truncamento de entrada |
| A7 | LLM-as-judge não confiável | amostras isoladas, voto por campo, calibração com humano (Zime `judge.py`, `calibrate.py`) | se usarmos judge: modelo fixado, alucinação calculada do lado da saída comparando `segment_id` com gold, gate de kappa judge×humano (N/A quando indefinido) | Golden Set humano como verdade | código deles (falhas listadas) |
| A8 | Evals de classificação | casos YAML + rótulo esperado + matriz de confusão (Attention `evals/run_evals.py`) | casos para categoria de objeção e `resolution_status` | harness do AI Closer | API real obrigatória em teste |
| A9 | Instruções de prompt | ler tudo antes; "Do not" list; confiança ancorada em evidência (Zime) | seções do prompt do extractor | contratos Pydantic | "decida e siga" |

## IDEA_ONLY candidates

- Render de transcript com id de segmento + tempo, pedindo ids de volta (evolução do layout de
  Attention `models.py:46-59`).
- Sementes de taxonomia: Attention `objection-catcher.builds/claude-agent.py:25-27`; Zime
  `pain-finder/references/rubric.md:5-19`, `deal-highlights/references/rubric.md:3-21`,
  `persona-based-discovery/references/rubric.md:70-84` (EXTERNAL_REFERENCE_ONLY).
- Teste de três elementos de next step (Zime `next-step-commitment/references/rubric.md`) para um
  futuro contrato de Commitment.
- Scorecard de status honesto com disclaimers e N/A explícito (Zime `evals/SCORECARD.md`) como
  modelo de relatório de eval.
- promptfoo só se quisermos matriz prompt×modelo; pytest + harness pequeno cobre o resto.
- Check de CI de que caminhos de dado privado continuam gitignored (Zime `validate-skills.sh`).
- Structured output/tool-use nativo em vez de extração de JSON por heurística.

## IGNORE

Quote de texto livre como evidência; scores 0–100 forçados, pesos e bandas; missing→0; truncamento
silencioso de transcript; inferência de speaker/side por regex; relatório monolítico; rollup de
call score para deal e ponderação por won/lost do CRM; "decida e siga"; inferidos no output;
empacotamento como Claude skill; adapters de recorder/CRM; templates de agentes; telemetry; o código
do judge da Zime.

## Licensing notes

| Repo | Licença | Se copiarmos código no futuro |
|---|---|---|
| Attention | Apache-2.0 | manter uma cópia da licença; preservar avisos de copyright/atribuição existentes; **marcar arquivos modificados** ("modified" notice, cl. 4b); se houver `NOTICE` no upstream, reproduzi-lo (hoje não há); patent grant da cl. 3 se aplica |
| Zime | MIT | incluir o aviso de copyright "Copyright (c) 2026 Zime" e o texto da permissão em cópias/porções substanciais |

Regra prática: qualquer código copiado vai para um arquivo com cabeçalho de origem (repo, commit,
path, licença) e a licença correspondente entra em `third_party/` ou equivalente. Adaptar *ideias*
(ADAPT/IDEA_ONLY) não gera essas obrigações; ainda assim citar a referência no doc da feature.
Não é parecer jurídico.

## Recommended next implementation sequence

1. **Golden Set schema** (A1, A2): adicionar rótulos negativos, N/A, `tier` e falsifying
   expectations ao plano do Golden Set; métricas separadas como regra do harness.
2. **Annotation Guidelines + taxonomy files** (A3, A4, A5): formato de entrada versionado,
   dito × inferido; conteúdo das categorias só após workshop com Gabriel/Otávio (D3/D6 de AC-47).
3. **ObjectionEpisode LLM extractor** (A6, A9, IDEA render com ids): seam existente, structured
   output, ids de segmento de volta, falha tipada em truncamento, proveniência no run.
4. **Eval harness** (A8, A2): casos com tiers, matriz de confusão, P/R por overlap (AC-47 §12).
5. **Judge (opcional)** (A7): só se a revisão humana não escalar; calibrado contra humano.

Nada disso exige dependência nova; promptfoo/Instructor/Langfuse/Label Studio ficam para decisão
própria quando a necessidade aparecer (nenhum dos dois repos integra Instructor, Langfuse ou Label
Studio; Zime usa promptfoo como runner fino).

## Files worth consulting in future tasks

Base: `C:\Users\mathe\Documents\projects\closer-ai-references\`.

Attention (`gtm-superintelligence\`, commit `15d60c01`):
- `src\gtmsi\models.py` — Transcript/Turn (18-78), Quote (164-167), Classification (170-175),
  CriterionScore (188)
- `src\gtmsi\pipeline.py` — LLMLike (25-26), truncamento (21-22, 47-51), missing→0 (123-126)
- `src\gtmsi\llm.py` — cached blocks (67-80), retry tipado (83-111), parse JSON (124-139)
- `scorecards\discovery.yaml` (23-60); `config\call_types.yaml`
- `schemas\scorecard.schema.json`, `schemas\transcript.schema.json`,
  `schemas\coaching_report.schema.json` (107-114)
- `evals\run_evals.py`, `evals\cases\classification.yaml`
- `prompts\system.md` (6-9), `prompts\classifier.md` (3)
- `agents\sales-enablement\objection-catcher.builds\claude-agent.py` (25-30)

Zime (`zime-gtm-skills\`, commit `4f134175`):
- `EVALS.md` (15-38, 40-131)
- `evals\gold\BRIEFS.md` (1-19, 47-65)
- `evals\SCORECARD.md` (9-48, 92-93)
- `evals\cases.example.yaml` (18)
- `evals\framework\judge.py` (32, 34-47, 71, 162, 176, 188, 197)
- `evals\framework\calibrate.py` (22-31)
- `evals\framework\README.md` (86-137, 146-172)
- `evals\promptfooconfig.yaml`
- `skills\pain-finder\SKILL.md` (33-35, 53-63), `skills\pain-finder\references\rubric.md`
- `skills\mutual-action-plan\references\rubric.md` (3-43)
- `skills\negotiation-closing\SKILL.md` (39-40, 52-54, 73-74), `references\rubric.md` (6-17, 88-90)
- `skills\next-step-commitment\references\rubric.md`
- `skills\persona-based-discovery\references\rubric.md` (70-84)
- `skills\deal-highlights\references\rubric.md` (3-41)
