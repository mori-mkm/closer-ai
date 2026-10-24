# Real Call Validation & Calibration v1

Measures the live copilot as a **commercial system** on whole calls. It covers objections, opportunities,
the Commercial State, compliance, the seller card and latency. It is measurement only: the harness never
changes production behavior, and a finding becomes a separate fix PR.

```
calls (canonical JSONL | calibration kit)
  -> replay, one utterance at a time, in virtual time (python -m closer_ai.live.eval)
  -> trace.jsonl (one event per utterance / analysis / facts extraction)
  -> metrics vs annotations (only what is labeled is scored)
  -> EVAL_REPORT.md + false_positives.jsonl + false_negatives.jsonl
```

## Data policy

| What | Where | Git |
|---|---|---|
| Real calls (transcripts, PII) | `data/raw/real_calls/*.jsonl` | **never** (`data/raw/` is ignored, ADR-004) |
| Annotations of real calls | `data/raw/real_calls/*.annotations.jsonl` | **never**: they quote the call |
| Run outputs (trace with call text, metrics, report) | `artifacts/eval/<label>-<time>/` | **never** (`artifacts/` is ignored) |
| Schema, README, synthetic fixtures | `evals/real_calls/` | yes |

Processing real calls still needs the authorization in `docs/context/HUMAN_DECISIONS.md`. Until then,
`--real` finds nothing and says `NOT_FOUND`.

## Call format (canonical JSONL, one utterance per line)

```json
{"meeting_id": "call-001", "speaker": "Ana", "role": "lead", "text": "Achei caro.", "sequence": 7, "timestamp": 1730000000.5}
```

- `role`: `closer` | `lead` | `other`.
- `sequence`: an integer, unique per call. Order is by `sequence`.
- `timestamp`: optional, in epoch seconds/ms or ISO-8601. Without it, lines are `--gap` seconds apart
  (default 6).
- `outcome`: optional call metadata (e.g. `won`), used only for sampling.
- **Roles reach the runtime through the speaker name,** like in Meet. The `closer` speakers are added to
  the runtime's closer names. Any other speaker, including `other`, is a lead for the runtime, exactly as
  live; the trace keeps both `role` and `runtime_role`.

**Adapters:**
- the Synthetic Calibration Kit v0.1 tables (`docs/evals/calibration/SYNTHETIC_CASES_V0_1.md`, read in
  place);
- canonical JSONL.

Add one for the real format (vtt/srt/json) when it arrives.

## Annotation contract

Schema: [`annotation.schema.json`](annotation.schema.json), validated on load (an invalid record stops
the run). One JSONL record:
- **without `sequence`:** labels the call (`scope`, `expected_rules`, `source`, `known_failure`);
- **with `sequence`:** labels one utterance.

```json
{"meeting_id": "call-001", "source": "human", "annotator": "matheus",
 "scope": {"objections": "COMPLETE", "opportunities": "PARTIAL", "facts": "PARTIAL", "seller_action": "PARTIAL"},
 "expected_rules": {"E6-R1": "SATISFIED"}}
{"meeting_id": "call-001", "sequence": 42,
 "expected_objection": {"present": true, "category": "PRICE_BUDGET"},
 "expected_opportunities": ["OP-03"],
 "expected_facts": [{"type": "stakeholder", "value": "sócio"}],
 "seller_action_quality": "GOOD"}
```

**`scope` per dimension:**
- **COMPLETE:** every lead line was reviewed, so a detection on an unlabeled line is a false positive.
- **PARTIAL:** only the labeled lines count (recall, plus explicit `present: false` negatives).
- **NONE:** not reviewed, reported as **UNLABELED**.

When a call has no `scope`, a dimension with labels counts as PARTIAL.

**Utterance fields:**
- **`expected_objection.present`:** `true`, `false`, or `"AMBIGUOUS"`. AMBIGUOUS lines are never scored.
- **`category`:** a CIT-O1 label or `UNKNOWN`. UNKNOWN counts for detection but not for category.
  `acceptable_categories` lists the accepted alternatives.
- **`accept_at`:** the episode's other lead lines, where a detection still counts for this label (for
  example, the lead reaffirming the objection).
- **`expected_opportunities`:** an OP id, or `{"id": "OP-03", "final_status": "RESOLVED"}` for resolution
  accuracy.
- **`expected_facts`:** the type is one of pain, impact, stakeholder, decision_process, buying_signal,
  commercial_term or next_step. The fact matches when the extracted fact is on the same line (or
  `accept_at`) and one value's words contain the other's (folded).
- **`expected_seller_action`:** the card that should be on screen before the next utterance:
  `{"source": "OBJECTION|OPPORTUNITY|NONE", "id": "OP-14 | PRICE_BUDGET"}`.
- **`seller_action_quality`:** `GOOD`, `ACCEPTABLE`, `BAD` or `WRONG_MOMENT`, for human judgment of
  usefulness.
- **`known_failure`:** a pattern id (`NEGATION`, `PAIN_AS_OBJECTION`…). The case is reported
  `KNOWN_FAILURE` while it fails and `UNEXPECTED_PASS` once it passes, so the mark can be removed.

After an unlabeled run, `review_template.annotations.jsonl` holds stubs for the lines where the copilot
did something. It never pre-fills an expectation.

## Metrics

| Dimension | Metrics |
|---|---|
| Objections | precision, recall, false positive rate (FP / labeled negative lead lines), false negative rate, category accuracy, FP/FN by category, category confusion, duplicates |
| Opportunities | precision, recall, false and missed opportunities, duplicates, resolution accuracy, per OP |
| Commercial State | fact precision (only with `facts: COMPLETE`), fact recall, per type |
| Compliance | per expected status (SATISFIED/PENDING/VIOLATED/UNKNOWN): correct/total, confusion, rule coverage (evaluated / playbook) |
| Seller action | correct source, correct priority (id), action available when needed, stale card, duplicate card (same category/OP as a new card within 90 s), quality label counts |
| Latency | FAST_PATH, LLM_CLASSIFIER, OPPORTUNITY_ONLY: utterance received → card available (median/p90/p95/max); NO_RECOMMENDATION separately (time to decide nothing, never a 0) |

- **Error patterns** are heuristic labels for review: NEGATION, PAIN_AS_OBJECTION,
  DISCOVERY_AS_OBJECTION, CONTEXT_LEAK, STALE_OBJECTION, MISSED_BUYING_SIGNAL,
  MISSED_DECISION_DEPENDENCY, TOO_SHORT, GUIDANCE_FAILED (the objection was detected but its guidance failed
  closed, so another card or none was shown) and others.
- **A coalesced line** (said while an analysis ran, then replaced by a newer lead line) is not lost: the next
  analysis reads every new lead line as a target. A miss there is `MODEL_FN_IN_BATCH` (the model or a gate
  missed it in that batch); `PIPELINE_COALESCED` means no analysis ever read it.
- **Inspectors:** `false_positives.jsonl` and `false_negatives.jsonl` hold, per error, the text, the
  previous 5 utterances, what the engine did (category, source, outcome, recommendation), the Commercial
  State and the opportunities at that moment.

## Replay fidelity

`Runtime` / `LiveSalesSession` run unchanged, in virtual time:
- **Clock:** the session clock follows the call's timestamps, plus the real time each model job takes.
  TTL, cooldown, the window and the facts pause therefore behave as in the call.
- **Worker:** the single-flight, latest-wins worker of `Runtime._kick`. A lead line said during an
  analysis waits, and a newer one replaces it (`COALESCED`).
- **Known limit:** a job runs before the lines said during it are added, so its input is exact. Their
  snapshot is taken at the job end (`visible_at`).
- **Latency:** recommendation latencies come from the session's own timings. The dock's 0.5 s poll is not
  added.

## Commands

```bash
# known regression suite + synthetic calibration kit (12 calls)
python -m closer_ai.live.eval --fixtures --label baseline-qwen8b

# real calls (once authorized), a deterministic diverse sample of 10
python -m closer_ai.live.eval --real --sample 10 --seed v1 --label baseline-qwen8b

# any input, an explicit output directory
python -m closer_ai.live.eval --input data/raw/real_calls --label candidate-fix --out artifacts/eval/candidate-fix

# each finished call is saved at once (trace.jsonl / sessions.jsonl). After an interruption, or after new
# annotations, rescore without any model call, or resume the remaining calls:
python -m closer_ai.live.eval --rescore artifacts/eval/baseline-qwen8b-<time>
python -m closer_ai.live.eval --resume artifacts/eval/baseline-qwen8b-<time>

# compare two runs (read only)
python -m closer_ai.live.eval --compare artifacts/eval/baseline-qwen8b-<time> artifacts/eval/candidate-fix-<time>
```

**Options:**
- `--no-fast-path` and `--no-commercial` give A/B configurations.
- `--calls id1,id2` picks calls.
- `--model` and `--num-ctx` set the Ollama model.
- A run never overwrites another: the directory name carries the time.

**Sampling** (`--sample N --seed S`) is deterministic:
- calls are tagged price / authority / think / short / medium / long / outcome:*;
- a round-robin over the tags picks them, each tag ordered by `sha256(seed:id)`;
- the chosen ids go to `config.json`.
