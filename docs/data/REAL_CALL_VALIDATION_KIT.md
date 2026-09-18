# Real Call Validation Kit

Owner: Matheus. Scope: real call source validation — source contracts, ingestion readiness,
raw→canonical validation, participant identity/role evidence, data quality, and (later)
technical prep for Call↔Deal matching. **Not** in scope here: `objection_episode`/taxonomy/
annotation/eval protocol/LLM extractor architecture (Otávio), or CRM discovery/open-deals
audit/WON-LOST-OPEN-STALE semantics/pipeline-stage semantics (Gabriel) — see their handoff
interfaces below instead of duplicating their work.

Goal: when a small, **authorized** real sample arrives, follow this kit without improvising —
and without contaminating the architecture with hypotheses before evidence exists.

```
receive source
    ↓
profile structure safely      (closer_ai.ingestion.profiling)
    ↓
understand source semantics    (Source Discovery Questions, below)
    ↓
map fields                      (RAW_TO_CANONICAL_MAPPING_TEMPLATE.md)
    ↓
validate identity                (Identity & Role Validation, below — TD-01/TD-02/TD-14)
    ↓
adapt source boundary            (evidence-based only — see Source Contract Decision)
    ↓
parse
    ↓
normalize
    ↓
validate Canonical Call
    ↓
measure data quality             (DATA_QUALITY_REPORT.md, CALL_VALIDATION_REPORT_TEMPLATE.md)
    ↓
produce validation report
```

## Authorization gate (absolute, read first)

Before opening, processing, or sending any real data anywhere:

**Is authorization for this specific dataset confirmed?** Check
[`docs/context/HUMAN_DECISIONS.md`](../context/HUMAN_DECISIONS.md) and
[`docs/context/OPEN_QUESTIONS.md`](../context/OPEN_QUESTIONS.md). As of this writing,
authorization for Agro/BeefPoint and Empreende Brazil is **not confirmed**.

If not confirmed: **do not read real customer content.** Everything in this kit — templates,
tooling, runbooks, synthetic fixtures — can be prepared and tested without it. Nothing below
authorizes bypassing this gate.

Real data is never sent to OpenAI, the Anthropic API, any external service, public GitHub, or
public logs. Never copied into public documentation.

## Existing readiness audit

What already existed before this branch, verified against the repo (not assumed):

| Capability | Existed? | Complete? | File | Gap closed by this kit |
|---|---|---|---|---|
| Authorization gate | Yes | Yes | `docs/context/HUMAN_DECISIONS.md` | — |
| Private storage boundary | Yes | Yes | `data/README.md`, `.gitignore` (verified via `git check-ignore`) | — |
| Source manifest | Yes | Partial | `data/manifests/TEMPLATE.yaml` | Added `partner`, `format`, `storage_location`, `ingestion_status`, `validation_status`, `known_limitations` |
| Source profiling | No | — | — | New: `src/closer_ai/ingestion/profiling.py` |
| Source-format discovery | Partial (Agro-specific) | `docs/data/FIRST_CALLS_VALIDATION.md` steps 1-5 | Added a source-agnostic question list below (applies to Empreende too) |
| Field mapping | Partial (diff-only) | `docs/data/SOURCE_CONTRACT_DIFF_TEMPLATE.md` | New: `RAW_TO_CANONICAL_MAPPING_TEMPLATE.md` (open-ended discovery, not just diff-against-hypothesis) |
| Identity validation | Partial (inline) | `docs/data/FIRST_CALLS_VALIDATION.md` steps 9-13 | Consolidated checklist below, explicit TD-01/TD-02/TD-14 cross-reference |
| Speaker validation | Partial (inline) | same | same |
| Timestamp validation | Partial (inline) | same | Consolidated below, deterministic vs. manual split |
| Transcript validation | Partial (inline) | same | same |
| Parser validation | Yes | Yes | `docs/data/FIRST_CALLS_VALIDATION.md` steps 16-19 | — |
| Canonical validation | Yes | Yes | same, step 18; `Call`/`TranscriptSegment` validators | — |
| Quality flags | Yes | Yes | `src/closer_ai/ingestion/agro/parser.py` | — |
| PII safeguards | Yes | Yes | `docs/data/PRIVACY_BOUNDARY.md` | — |
| First-call report | No (call-level granularity) | — | `docs/data/DATA_QUALITY_REPORT.md` is dataset-level | New: `CALL_VALIDATION_REPORT_TEMPLATE.md` |
| Source comparison (Agro vs. Empreende) | No | — | — | Added below |
| Decision log | No | — | — | Added below |

Nothing above was recreated. Existing docs are referenced, not duplicated.

## Minimum data package (what to request)

Full request text (internal + partner-facing): [`REAL_DATA_REQUEST.md`](REAL_DATA_REQUEST.md).
Summary — the smallest package that lets this kit run:

- **3-5 representative Agro calls**, original export format (not converted).
- Per call: transcript, meeting metadata (id, date/time, duration if available), participant
  metadata (if separate from transcript), source identifier.
- Not the full 108-call corpus. Not pre-mapped to `AgroRawCall`.

## Source Discovery Questions (source-agnostic — Agro or Empreende)

Answer with evidence, not assumption, before writing any adapter code:

- What file/container format is this? What does one file represent — one call, one transcript,
  or an export containing multiple calls?
- Encoding? Timezone? Timestamp format (absolute or relative to call start)?
- How are speakers represented? Are speaker IDs stable across files, or only labels?
- Does the source identify host/closer explicitly? Does it identify customer/lead explicitly?
- Are emails or external IDs present anywhere in the structure (not their values — their
  presence)?
- Is duration explicit, or does it need to be derived from segment timestamps?
- Are transcript segments timed? Can speakers overlap?
- Are recordings and transcripts separate artifacts? One transcript per recording, or could one
  file bundle several calls?
- Are any transcripts missing/empty in the sample?

Use `closer_ai.ingestion.profiling.profile_file()` / `profile_directory()` to answer the
structural half of these questions safely (format, keys, counts, timestamp/speaker-like field
names) without opening file content by hand. It never emits values, text, or filenames — see
its module docstring for the exact guarantee. Structural support for a format there is **not**
a claim that AI Closer ingests that source — it's inspection only.

## Identity & Role Validation (TD-01 / TD-02 / TD-14)

The first real validation must specifically answer whether the source can resolve closer, lead,
and other participants — not assume it:

- How do we know who the closer is? Explicit field, or inference?
- How do we know who the lead is? (No automatic inference is implemented or permitted — see
  TD-14 below. `role="lead"` only comes from explicit source evidence.)
- Does the source provide a stable participant id (Zoom UUID, email), or only a name/label?
  (TD-01: today identity is name-based via `_slugify`, which collides on near-duplicate names.)
- Can two different people share a normalized label? Can one person appear under multiple
  labels across the sample? (TD-02: collisions are flagged, not resolved, by the current
  parser.)
- Can CRM data (Gabriel's workstream) supply supporting identity evidence later? Not to be
  answered here — just noted as a future dependency (see Gabriel handoff, below).

**TD-14 rule, restated:** `role="lead"` is never inferred from participant count or topology
("closer + 1 other = lead" was evaluated and rejected — see
[`docs/domain/AGRO_INGESTION_CONTRACT.md`](../domain/AGRO_INGESTION_CONTRACT.md), "Known
limitations"). No LLM is used to guess identity. `role="unknown"` is a legitimate, expected
outcome when the source gives no evidence — not a bug to work around with a heuristic.

## Transcript Validation Checklist

Split explicitly — some checks the parser already makes deterministically, some need a human
to look at (structure only, never content, per the privacy boundary):

**Deterministic (already enforced by `parse_agro_call()`/`Call` validators):**
transcript exists and non-empty; segment `start < end`; every segment's speaker resolves to a
known participant; `segment_index` contiguous from 0; duration present or estimated
(`missing_duration` flag); `occurred_at` timezone-aware.

**Needs human inspection (structure, not content):**
timestamps ordered across the whole call (not just per-segment); timestamps inside call bounds;
overlapping speakers present (crosstalk — allowed by schema, but worth knowing how common);
gaps between segments; duplicate segments; unexpected encoding; obvious truncation (transcript
cuts off mid-call); language (is it Portuguese as expected, or code-switched); overall
usability for extraction (see the known ASR/regional-slang limitation already flagged in
`docs/data/FIRST_CALLS_VALIDATION.md`).

Not everything needs automation in this branch — see `docs/data/CALL_VALIDATION_REPORT_TEMPLATE.md`
for where each finding gets recorded.

## Source Contract Decision (after observing real data)

Record the decision once per source, with evidence, not before:

```
Source: <agro | empreende>
Date: <ISO date>
Evidence: <N samples inspected, via RAW_TO_CANONICAL_MAPPING_TEMPLATE.md + SOURCE_CONTRACT_DIFF_TEMPLATE.md>

Decision:
  A. AgroRawCall already matches the source sufficiently
  B. AgroRawCall needs adaptation (list the specific field changes)
  C. Need a source-specific raw adapter before AgroRawCall (e.g. Empreende is structurally different)
  D. The current conceptual boundary is wrong and should be redesigned

Chosen: <A | B | C | D>
Reasoning: <based on the real examples, not preference>
Next branch: <if code changes follow>
```

Do not preserve an abstraction just because it already exists — see
[`docs/domain/AGRO_INGESTION_CONTRACT.md`](../domain/AGRO_INGESTION_CONTRACT.md): `AgroRawCall`
is a pre-inspection hypothesis, not a confirmed format.

## Agro vs. Empreende: same source or different adapter?

Do not assume equivalence. Once both have at least one real sample, answer directly: is
Empreende structurally the same kind of export as Agro (same tool, similar shape — reuse
`ingestion/agro/` with a new parser function), or does it need its own adapter under
`ingestion/empreende/`? Answer using the same Source Discovery Questions and Raw→Canonical
Mapping Template against both sources side by side — do not build an Empreende parser without
real Empreende files (see `docs/context/TECH_DEBT.md` TD-05/TD-06 for the related "don't
extract a shared helper before a second real source exists" reasoning).

## Gabriel dependency list (Call ↔ Deal, future)

What this workstream will need from Gabriel's CRM discovery before real Call↔Deal matching can
be attempted (not implemented here — see `docs/data/DATA_ACCESS_MATRIX.md`'s matching-signal
table):

- Stable Deal identifier
- Possible Call/meeting identifier stored on the CRM side, if any
- Contact identifiers usable for matching (email/phone — what's actually populated in practice)
- Deal timestamps (`created_at`, stage changes)
- Owner/closer field on the Deal
- Pipeline and stage identifiers (semantics are Gabriel's to define, not assumed here)
- Outcome field/status semantics (again, Gabriel's to define — not re-derived here)

This is a dependency list, not a request to start CRM discovery from this branch.

## Otávio dependency: "CALL READY FOR ANNOTATION"

What "ready" means when handing a validated call to Otávio's Golden Set workflow — the
technical preconditions only, not the annotation guideline content itself (his to define):

- Transcript usable (parsed, no `transcript_parse_error` covering the whole call)
- Canonical Call validated successfully (`normalize_call()` produced a valid `Call`, not just a
  parseable `AgroRawCall` — steps 12-13 of the runbook, distinct from step 11's parse-only check)
- Timestamps sufficiently valid for evidence grounding
- Speaker mapping usable (every segment's `speaker_id` resolves to a known participant)
- Lead resolution known — either resolved (`role="lead"`) or explicitly flagged
  (`unresolved_lead`), never ambiguous/unknown-and-unflagged
- Closer resolution known (resolved or explicitly `metadata_incomplete`)
- Privacy authorization confirmed for that specific call/source
- Source provenance recorded (which manifest, which `dataset_id`)
- Quality flags available and reviewed (`CALL_VALIDATION_REPORT_TEMPLATE.md`)

## Execution Runbook

```
1.  Confirm authorization (docs/context/HUMAN_DECISIONS.md) — STOP if not confirmed
2.  Receive 3-5 real source samples (docs/data/REAL_DATA_REQUEST.md)
3.  Store under data/raw/<source>/ (gitignored — confirm with `git check-ignore -v`)
4.  Register/update a manifest (data/manifests/<dataset_id>.yaml, from TEMPLATE.yaml)
5.  Run structural profile (closer_ai.ingestion.profiling.profile_directory)
6.  Inspect source structure (Source Discovery Questions, above)
7.  Create raw→canonical mapping (RAW_TO_CANONICAL_MAPPING_TEMPLATE.md)
8.  Validate identity/roles (Identity & Role Validation, above)
9.  Compare source with current AgroRawCall assumptions (SOURCE_CONTRACT_DIFF_TEMPLATE.md)
10. Implement minimal evidence-based adapter changes (only if step 9 requires it)
11. Parse samples (parse_agro_call() or the adapted equivalent)
12. Normalize samples (normalize_call())
13. Validate Canonical Calls (schema validators + manual spot-check)
14. Inspect quality flags (docs/domain/AGRO_INGESTION_CONTRACT.md flag table)
15. Produce first-calls report (CALL_VALIDATION_REPORT_TEMPLATE.md per call,
    DATA_QUALITY_REPORT.md for the aggregate)
16. Review (Domain Agent + Evaluator + Reviewer — see below)
17. Only then consider a larger batch (still not all 108 at once — see
    docs/context/EXECUTION_GATES.md "BATCH READINESS")
```

## Review

- **Domain Agent**: source vs. canonical responsibility, participant/role semantics,
  invariants.
- **Evaluator**: first-calls validation criteria, data quality measurements, fitness for the
  future real Golden Set (not its taxonomy/annotation content — Otávio's scope).
- **Reviewer**: unjustified source assumptions, PII leakage, duplicated documentation,
  speculative code, overlap with Gabriel/Otávio, any Canonical Call change, untested tooling.
  Verdict: APPROVE or REJECT with concrete blockers.
