# ADR-004 — Real-Data Privacy and Storage Boundary

## Status

Accepted

Consolida regras que já governam o projeto, mas estavam espalhadas em `AGENTS.md`,
[`data/README.md`](../../data/README.md), [`PRIVACY_BOUNDARY.md`](../data/PRIVACY_BOUNDARY.md),
[`OCI_SHARED_STORAGE.md`](../data/OCI_SHARED_STORAGE.md) e
[`HUMAN_DECISIONS.md`](../context/HUMAN_DECISIONS.md). Não cria política nova. Aceito
formalmente na reconciliação de 2026-09-29. As autorizações de uso de dados reais **não** são decididas aqui:
continuam pendentes como decisões humanas.
ADR Accepted ≠ dado real autorizado ou produção validada.

Detalhe técnico (**como**): `PRIVACY_BOUNDARY.md` (o que pode entrar no Git, redação/recriação) e
`OCI_SHARED_STORAGE.md` (bucket, IAM, runbook).

## Context

- O produto processa transcrições de calls e dados de CRM de empresas parceiras. Esses dados contêm
  PII direta e indireta: nomes, telefones, valores, jeito de falar.
- O repositório é compartilhado entre pessoas e agents. O conteúdo do Git deve ser tratado como
  potencialmente público, seja qual for a visibilidade atual.
- Agora existe um classifier com provider de LLM. Um provider remoto enviaria o transcript para
  fora da máquina.

## Decision

1. **Dado real de cliente nunca entra no Git.** Isso inclui transcrições, gravações, exports de CRM,
   nomes/emails/telefones, ids identificáveis, secrets e output de modelo derivado de dado real sem
   revisão. Fixtures e datasets versionados são sintéticos, recriados em vez de redigidos.
2. **Autorização explícita antes de processar dado real.** Isso vale para o uso de cada corpus
   (Agro, Empreende, CRM) e para enviar transcript real a qualquer sistema externo ou cloud. É uma
   decisão humana (`HUMAN_DECISIONS.md`) que nenhum agent toma.
3. **O dado bruto fica dentro de um perímetro autorizado:**
   - local, em `data/raw/`, `data/interim/` e `data/processed/private/` (gitignored);
   - ou no storage compartilhado privado, quando autorizado.
4. **O storage compartilhado candidato é OCI Object Storage** (bucket privado `NoPublicAccess`,
   versionado, IAM por prefixo). Está provisionado e passou num smoke test com dado 100% sintético.
   Ele **não** é plataforma de dados de produção, e nenhum dado real foi enviado. O primeiro upload
   exige autorização, decisão de storage e revisão de acesso confirmadas.
5. **Processamento local é aceitável e é o padrão atual.** O LLM provider v0.1 é local-only
   ([ADR-005](ADR_005-classification-provider-boundary.md)).
6. **Artifacts de experimento são privacy-first por padrão.** Persistem ids, digests, labels
   estruturados e metadata operacional. Não persistem texto de transcript, prompt, resposta crua do
   modelo nem summary livre. Valores produzidos pelo modelo fora da allowlist são redigidos. Ficam
   em `artifacts/`, que é gitignored.
7. **Hash não é anonimização.** Os ids determinísticos nunca derivam de PII, e os adapters não podem
   usar como `source_id`/`external_id` um valor que já seja PII.

## Alternatives considered

| Alternativa | Por que foi rejeitada |
|---|---|
| Versionar amostras reais "pequenas" ou redigidas | texto redigido ainda carrega PII indireta (PRIVACY_BOUNDARY) |
| Compartilhar dado por envio manual de arquivos | sem registro reproduzível do que chegou, quando e sob qual autorização (motivação do OCI) |
| Provider de LLM em cloud desde o início | enviaria transcript para fora do perímetro antes de qualquer autorização |

## Consequences

### Positive

- Fronteira única e explícita para pessoas e agents, e o Git fica seguro por construção.
- Os experimentos já produzem artifacts que não vazam transcript.

### Negative

- Validar contra dado real fica bloqueado por decisões humanas (autorização, storage, acesso).
- O processamento local limita o tamanho de modelo e a velocidade.
- A política de storage (`OCI_SHARED_STORAGE.md`, "MVP storage policy") ainda precisa de sign-off
  humano.

## Implementation status (2026-09-29)

| Regra | Status |
|---|---|
| `.gitignore` de dados reais e secrets; fixtures sintéticas | IMPLEMENTED |
| OCI bucket privado | PROVISIONED, smoke-tested só com dado sintético; **sem dado real** |
| Ollama local-only (loopback, sem redirect/proxy) | IMPLEMENTED (`src/closer_ai/ai/ollama_provider.py`) |
| Artifacts privacy-first + redação de valores do modelo | IMPLEMENTED (`src/closer_ai/ai/experiment_runner.py`) |
| Autorização de uso dos corpora reais | **HUMAN BLOCKER — pendente** |
| Autorização para enviar transcript real a provider cloud | **HUMAN BLOCKER — nenhum provider cloud existe** |
| Sign-off da política de storage para dado real | **HUMAN BLOCKER — pendente** |
