# ADR-005 — Classification Provider Boundary (local-first LLM)

## Status

Accepted

Registra uma decisão **já implementada e mergeada**: o classifier com um seam de provider (PR #34) e o
Ollama provider local (PR #35). Aceito formalmente na reconciliação de 2026-09-29. O provedor de
LLM **definitivo** continua sem escolha; este ADR não o escolhe.

Detalhe (**como**): [`OBJECTION_CLASSIFIER_RUNNER_V0_1.md`](../ai/OBJECTION_CLASSIFIER_RUNNER_V0_1.md),
[`OLLAMA_CLASSIFICATION_PROVIDER_V0_1.md`](../ai/OLLAMA_CLASSIFICATION_PROVIDER_V0_1.md).

## Context

- O classifier experimental (E0/E1/E2) precisa de um LLM real para rodar. O projeto também precisa
  poder trocar de modelo ou provedor sem mexer em prompt, validação ou proveniência.
- Transcripts reais ainda não têm autorização de uso nem de envio para cloud
  ([ADR-004](ADR_004-real-data-privacy-boundary.md)).
- Queremos medir se o modelo cumpre o output contract, não esconder falhas.

## Decision

1. **Classifier core → `ClassificationProvider` → implementação.** O core monta o prompt, faz a
   validação de forma e das predições e registra a proveniência. O provider só recebe o prompt
   exato e devolve o objeto JSON. É um `Protocol` com `name`, `model` e `classify(prompt)`, sem
   factory nem registry. O classifier não importa nenhum provider concreto.
2. **O provider é transport/model adapter.** Não muda o prompt e não contém taxonomia, conhecimento
   ou validação de predição.
3. **O primeiro provider real é o Ollama, local-only por decisão de design.** `base_url` só aceita
   `http` em loopback (`127.0.0.1`, `localhost`, `::1`); redirects são recusados e proxies do
   ambiente são ignorados. Uma configuração errada não pode enviar transcript para fora da máquina.
   Remote Ollama fica deferred.
4. **Sem reparo silencioso em v0.1:** output que não é JSON, ou que tem a forma errada, é erro explícito.
   Nada de strip de code fences nem busca por `{`.
5. **Sem retry, fallback de modelo ou backoff em v0.1:** uma chamada termina em sucesso ou em erro
   explícito, registrado como dado de compliance.
6. **Um provider cloud futuro** é outra implementação do mesmo `Protocol`. Ele exige decisão
   explícita de autorização/privacidade para dado real (ADR-004) e configuração de secrets, que
   hoje não existe.

## Alternatives considered

| Alternativa | Por que foi rejeitada |
|---|---|
| Classifier chamando um SDK/provider diretamente | acopla prompt/validação a um vendor; impede comparar modelos |
| Começar com provider cloud | transcript sairia da máquina antes de autorização |
| Reparar JSON / retry automático | esconde falhas do modelo que queremos medir |
| Framework de providers (factory, registry, plugins) | um provider real não justifica |

## Consequences

### Positive

- Trocar modelo/provedor não muda prompt, validação nem proveniência, e os arms continuam
  comparáveis.
- A fronteira de privacidade é imposta pelo código, não por convenção.
- Falhas de compliance ficam visíveis (o Experiment Runner as conta separadamente).

### Negative

- Os modelos locais são menores e mais lentos, e o contexto precisa ser dimensionado (`num_ctx`,
  com risco de truncamento silencioso do Ollama).
- Não há resiliência (sem retry).
- A avaliação de qualidade continua dependendo de gold real (D3), que não existe.

## Implementation status (2026-09-29)

- **IMPLEMENTED:** `ClassificationProvider` (`src/closer_ai/ai/objection_classifier.py`) e
  `OllamaClassificationProvider` (`src/closer_ai/ai/ollama_provider.py`). Testes usam um fake server
  em loopback, sem Ollama no CI.
- **EXECUTED:** smoke local com calls sintéticas (qwen3:8b). É execução, **não** avaliação de
  qualidade.
- **NOT IMPLEMENTED:** provider cloud, remote Ollama, secrets, retry/fallback, async.
