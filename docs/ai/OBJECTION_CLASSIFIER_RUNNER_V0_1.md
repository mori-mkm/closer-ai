# Objection Classifier / E0-E1-E2 Runner v0.1

Status: **IMPLEMENTED** — `src/closer_ai/ai/objection_classifier.py`; tests in
`tests/unit/ai/test_objection_classifier.py` and `tests/integration/test_objection_classifier_runner.py`.
Provider **interface only**: no production LLM provider, no external call, no Golden Set evaluation, no
E3 retrieval, no embeddings/vector DB. Domain contract unchanged (D7 open).

## Purpose

The classifier core for the ablation in the
[RAG proposal](SALES_KNOWLEDGE_RETRIEVAL_RAG_V0_1_PROPOSAL.md): same call, same model, same output
contract, only the classification knowledge changes.

```
Canonical Call → prompt (arm) → ClassificationProvider → parse → validate → ClassificationRun
```

## Arms

| Arm | Prompt blocks |
|---|---|
| E0 | TASK RULES · FACTS FROM CALL · OUTPUT REQUIREMENTS |
| E1 | … + `CLASSIFICATION_GUIDE` (8 labels + OTHER with one-line definitions, 5 category rules) |
| E2 | … + EXTERNAL KNOWLEDGE from `build_knowledge_context()` (default card projection) |

TASK RULES, FACTS FROM CALL and OUTPUT REQUIREMENTS are byte-identical in all arms; the arm block
sits between facts and output requirements. E1 is a short constant, not the guideline file and not the
cards. E2 reuses the Knowledge Context Builder output verbatim (RAG-O4 stays open: default projection,
no positive examples/signals). The output requirements list the label names for every arm, so the
output contract does not vary.

## Input boundary

`classify_call(call, arm, provider, knowledge_root=None, knowledge_git_sha=None)` takes the canonical
`closer_ai.normalization.Call`. There is no Deal, Outcome, stage or CRM parameter, and the prompt uses
only segment ids, speaker roles (from `participants`) and text, in `segment_index` order:

```
FACTS FROM CALL

[<segment_id> | lead]
<text>
```

`knowledge_root` is read only by E2 (E0/E1 ignore it; E2 without it fails).

## Prediction model

Eval-layer dataclasses, not `ObjectionEpisode` and not gold:

- call level: `call_detection` ∈ `OBJECTIONS_FOUND | NO_OBJECTION | UNKNOWN`; `uncertain_spans`
  (`segment_ids` + `AMBIGUOUS | UNKNOWN`) for stretches where detection is undecided — no episode;
- `EpisodePrediction`: `prediction_id`, `objection_segment_ids` (`[0]` = anchor), `context_segment_ids`,
  `category_status` (`PRESENT | AMBIGUOUS | UNKNOWN`) + `category` / `category_candidates`,
  `reaction_status` (`PRESENT | ABSENT | AMBIGUOUS`) + `reaction` (decisive response: `ACCEPT | REJECT |
  MIXED | UNKNOWN | CLARIFICATION`) / `reaction_candidates`, `resolution_status`, `summary` (one short
  sentence, ≤ 300 chars; no chain-of-thought is requested or stored).

Categories are the CIT-O1 annotation labels (`CATEGORY_LABELS` = Knowledge Context Builder
`CONCEPT_ORDER` + `OTHER`). Seller handling is not a predicted field: per the contract it is derived
from closer segments in `context_segment_ids`.

## Validation

Shape errors (missing/extra keys, wrong types) raise `MalformedResponseError`. Everything else is
checked by `validate_predictions` and **reported** in `ClassificationRun.validation_errors`, never
repaired or dropped (`run.valid` is false if any):

- segment ids exist in this call, no duplicates, call order; objection ∩ context empty; context after
  the anchor; anchor spoken by a `lead`; all objection segments from the anchor's speaker;
- labels/statuses from the allowed sets; AMBIGUOUS needs ≥ 2 distinct candidates and no value;
  UNKNOWN takes neither;
- `call_detection` consistent with the episode count (NO_OBJECTION never coexists with episodes);
- unique `prediction_id`; no two predictions with the same anchor and category;
- `resolution_status` ∈ the four contract values and consistent with the reaction: ACCEPT → resolved,
  REJECT → unresolved, MIXED → partially_resolved, UNKNOWN/CLARIFICATION/ABSENT/AMBIGUOUS → unknown
  (contract §9.2 + GL-3). AMBIGUOUS is never a resolution value.

The validator does not judge whether a prediction is *correct*; that is the future eval against gold.

## Run artifact and provenance

`ClassificationRun`: `arm`, `runner_version`, `call_id`, `segment_sequence_hash` (contract §11
serialization), `provider`, `model`, `prompt_sha256` (exact prompt bytes), `prompt_chars`,
`prompt_utf8_bytes`, E2-only `knowledge_sha256` / `knowledge_concept_versions` / `knowledge_git_sha`
(passed through by the caller; the core never runs Git), `raw_response`, parsed predictions and
`validation_errors`. No timestamp and no run id: identity is the digests. No token count (tokenizer
depends on the model). The prompt text is not stored (it contains the transcript); `build_prompt`
reproduces it.

## Evidence boundary

Only `segment_id`s from the call can support occurrence; the prompt says so in TASK RULES and OUTPUT
REQUIREMENTS, the E1/E2 blocks are labelled NOT FROM THIS CALL, and the validator rejects any id not in
the call (including free-text quotes).

## Provider interface

```python
class ClassificationProvider(Protocol):
    name: str
    model: str
    def classify(self, prompt: str) -> Mapping[str, Any]: ...
```

A provider receives the exact prompt and returns the parsed JSON object. Provider exceptions propagate
unchanged. Tests use `ScriptedClassificationProvider` (`tests/fixtures/classifier_support.py`).

## Explicitly deferred

Real providers (OpenAI/Anthropic/Gemini/Ollama), model choice, secrets, retries/fallback, async; E3/E4
selection, embeddings, vector DB; Golden Set comparison and metrics; persistence of runs; dirty-tree
rejection and Git SHA capture (orchestration); domain enum migration (D7).

## Smoke test (synthetic 5-segment call, scripted provider, 2026-09-29)

One-off snapshot, not pinned by tests: digests change whenever prompt text, the call or the Knowledge
Base change.

| Arm | chars | UTF-8 bytes | prompt sha256 | knowledge digest | predictions | valid |
|---|---|---|---|---|---|---|
| E0 | 3,568 | 3,569 | `7b35b448…4d7fba05` | no | 1 | yes |
| E1 | 5,098 | 5,101 | `f74f28d1…0174195ffd` | no | 1 | yes |
| E2 | 23,262 | 24,067 | `073045d8…0c8fa45307` | yes | 1 | yes |

Token count not measured.
