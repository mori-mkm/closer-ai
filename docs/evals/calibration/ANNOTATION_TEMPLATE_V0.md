# Annotation Template v0

Copie este bloco uma vez por call. Preencha sozinho, sem ver outras anotações, a referência, o
Outcome ou saídas de modelo. Use ids de segmento (`CALnn_Snnn`), nunca trechos de texto.

Status possíveis: `PRESENT`, `ABSENT`, `UNKNOWN`, `N/A`, `AMBIGUOUS` (com candidatas).

```
# Annotation

Case ID:
Annotator (A ou B):
Guideline version: OBJECTION_ANNOTATION_GUIDELINE_V0
Date:
Tempo gasto (min):

## Call-level review

Annotatable: YES / NO (motivo)
Full relevant scope reviewed: YES / NO
Case tier (opcional): happy_path / missing_context / ambiguous / adversarial
No-objection negative label: YES (call ABSENT) / NO
Trechos que parecem objeção e não são (ids + motivo curto):
Notes:

## Episode 1

Detection status: PRESENT / AMBIGUOUS / UNKNOWN
Anchor segment:
Objection segments:
Context segments:

Category:                (valor do enum v0 ou vazio)
Category status: PRESENT / AMBIGUOUS {candidatas} / UNKNOWN

Handling segments (closer):
Handling status: PRESENT / ABSENT / UNKNOWN

Reaction segments (objetor):
Reaction status: PRESENT / ABSENT / UNKNOWN

Resolution: resolved / partially_resolved / unresolved / unknown
Resolution status: PRESENT / AMBIGUOUS {candidatas}
Decisive response segment (opcional):

Observed facts (o que foi dito):
Inferences / hypotheses (marcar INFERIDO):
Annotator uncertainty:

## Episode 2 (copie o bloco acima se houver)

## Questions / guideline gaps
```
