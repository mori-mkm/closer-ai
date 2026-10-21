# Real-call Pilot (Value Sprint v0.2): product validation of the guidance

Status: **ready to run, blocked on authorization** (ADR-004). No real call has been processed.

This is **product validation**, not a quality benchmark, accuracy certification, Golden Set or causal
evidence. Gabriel and a closer read the outputs of 5–10 real calls, to decide what to improve next.

## Main question

> **"Depois de ler essa orientação, um closer saberia melhor o que fazer?"**

## Before running

1. **Written authorization** to use the calls (see `docs/context/HUMAN_DECISIONS.md`).
2. **Private folders outside this repository** for inputs and outputs. The CLI refuses an `--out-dir`
   inside the repo unless it is under the gitignored `artifacts/`. Real calls go outside the repo.
3. **A local Ollama** with `qwen3:8b` (loopback only; nothing leaves the machine).
4. **One `.txt` per call**, one utterance per line as `<speaker>: <text>`, in call order.
   - Speakers are the labels `closer`, `lead` and `other`, or real labels mapped with `--roles`.
   - The adapter keeps the order, the speaker of every line and the text, except leading and
     trailing spaces.
   - It **fails** on a line without `speaker:`, on an unmapped speaker or on an empty utterance. It
     never guesses who is lead or closer.
   - Convert the real export by hand or with a local script, and never commit the transcripts.

## Command

```bash
python -m closer_ai.demo.analyze_call "D:/pilot/calls" \
  --out-dir "D:/pilot/out" \
  --roles "Renato=lead,Ana=closer" \
  --num-ctx 40960 \
  --continue-on-error
```

Output:
- `<call>.json` + `<call>.md` per call;
- `review_sheet.csv`;
- a summary such as `summary: SUCCESS=6 INVALID=2 INPUT_TOO_LARGE=1 ERROR=0`.

| Status | Meaning |
|---|---|
| SUCCESS | Nothing the model wrote was rejected. |
| INVALID | Some model output was rejected by a validator (listed under "Avisos" in the Markdown). The call still has an output, with less content. |
| INPUT_TOO_LARGE | The call may not fit the model context. **It is not analyzed:** no output is written and nothing is truncated, chunked or summarized. |
| ERROR | The call failed to run: parse error, Ollama down, malformed JSON. |

### Context size (no silent truncation)

Ollama silently truncates a prompt that is longer than `num_ctx`. The CLI therefore refuses any prompt
whose conservative size estimate does not fit:
- the estimate is 2.5 chars/token (the measured ratio on these prompts is 3.1–3.6);
- 2048 tokens are reserved for the output;
- the output is also discarded if Ollama reports a prompt that fills that budget.

Rough capacity with the E2 classifier (the transcript is sent whole):

| `--num-ctx` | Transcript that fits | |
|---|---|---|
| 16384 (default) | ~12k chars, ~10 min of conversation | |
| 40960 | ~74k chars, ~60 min | qwen3:8b's native maximum; more RAM/VRAM, slower |

A call that still does not fit comes back INPUT_TOO_LARGE: note it, and do not cut it by hand to make
it fit.

## Review sheet (`review_sheet.csv`, UTF-8, opens in Excel)

| Column | Filled by | Values |
|---|---|---|
| `source_file`, `call_id` | pipeline | — |
| `detected_category` | pipeline | CIT-O1 label(s), `;`-separated; `NONE` = no objection |
| `recommended_move` | pipeline | move id(s), e.g. `PRICE_BUDGET.M2` |
| `knowledge_grade` | pipeline | WEAK = practice hypothesis, no measured effect |
| `next_step_detected` | pipeline | yes / no |
| `risk_count` | pipeline | number of rule-based risks |
| `pipeline_status` | pipeline | SUCCESS / INVALID / INPUT_TOO_LARGE / ERROR |
| `human_category_correct` | reviewer | yes / no |
| `human_guidance_useful` | reviewer | **2** useful and actionable · **1** partially useful · **0** useless or wrong |
| `human_guidance_grounded` | reviewer | yes / no: does every fact in the guidance appear in the call? |
| `human_next_step_correct` | reviewer | yes / no |
| `human_better_recommendation` | reviewer | what the closer should have been told, in your words |
| `human_error_category` | reviewer | when something is bad, one or more from the taxonomy below, `;`-separated |
| `human_notes` | reviewer | free text |

**Do not paste transcript content into the sheet.** It stays next to the outputs, in the private
folder.

### Error taxonomy

| Code | When |
|---|---|
| `WRONG_OBJECTION` | wrong category, or an objection that is not one (or one that was missed) |
| `WRONG_MOVE` | the move chosen from the knowledge is not the right one for this situation |
| `GENERIC_GUIDANCE` | correct but too generic to change what the closer does |
| `UNGROUNDED_GUIDANCE` | the guidance asserts something the call does not support |
| `BAD_SUGGESTED_QUESTION` | right move, but the question is awkward, unnatural or counterproductive |
| `MISSED_NEXT_STEP` | a next step said in the call is missing |
| `WRONG_NEXT_STEP` | the owner, action or date is wrong |
| `WRONG_END_POSITION` | the lead's end position is wrong |
| `INSUFFICIENT_CONTEXT` | the guidance needed information the system did not use (an earlier call, the rest of the call, the offer) |
| `OTHER` | none of the above; explain in `human_notes` |

## Product Validation Metrics

```bash
python -m closer_ai.demo.pilot_summary "D:/pilot/out/review_sheet.csv" > "D:/pilot/out/summary.md"
```

It prints:
- calls in sheet / reviewed;
- **A. Usefulness:** % of scores 2, 1 and 0, and the average;
- **B. Trust:** grounded rate;
- **C. Understanding:** category and next-step accuracy (shown as `% (yes/answered)`);
- **D. Failure modes:** error-category counts;
- **E. Examples:** the calls scored 2 and 0, with their better recommendation and notes;
- grouped free-text feedback.

An invalid human value (e.g. `3`, `talvez`, an unknown error code) stops the summary with the list of
cells to fix. It is never dropped silently.

## Product gate and decision (after the review, not before)

Report A–E from the summary. Describe examples in repo docs only in anonymized or synthetic form. Then
recommend **one** next step, from the failure modes:

| Dominant failure modes | Recommendation |
|---|---|
| `GENERIC_GUIDANCE`, `WRONG_MOVE`, `BAD_SUGGESTED_QUESTION`, `INSUFFICIENT_CONTEXT` | **A. Improve the Guidance Engine** |
| `WRONG_OBJECTION` | **B. Improve objection classification** |
| `MISSED_NEXT_STEP`, `WRONG_NEXT_STEP`, `WRONG_END_POSITION` | **C. Improve next-step extraction** |
| Usefulness mostly 2 and few errors | consider **D. Manager Intelligence** |

Nothing is implemented automatically from the pilot.

## What this pilot does not do

- **No inter-annotator agreement, gold labels or metrics** that could be cited as accuracy. Those
  belong to the D3 pilot and the Golden Set protocol.
- **No change to the knowledge** based on 5–10 calls. Observations go to Gabriel as open questions.
