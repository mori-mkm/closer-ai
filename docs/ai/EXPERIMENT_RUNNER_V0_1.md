# Experiment Runner / Run Orchestration v0.1

Status: **IMPLEMENTED** — `src/closer_ai/ai/experiment_runner.py`; tests in
`tests/unit/ai/test_experiment_runner.py`. Operational compliance only: **no quality evaluation**
(no gold, no accuracy/precision/recall/F1, no best arm). No E3/E4. Domain unchanged.

## Purpose

Turn single `classify_call` executions into a repeatable experiment: the same Calls, the same provider
instance and model, every arm, each execution recorded with enough provenance to answer "with which
configuration was this prediction produced?". The runner is not a classifier: it never builds prompts,
chooses labels, evidence or resolution, or retrieves knowledge.

## Flow

```
ExperimentSpec(name, arms, knowledge_root, knowledge_git_sha) + Calls + provider (already built)
  → checks: name, arms ⊆ {E0,E1,E2}, Calls are canonical and unique; E2 → build_knowledge_context once
  → for each Call (given order): for each arm (canonical order E0, E1, E2): classify_call(...) once
  → ExperimentRunRecord per Call × arm → ExperimentResult (+ summary) → write_artifact (JSON)
```

Sequential, single-threaded, one provider instance for every run. The provider is passed in (Ollama,
scripted test double, a future cloud adapter); the runner never constructs one.

## Statuses

| Status | Meaning |
|---|---|
| `SUCCESS_VALID` | output parsed and passed `validate_predictions` |
| `SUCCESS_INVALID_PREDICTION` | output parsed, but breaks rules against the Call (`validation_errors` kept) |
| `MALFORMED_RESPONSE` | `MalformedResponseError`: model output not JSON / not an object / wrong shape |
| `PROVIDER_ERROR` | the provider raised anything else (transport, HTTP, timeout, API response) |

HTTP success ≠ parseable output ≠ valid prediction. These are **compliance** counts, not model quality.
`failure_type` is the exception class, `failure_message` its message.

There is no per-run context-error status: a Knowledge Base problem is global (see below).

## Failure boundary

- **Per run, recorded and continue:** `PROVIDER_ERROR`, `MALFORMED_RESPONSE`, invalid predictions.
  A failure in Call A × E0 never skips A × E1 or other Calls.
- **Global, raise and abort:** invalid spec (name, arms, E2 without `knowledge_root`), non-Call input,
  duplicate `call_id`, invalid Knowledge Base (`KnowledgeBaseError`, before any provider call), Knowledge
  Base changing mid-experiment (an E2 digest differing from the preflight digest), and any unexpected
  exception (bugs are not hidden as run failures). Provider exceptions are identified by wrapping the
  provider, so only exceptions raised *by the provider* become `PROVIDER_ERROR`.

## Provenance

Per run: `call_id`, `segment_sequence_hash`, `arm`, `provider`, `model`, `prompt_sha256` / `prompt_chars`
/ `prompt_utf8_bytes` (of the exact prompt the provider received — known even when the provider then
failed), E2-only `knowledge_sha256`, `knowledge_concept_versions` (concept ids + versions),
`knowledge_git_sha`, `usage`, `elapsed_seconds`, status fields, `call_detection`, predictions,
uncertain spans, `validation_errors`.

Per experiment: arms, `call_ids`, provider name/model, `provider_config` (from the provider's optional
`config` mapping; Ollama: `base_url`, `timeout`, `format`, `think`, `temperature`, `num_ctx`; no
secrets), knowledge digest/versions/Git SHA, `started_at` / `finished_at` (UTC).

The provider configuration (snapshotted before the first run) and usage are **not** in the prompt
digest. A provider without `config` records `{}`; a future cloud adapter should expose one. Timestamps and elapsed times are
observational and not part of any identity; there is no experiment id (the name names the artifact).

**Usage:** the runner reads the provider's optional `last_usage` right after each call (Ollama:
`prompt_eval_count` = prompt tokens, `eval_count` = generated tokens, `total_duration` in ns), through a
per-run wrapper; Ollama resets it at the start of each call, so a failed call never inherits the
previous run's usage. This relies on sequential execution (v0.1). `ClassificationProvider` is unchanged.
No monetary cost is recorded.

Known limits: run order is fixed (Call-major, E0→E1→E2), so model warm-up and prompt caching bias
`elapsed_seconds` across arms — latency is not comparable between arms. Ollama is run with
`temperature: 0` and no seed: generation is more stable, not guaranteed identical. A generation that did
not finish (`done_reason`) is a `PROVIDER_ERROR`; the reason is in `failure_message`.

## Git clean check

`knowledge_git_sha(knowledge_root)` (orchestration only; the classifier and context builder never run
Git) returns `HEAD` of the repository holding `knowledge_root` after checking that the directory has
tracked files and no modified, staged, deleted, untracked or ignored file. Only that directory is
checked: an untracked `docs/evals/calibration/runs/` or any change elsewhere does not block. Git missing,
not a repository, untracked directory, timeout or dirty tree → `KnowledgeGitError`. Commands run as
argument lists, no shell, 10 s timeout. Pass the SHA into `ExperimentSpec`; the runner records it and
never computes it (so it cannot verify a caller-supplied SHA: call `knowledge_git_sha` right before
`run_experiment`). Within the run, every E2 prompt must contain the preflight knowledge block and the
Knowledge Base is rebuilt at the end; any difference aborts. `git update-index --assume-unchanged` /
`--skip-worktree` on a KB file would hide an edit from the check (deliberate action; not handled).

## Artifacts (privacy-first)

`write_artifact(result, out_dir)` writes `<out_dir>/<name>.json` (suggested `artifacts/experiments/`,
gitignored), `artifact_version: "v0.1"`, stdlib `json`, via temp file + `os.replace`, and **refuses to
overwrite** an existing artifact (`FileExistsError`).

Persisted: ids, digests, labels, segment ids, statuses, validation errors, usage, configuration.
**Not persisted:** transcript text, prompt, raw model response, the episode `summary` (free text derived
from the transcript), local `knowledge_root` path.

**Model-produced values are allowlisted.** A model can echo transcript text into any field (an invented
segment id, a label, a JSON key). Before a run is recorded, every label/status value must be a known
token, every segment id must belong to the Call and `prediction_id` must look like a short id; anything
else becomes `<unlisted:N>` (distinct values stay distinct, equal values equal). `validation_errors` are
recomputed on the redacted predictions, so verdicts match the real validation without quoting the
values. `failure_message` keeps only known quoted tokens and is capped at 300 chars. `run.valid` / the
status always come from the unredacted validation.

## Operational summary

`planned_runs` (Calls × arms), `completed_runs`, counts per status overall and `by_arm`, total
`elapsed_seconds`, `prompt_eval_count_total`, `eval_count_total`. Nothing else: without gold there is no
accuracy, and one run per Call × arm cannot say one arm is better.

## Future Golden Set eval

Gold (D3 pilot / Golden Set v1) compared against these run records, per arm, with the metrics in the
[RAG proposal](SALES_KNOWLEDGE_RETRIEVAL_RAG_V0_1_PROPOSAL.md) (invalid runs counted as such).

## Explicitly deferred

Calibration Kit loader (the kit's Markdown is regular, but loading it is its own task — IDs, speaker
mapping and hash verification belong to a Calibration Dataset Loader); CLI; quality metrics and Golden
Set comparison; E3/E4; parallelism/async/retry; opt-in raw prompt/response persistence for synthetic
debugging; redaction of invalid model-produced values; database/dashboard/tracking tools.
