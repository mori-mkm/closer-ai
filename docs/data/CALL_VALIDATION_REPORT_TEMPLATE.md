# Call Validation Report Template

Um bloco por call, para as primeiras ~5 calls reais (`docs/data/FIRST_CALLS_VALIDATION.md`,
passo 20). Granularidade de **uma call**, diferente de
[`DATA_QUALITY_REPORT.md`](DATA_QUALITY_REPORT.md) (agregado do lote inteiro). **Nunca contém
PII** — `sample_id` é o id seguro do profiler (`sample_001`, ...) ou do manifest, nunca nome/
email/telefone/transcript.

## Template

```
sample_id: <sample_001, ou id do manifest>

Source format: <ex.: JSON de API, .vtt, .srt>

Parse status: <PASS | FAIL (AgroParseError) | FAIL (unexpected exception)>
Normalize status: <PASS | FAIL | N/A (parse já falhou)>

Participants: <contagem total>
Resolved closer? <YES | NO>
Resolved lead? <YES | NO>
  (se NO: unresolved_lead deve estar em quality_flags — ver TD-14)

Segment count: <contagem>
Duration: <segundos, ou "estimado via missing_duration">
Timestamp quality: <OK | issues — descrever categoria, nunca o valor bruto>

Quality flags: <lista de flags de docs/domain/AGRO_INGESTION_CONTRACT.md>

Critical failures: <lista, ou "nenhuma">
Warnings: <lista, ou "nenhuma">

Canonical compatibility: <produz Call válido? YES/NO — se NO, qual invariante quebrou>

Manual review result: <nota curta do revisor humano, sem citar conteúdo real>
```

## Regra de privacidade

Nenhum campo acima deve conter nome, email, telefone, trecho de transcript, ou qualquer valor
bruto da fonte — só metadados estruturais e status. Ver
[`PRIVACY_BOUNDARY.md`](PRIVACY_BOUNDARY.md). Este relatório, preenchido, é seguro para
commit — o dado bruto que ele descreve nunca é.

## Como usar

Um bloco por call na amostra inicial (`docs/data/FIRST_CALLS_VALIDATION.md`, passos 17-20).
Agregar os ~5 blocos numa tabela resumo simples (sample_id × parse/normalize status × lead
resolvido?) antes de produzir o relatório de qualidade do lote
(`DATA_QUALITY_REPORT.md`).
