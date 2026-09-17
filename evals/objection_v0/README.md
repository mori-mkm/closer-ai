# evals/objection_v0

Evaluates `RuleBasedObjectionExtractor` (`src/closer_ai/ai/objection_extraction.py`) — the
deterministic, keyword-based v0 reference implementation of `ObjectionExtractor` — against a
100% synthetic golden set. No real client data anywhere in this directory.

## What this evaluates

Extraction of `ObjectionEvent`s (`src/closer_ai/domain/objection.py`) from a canonical `Call`
(`src/closer_ai/normalization/models.py`). Scope is deliberately narrow for v0: a
rule-based/deterministic extractor, no real LLM call, no CRM/Deal/Outcome linkage yet (see
`docs/agents/tasks/objection-event-v0.md`).

## Metrics and why

Chosen in this evaluator's design phase, appropriate to a v0 with a small synthetic golden
set and no human-labeled corpus:

- **Schema validity** — every emitted item is an already-validated `ObjectionEvent` instance.
  A gate, not a rate to optimize (Pydantic construction would raise otherwise).
- **Evidence grounding** — every emitted event's `(call_id, segment_id)` resolves to a real
  segment on the source `Call`, spoken by a `role="lead"` participant. Catches the
  closer-quoting-the-lead attribution trap and any dangling id.
- **Detection precision/recall** — emitted events vs. the golden set's expected events,
  compared by `objection_id` (itself a deterministic function of `call_id` + `segment_id` +
  `category`, so this is exact identity comparison, not fuzzy text matching).
- **Unsupported/extra-extraction rate** — emitted events absent from the expected set (false
  positives), as a fraction of everything emitted. This is the available operationalization
  of "hallucination rate" at this stage: there's no separate human-labeled corpus to check
  emitted text against, only the golden set's own ground truth.

**Explicitly not measured yet** (see the design-phase report for full rationale):
inter-rater category-agreement kappa (no second labeler exists), fine-grained taxonomy F1
(v0's taxonomy is deliberately coarse), latency/cost (deterministic, no network call), and
anything tied to `Deal`/`Outcome` (not part of the v0 contract).

## Golden set

`golden_set.py` builds each entry as a synthetic `Call` (via
`tests/fixtures/synthetic_objection_calls.py`) paired with the `ObjectionEvent`s a correct
extractor should produce for it. Coverage: true negative (no objection), single objection,
multiple objections across categories/segments, same category repeated in different segments
(must be two distinct events), same category twice in one segment (must collapse to one
event), closer-only objection-shaped language (must yield nothing — role trap), ambiguous
phrasing and a cross-segment split objection (both documented recall-gap true negatives, not
bugs), and a minimal valid call.

## Running it

```
python evals/objection_v0/run_eval.py
```

Prints schema validity, evidence grounding, precision, recall, and unsupported rate, plus any
false negatives/positives/grounding failures by golden-set entry name. Exits 0 on a clean
pass, 1 otherwise.

Adversarial unit tests for the same cases live in `tests/unit/ai/test_objection_extraction.py`
(extractor) and `tests/unit/domain/test_objection.py` (the `ObjectionEvent` contract itself).
