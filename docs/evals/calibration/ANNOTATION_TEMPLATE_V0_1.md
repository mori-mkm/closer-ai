# Annotation Template v0.1

Copie o bloco uma vez por call. Preencha sozinho, sem ver outras anotações, a referência, Outcome,
CRM ou qualquer saída de modelo/RAG. Evidência só por `segment_id` (`CALnn_Sii`), nunca texto.

- Status de pergunta (protocolo): `PRESENT`, `ABSENT`, `UNKNOWN`, `AMBIGUOUS {candidatas}`, `N/A`.
- Category (label set CIT-O1, **não** enum de domínio): `PRICE_BUDGET`, `TIMING_PRIORITY`,
  `NEED_VALUE_FIT`, `AUTHORITY_INTERNAL_BUY_IN`, `TRUST_RISK`, `COMPETITION_EXISTING_SOLUTION`,
  `IMPLEMENTATION_INTEGRATION`, `TERMS_PROCESS`, `OTHER`. Incerteza vai no **Category status**, nunca
  como categoria.
- Rótulos de resposta (contrato §9.1): ACCEPT, REJECT, MIXED, NEUTRAL, OFF_CATEGORY, UNKNOWN; nota
  `CLARIFICATION` para GL-3.
- `resolution_status`: só `resolved`, `partially_resolved`, `unresolved`, `unknown`.

```
# Annotation

call_id:
segment_sequence_hash:          (copie do caso)
annotator:                      (pseudônimo)
mode:                           A (solo) / B (A, B ou adjudicador)
calibration_kit_version: v0.1
guideline_version: v0.1
taxonomy_version: CIT-O1 provisional 8-category set
date:
time spent (min):

## Call-level

annotatable: YES / NO (motivo)
full call reviewed: YES / NO
tier (opcional): happy_path / missing_context / ambiguous / adversarial
call ABSENT (nenhum episódio): YES / NO
NO_OBJECTION trechos (ids + motivo curto):
AMBIGUOUS / UNKNOWN trechos de detecção (ids + leituras candidatas):

## Episode <episode_local_id>

detection status: PRESENT / AMBIGUOUS {…} / UNKNOWN
anchor_segment_id:
objection_segment_ids:
context_segment_ids:

category:                       (label acima, ou vazio se status ≠ PRESENT)
category status: PRESENT / AMBIGUOUS {candidatas} / UNKNOWN
OTHER description (se OTHER):
NEED_VALUE_FIT sub-concept read (se aplicável): need / value / fit

seller_handling_present: PRESENT (ids) / ABSENT
prospect reactions (id → rótulo | nota CLARIFICATION):
reaction status: PRESENT / ABSENT / AMBIGUOUS {leituras} / UNKNOWN

resolution_status: resolved / partially_resolved / unresolved / unknown
decisive response segment (opcional):

notes (observado):
inferred_notes (marcar INFERIDO):
open issue (caso que o contrato/guideline não representa):

## Knowledge Base
consulted: YES / NO
where (unit + seção) and whether it decided something:

## Questions / guideline gaps
```

Se a reação for AMBIGUOUS, `resolution_status` = `unknown` e as leituras vão em notes (GL-3).
