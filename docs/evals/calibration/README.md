# Synthetic Annotation Calibration Kit v0

## Purpose

Treinar o anotador A, o anotador B e o adjudicador no
[protocolo](../GOLDEN_SET_ANNOTATION_PROTOCOL_V1.md) e na
[guideline](../OBJECTION_ANNOTATION_GUIDELINE_V0.md) **antes** do pilot D3 com calls reais.
Pergunta: *três pessoas conseguem executar o processo corretamente antes de usarmos dados reais?*

## What this kit is

Calibração operacional sintética: 3 calls curtas, templates manuais e uma referência para discussão
posterior.

## What this kit is not

Não é Golden Set, não é ground truth, não é benchmark de modelo, não substitui o pilot D3, não
serve para definir thresholds, fechar a taxonomia ou treinar LLM. Não avalia nem pontua pessoas.

## Files

| Arquivo | Quem usa | Quando |
|---|---|---|
| [`SYNTHETIC_CASES_V0.md`](SYNTHETIC_CASES_V0.md) | A, B, adjudicador | desde o início |
| [`ANNOTATION_TEMPLATE_V0.md`](ANNOTATION_TEMPLATE_V0.md) | A, B | anotação |
| [`ADJUDICATION_TEMPLATE_V0.md`](ADJUDICATION_TEMPLATE_V0.md) | adjudicador | adjudicação |
| [`REFERENCE_ANSWERS_V0.md`](REFERENCE_ANSWERS_V0.md) | todos | **só no fim** |

## Recommended workflow

1. A lê a guideline.
2. B lê a guideline.
3. A e B recebem **apenas** `SYNTHETIC_CASES_V0.md`.
4. Cada um preenche `ANNOTATION_TEMPLATE_V0.md` para as três calls, sozinho.
5. A e B **não** consultam `REFERENCE_ANSWERS_V0.md`.
6. As duas anotações são comparadas (manualmente, pareando episódios por sobreposição dos segmentos
   de objeção na mesma call, como no protocolo).
7. O adjudicador recebe as calls + A + B.
8. O adjudicador preenche `ADJUDICATION_TEMPLATE_V0.md`.
9. Só então todos abrem `REFERENCE_ANSWERS_V0.md` e discutem.
10. A equipe registra dúvidas e lacunas da guideline (seção abaixo).

**Não edite a guideline durante um caso.** Uma mudança descoberta na calibração vira proposta para a
próxima versão (v0.1), aplicada depois.

## Blindness rules

- A e B **não** consultam: a referência, a anotação do outro, Outcome do Deal, estágio do CRM ou
  qualquer saída de modelo.
- O adjudicador **não** é A nem B e **não** consulta a referência antes de produzir sua adjudicação.
- `REFERENCE_ANSWERS_V0.md` só entra depois da adjudicação.

## Calibration review (registro manual, depois das três calls)

- Episódios encontrados por A e por B, por call.
- Tipos de divergência (DETECTION, BOUNDARY, CATEGORY, HANDLING, RESOLUTION, APPLICABILITY).
- Dúvidas sobre a guideline.
- Tempo aproximado por call.
- Decisões que continuaram AMBIGUOUS.
- Pontos em que A ou B dependeram de inferência.

**Sem** threshold de agreement, **sem** kappa obrigatório, **sem** nota de aprovação dos anotadores.
É diagnóstico.

## Exit criteria

A calibração termina quando dá para responder:

1. A e B entendem o que é objeção?
2. Localizam a evidência por segment id?
3. Separam observado de inferido?
4. Identificam handling e reação?
5. Usam UNKNOWN, AMBIGUOUS e N/A corretamente?
6. O adjudicador resolve ou preserva divergências?
7. Os templates são utilizáveis?
8. Alguma regra da guideline precisa mudar antes do D3?

Nenhuma concordância numérica mínima é exigida.

## Open decisions exercised

GL-1 (CAL02), D6 (CAL03: pendência declarada como resposta), GL-2 só como observação se alguém
ler o "vou pensar" de CAL03 como resposta ininteligível, TAX (categorias provisórias em CAL01 e
CAL03). O kit expõe essas dúvidas; não as resolve.

## Privacy

Tudo é **sintético**: nenhum nome, telefone, e-mail, empresa, Deal ou call real, e nenhum texto
copiado de transcript real. Por isso estes arquivos podem ficar no Git. Anotações feitas por pessoas
reais sobre estes casos também são sintéticas, mas as do pilot D3 (calls reais) **não** entram no Git.
