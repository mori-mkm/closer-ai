# Ollama Classification Provider v0.1

Status: **IMPLEMENTED** — `src/closer_ai/ai/ollama_provider.py`; tests in
`tests/unit/ai/test_ollama_provider.py` (fake Ollama on loopback; no Ollama needed in CI). First real
provider of the [Objection Classifier](OBJECTION_CLASSIFIER_RUNNER_V0_1.md). Local only. Not a
permanent project requirement: it is one adapter behind `ClassificationProvider`.

## Purpose

Run the existing E0/E1/E2 runner against a local model:

```
Canonical Call → classifier prompt (arm) → OllamaClassificationProvider → POST /api/generate
  → model JSON → classifier shape check → classifier validation → ClassificationRun
```

The provider is transport only. Prompt assembly, arms, knowledge, the output contract, parsing and
validation stay in `objection_classifier`; the provider sends the prompt byte-for-byte and returns the
model's JSON object.

## Local-only boundary

- `base_url` must be `http://` on `127.0.0.1`, `localhost` or `[::1]`, with no path, query or
  credentials; anything else (remote hosts, LAN/public IPs, `0.0.0.0`, `https://`) is a `ValueError` at
  construction. Remote Ollama is deferred on purpose, to protect future real transcripts.
- HTTP redirects are refused (a 3xx becomes an error; the `Location` is never requested).
- `HTTP(S)_PROXY`/system proxy settings are ignored (the opener has an empty `ProxyHandler`).

## Configuration

```python
OllamaClassificationProvider(model="qwen3:8b", base_url="http://127.0.0.1:11434", timeout=300.0, num_ctx=16384)
```

`model` is required and never read from env/config. `num_ctx` matters: Ollama **silently truncates**
prompts longer than its context window (a 12k-token probe was cut to ~2k with the server default), and
E2 is ~6.5k tokens on qwen3:8b. Size `num_ctx` to the largest arm; `provider.last_usage["prompt_eval_count"]`
shows what the model actually read. The provider does not detect truncation itself, and `num_ctx`
is not in `ClassificationRun`: record it with the run. `localhost` is trusted by name (OS resolver);
`127.0.0.1` is the safest setting.

`format: "json"` and `think: false` are part of the measured configuration (they shape model behaviour).
`think` is sent to every model; very old Ollama builds may reject it.

## Request / response

Request: `{"model", "prompt", "stream": false, "format": "json", "think": false, "options":
{"temperature": 0, "num_ctx"}}`. `format: "json"` is Ollama's plain JSON mode (no schema);
`think: false` asks thinking models not to produce reasoning. `temperature: 0` makes generation more
stable, not deterministic — the deterministic parts are prompt assembly, digests and validation.

Three layers, three outcomes:

| Layer | Failure | Raised |
|---|---|---|
| transport (HTTP) | connection refused, timeout, non-2xx, redirect | `OllamaError` |
| Ollama API JSON | not JSON, no string `response`, `done` not true | `OllamaError` |
| model content | not JSON, or JSON that is not an object | `MalformedResponseError` |
| classifier shape | wrong keys/types | `MalformedResponseError` (classifier) |
| classifier semantics | invalid predictions | `run.validation_errors` (not raised) |

## No repair, no retry

No stripping of code fences, no searching for `{`/`}`, no quote or enum fixing, no filling of missing
fields: a non-compliant model output is an explicit error, so model compliance can be measured. One
request per call: no retry, backoff or fallback model.

## Metadata and privacy

`run.provider == "ollama"`, `run.model` = the exact model name (existing run fields). Ollama's
`prompt_eval_count`, `eval_count` and `total_duration` (ns) are kept in `provider.last_usage` —
observational, not in the run, the digests or prediction identity. The provider receives only the
prompt (no Deal/Outcome/CRM/stage), logs nothing and writes nothing to disk.

## Local smoke

Requires a running Ollama with the model already installed (`ollama list`; the provider never pulls).

```python
from closer_ai.ai.objection_classifier import classify_call
from closer_ai.ai.ollama_provider import OllamaClassificationProvider

provider = OllamaClassificationProvider(model="qwen3:8b")
for arm in ("E0", "E1", "E2"):
    run = classify_call(call, arm, provider, knowledge_root=Path("docs/knowledge/sales/objections"))
    print(arm, run.valid, run.validation_errors, [e.category for e in run.episodes], provider.last_usage)
```

Use a synthetic `Call` only. Don't commit raw model output.

Smoke 2026-09-29 (qwen3:8b, one synthetic 5-segment price-objection call; execution check, **not an
evaluation**): all three arms returned HTTP 200 and parseable JSON; E1 and E2 were valid, E0 was invalid
(context segment before the anchor). prompt_eval_count 990 / 1,317 / 6,446.

## Explicitly deferred

Remote or authenticated Ollama; cloud providers (OpenAI/Anthropic/Gemini) and OpenAI-compatible
generic providers; JSON-schema-constrained output; retries/fallback; streaming; async; usage metadata
in `ClassificationRun`; truncation detection beyond `num_ctx` sizing; Golden Set scoring and RAG
evaluation.
