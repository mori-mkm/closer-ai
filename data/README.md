# data/

Este repositório é **público**. Nenhum dado real de cliente entra aqui — nunca.

Proibido versionar: transcrições, exports de CRM, nomes/telefone/e-mail de lead, gravações,
tokens, API keys, IDs identificáveis, ou output de LLM que contenha informação identificável.

`data/raw/`, `data/interim/` e `data/processed/private/` estão no `.gitignore` — use-os
localmente para dado real, eles nunca serão commitados.

Se um teste ou eval precisa de exemplo de call/CRM, use dado **sintético ou anonimizado**
apenas em `tests/fixtures/` ou `evals/datasets/` — nunca uma amostra real, mesmo pequena.

## Estrutura local recomendada

Nenhuma destas pastas existe versionada (todas cobertas pelo `.gitignore` — `data/raw/`,
`data/interim/`, `data/processed/private/`, recursivo). Criar localmente conforme o dado
chegar, não antecipadamente:

```
data/
├── README.md
├── raw/
│   ├── agro/          # arquivos originais recebidos (vtt/srt/json/etc.), sem transformação
│   ├── empreende/
│   └── kommo/          # export/API response original
├── interim/
│   ├── agro/           # outputs intermediários de exploração manual (docs/data/FIRST_CALLS_VALIDATION.md)
│   ├── empreende/
│   └── kommo/
└── processed/
    └── private/         # qualquer output processado que ainda contenha PII
```

Não criar subpastas além destas três fontes sem necessidade real — ver
`docs/data/REAL_DATA_REQUEST.md` para os três pacotes de dado que justificam esta estrutura.

## Manifest de dataset recebido

Quando um lote de dado real chega, registrar um manifest **sem PII** em
`data/manifests/<dataset_id>.yaml` (este arquivo pode ser versionado — só contém metadados
operacionais, nunca o dado em si). Template: `data/manifests/TEMPLATE.yaml`. Campos:
`dataset_id`, `source` (agro/empreende/kommo), `partner`, `received_at`, `received_from_role`
(Partner Owner/Product-RevOps/etc.), `format`, `record_count`, `files` (nomes de arquivo, não
conteúdo), `contains_pii` (sempre `true` para dado real), `authorization_status` (ver
`docs/context/HUMAN_DECISIONS.md`), `storage_location`, `ingestion_status`,
`validation_status` (ver `docs/data/REAL_CALL_VALIDATION_KIT.md`), `checksum` (sha256 do
arquivo, para detectar reenvio duplicado sem reabrir o arquivo), `known_limitations`, `notes`.
Sem pipeline de código para isso agora — é só um template documental, preenchido manualmente.
