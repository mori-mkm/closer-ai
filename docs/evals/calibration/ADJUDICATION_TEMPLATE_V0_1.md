# Adjudication Template v0.1

Só no modo B. Preencha depois de receber a call, a anotação A e a anotação B. O adjudicador **não** é
A nem B, **não** consulta `REFERENCE_ANSWERS_V0_1.md` antes de terminar e não usa modelo/RAG. Não há
voto majoritário: o adjudicador pode aceitar A, aceitar B, produzir uma terceira leitura ou concluir
NO_OBJECTION, UNKNOWN ou AMBIGUOUS. Mesmo com A = B, confirme.

```
# Adjudication

call_id:
segment_sequence_hash:          (deve ser igual em A, B e aqui; se diferir, pare)
annotator A:
annotator B:
adjudicator:
calibration_kit_version: v0.1
guideline_version: v0.1
date:

## Episode pairing
(pareie por sobreposição de objection_segment_ids na mesma call, sem particionar por categoria)

## Differences (tipo + descrição + ids)

DETECTION:
BOUNDARY (anchor / objection / context):
CATEGORY (inclui valor × UNKNOWN × AMBIGUOUS):
EVIDENCE (id inexistente, âncora fora do objetor, texto em vez de id):
HANDLING:
REACTION (inclui GL-3):
RESOLUTION:
APPLICABILITY / UNCERTAINTY (PRESENT / ABSENT / UNKNOWN / AMBIGUOUS / N/A):

## Adjudicated interpretation

call-level: annotatable? ABSENT? NO_OBJECTION trechos:
por episódio:
  anchor / objection_segment_ids / context_segment_ids:
  category + status:
  handling / reactions:
  resolution_status (só os 4 valores):
reasoning (A, B ou terceira leitura, e por quê):

## Final uncertainty kept (UNKNOWN / AMBIGUOUS / N/A e por quê)

## Inference or external knowledge used as evidence by A or B? YES / NO (onde)

## Guideline issue? YES / NO
regra insuficiente:
exemplo (ids):
proposed clarification (para v0.1.1 / v0.2):

## Open item triggered
GL-1 / GL-2 / GL-3 / D6 / TAX (KEEP/MERGE/SPLIT/REMOVE/ADD) / CIT-O2..O6 / GS-1..GS-3 / outro:
```
