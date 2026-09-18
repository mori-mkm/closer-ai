# Source Contract Diff Template

Template para comparar hipótese atual (`AgroRawCall`/`docs/domain/AGRO_INGESTION_CONTRACT.md`)
contra o formato real da fonte, campo a campo, quando a amostra chegar
(`docs/data/FIRST_CALLS_VALIDATION.md`, passo 15). Copiar um bloco por campo relevante.

## Template

```
Field: <nome do campo>

Current assumption:
<o que AgroRawCall/AGRO_INGESTION_CONTRACT.md assume hoje>

Observed:
<o que a amostra real mostrou — deixar "???" até haver dado>

Difference:
<divergência exata, ou "nenhuma" se bater>

Impact:
<o que quebra ou fica incorreto no pipeline se a divergência não for tratada>

Required code change:
<mudança mínima necessária em parser.py/models.py, ou "nenhuma">

Breaking?
<YES/NO — YES se exigir mudar o contrato de AgroRawCall ou Call; NO se for só ajuste
interno do parser>
```

## Exemplo preenchido (ilustrativo, não é dado real)

```
Field: duration_seconds

Current assumption:
Já vem em segundos (AgroRawCall.duration_seconds), sem conversão.

Observed:
???

Difference:
???

Impact:
Se a fonte real vier em minutos (comum na API do Zoom), toda duração seria interpretada 60x
menor do que o real, quebrando a checagem de duration_mismatch em Call e distorcendo qualquer
análise futura de duração de call.

Required code change:
Se confirmado minutos: multiplicar por 60 em parse_agro_call() antes de popular
raw_input["duration_seconds"] — mudança local ao parser, não ao contrato de AgroRawCall.

Breaking?
NO — é um ajuste de parsing, não uma mudança de schema.
```

## Campos a preencher assim que a amostra chegar

Lista de partida — mesma tabela de `docs/domain/AGRO_INGESTION_CONTRACT.md` ("Contrato de
input"), qualquer linha marcada "SIM" na coluna "Hipótese não validada com dado real":
`meeting_id`, `occurred_at` (formato + timezone), `duration_seconds` (unidade),
`participants[].label|name|id`, `transcript[].speaker`, `transcript[].start`/`.end`
(absoluto vs. relativo), `closer`. Um bloco do template acima por campo, preenchido durante
`docs/data/FIRST_CALLS_VALIDATION.md`.
