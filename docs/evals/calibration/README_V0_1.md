# Synthetic Annotation Calibration Kit v0.1

## Purpose

Testar se as regras da [guideline v0.1](../OBJECTION_ANNOTATION_GUIDELINE_V0_1.md) são compreensíveis e
aplicáveis **antes** do pilot D3 com calls reais. O kit procura: regras confusas, fronteiras confusas,
labels difíceis de distinguir, campos inúteis, inferências indevidas e inconsistências entre guideline
e template.

**Synthetic calibration ≠ Golden Set real.** O kit não prova que a taxonomia funciona em produção, não é
ground truth, não é benchmark de modelo, não define thresholds, não fecha TAX/D3/D6/D7 e não pontua
pessoas.

O kit v0 (`README.md`, `SYNTHETIC_CASES_V0.md`, …) fica intacto como registro histórico, ligado à
guideline v0 e ao enum v0. Este kit v0.1 usa a guideline v0.1 e o label set CIT-O1.

## Versions

- `calibration_kit_version = v0.1`
- `guideline_version = v0.1`
- `taxonomy_version = CIT-O1 provisional 8-category set` (label set de anotação/eval; **não** é o enum
  do domínio)

Git é o registro de versões.

## Files

| Arquivo | Quem usa | Quando |
|---|---|---|
| [`SYNTHETIC_CASES_V0_1.md`](SYNTHETIC_CASES_V0_1.md) | todos | desde o início |
| [`ANNOTATION_TEMPLATE_V0_1.md`](ANNOTATION_TEMPLATE_V0_1.md) | anotador (modo A) / A e B (modo B) | anotação |
| [`ADJUDICATION_TEMPLATE_V0_1.md`](ADJUDICATION_TEMPLATE_V0_1.md) | adjudicador | só no modo B |
| [`REFERENCE_ANSWERS_V0_1.md`](REFERENCE_ANSWERS_V0_1.md) | todos | **só no fim** |

12 calls curtas (`CAL01`–`CAL12`). Os ids não indicam o tema nem a resposta.

## Label set and mechanisms

- Categorias: `PRICE_BUDGET`, `TIMING_PRIORITY`, `NEED_VALUE_FIT`, `AUTHORITY_INTERNAL_BUY_IN`,
  `TRUST_RISK`, `COMPETITION_EXISTING_SOLUTION`, `IMPLEMENTATION_INTEGRATION`, `TERMS_PROCESS`, `OTHER`.
- `NO_OBJECTION`: trecho examinado que não é episódio; não cria `ObjectionEpisode`.
- `UNKNOWN` / `AMBIGUOUS`: status de incerteza, **nunca** categoria nem valor de `resolution_status`.
- **Annotation label set ≠ domain enum.** Nada aqui produz `ObjectionEpisode` de produção.

## Mode A — Solo calibration

Para uma pessoa testar a guideline sozinha (ex.: Matheus). **Não** produz concordância entre anotadores
e **não** substitui D3.

1. Leia a guideline v0.1.
2. **Não** abra `REFERENCE_ANSWERS_V0_1.md`.
3. Anote `CAL01` no template.
4. Registre onde teve dúvida (antes de seguir).
5. Continue pelas demais calls, na ordem.
6. Só depois de anotar **todas**, abra as referências.
7. Compare call a call.
8. Registre as diferenças e, para cada uma, se a guideline ou a referência parece errada.

Perguntas de diagnóstico (por call e no fim):

- Eu entendi por que isso é / não é objection?
- Consegui escolher a categoria sem inferir?
- Fiquei entre duas categorias? Quais?
- Algum campo do template ficou confuso ou inútil?
- Alguma regra exigiu conhecimento que não estava no transcript?
- Quanto tempo levei?
- Em qual trecho consultei a Knowledge Base, e ela decidiu algo?
- A referência me convenceu? Se não, qual regra da guideline parece insuficiente?

O objetivo não é "acertei X%", é "quais partes da guideline causaram divergência". Sem score, sem
ranking.

## Mode B — Blind double annotation

Quando houver três pessoas (papéis de anotação, não cargos comerciais; não precisam ser vendedores),
seguindo o [protocolo](../GOLDEN_SET_ANNOTATION_PROTOCOL_V1.md):

1. A e B leem a guideline v0.1 e recebem **só** `SYNTHETIC_CASES_V0_1.md` + template.
2. A e B anotam sozinhos, sem ver a anotação do outro.
3. As anotações são pareadas por sobreposição de `objection_segment_ids` na mesma call.
4. O adjudicador (nem A nem B) recebe calls + A + B e preenche o template de adjudicação.
5. Só depois da adjudicação todos abrem `REFERENCE_ANSWERS_V0_1.md` e discutem.

## Reference reveal rule

Referências **só depois** da anotação (modo A) ou **só depois da adjudicação** (modo B). O adjudicador
também não as vê antes de adjudicar.

## Blindness

Durante a anotação não há — e não se procura — Outcome, WON/LOST, CRM, stage, predição de modelo,
sugestão de RAG, LLM, anotação de outra pessoa ou score de vendedor.

## Knowledge Base usage

Pode consultar [`docs/knowledge/sales/`](../../knowledge/sales/): o kit testa o conjunto guideline +
conhecimento. Registre no template quando consultou e se isso decidiu algo. Conhecimento nunca é
evidência — a anotação aponta `segment_id`s. **Não** use LLM, RAG ou predição de modelo.

## Calibration exit questions

Responda qualitativamente, sem threshold numérico:

1. Objection × no-objection ficou claro?
2. As 8 categorias são distinguíveis?
3. Quais pares causam mais confusão?
4. OTHER foi compreensível?
5. UNKNOWN × AMBIGUOUS ficou claro?
6. As fronteiras de episódio ficaram claras?
7. GL-3 ficou operacional?
8. `partially_resolved` ficou claro?
9. Algum campo parece desnecessário?
10. A Knowledge Base ajudou?
11. Alguma referência parece discutível?
12. A guideline v0.1 precisa de patch antes do D3?

## Expected result

- **Lacunas materiais** → guideline v0.1.1 / v0.2, baseada no que o dry run mostrou.
- **Guideline adequada** → pilot D3 com 3–5 calls reais autorizadas.

A calibração sintética **não** conclui D3 e não valida a taxonomia.

## Privacy

Tudo é sintético: nenhuma pessoa, empresa, cliente, Deal ou resultado comercial real; nenhum texto de
transcript real. Anotações feitas sobre estes casos podem ficar no Git; anotações do pilot D3 (calls
reais) **não**.
