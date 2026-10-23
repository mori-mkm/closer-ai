# Live Meet Copilot v0

Goal: follow a live Google Meet call and show the closer **one** grounded commercial
recommendation while the conversation happens. Post-call analysis is no longer the first priority.

## Status: v0 validated end to end in a real Google Meet (2026-10-21)

Test meeting with two of our own accounts, no client and no client data. Captions in Portuguese.
The lead account said "Eu gostei da proposta, mas achei muito caro." The sidebar showed:

| Field | Value |
|---|---|
| speaker → role | the other participant → `lead` ("Você" → `closer`) |
| category / outcome / reason | `PRICE_BUDGET` / `RECOMMENDED` / `GUIDED` |
| recommendation_state | `ACTIVE` |
| knowledge_unit / move / grade | `guidance.PRICE_BUDGET` / `CLARIFY (PRICE_BUDGET.M2)` / `WEAK` |
| grounding | `VALID` |
| Objeção detectada | Preço / orçamento |
| O que fazer | Esclareça antes de responder |
| O que falar | "Caro em relação a quê: ao que você imaginava, ao retorno que espera ou à outra opção?" |

This confirms every stage in a real meeting: Meet captions → speaker/role → LiveSalesSession →
classifier → normalization/policy → exact-category knowledge → CommercialGuidance → grounding →
recommendation ACTIVE → sidebar. It is **one** validated objection (PRICE_BUDGET) in one test
meeting, not an accuracy measurement.

Also validated in real meetings:
- real caption capture with the current `SELECTORS`;
- speaker attribution from the caption name (`--closer` names and "Você" → closer, anyone else → lead);
- the latest-wins queue and the `active_analysis` / `last_completed_analysis` split (debug panel);
- the recommendation lifecycle up to ACTIVE, and the `--debug` stage logs.

Fixed while getting there (each one has a regression test in `tests/unit/live/`):
- segment ids embedded epoch-ms sequences, so qwen3 returned them as integers and guidance came back
  INVALID_RESPONSE → short per-session ids (`seg_<n>`);
- after a pain line, E1 labeled the price line NEED_VALUE_FIT → `price_override` (below);
- grounding rejected a fact the lead said in an earlier line of the window → two evidence scopes
  (below);
- the sidebar showed the previous line's result while the price line was being analyzed →
  `active_analysis` vs `last_completed_analysis`.

## Flow

```text
Meet captions (DOM) ── MeetCaptionAdapter ── CaptionTracker ── content.js ── background.js
                                                                                  │ POST /live-utterance
                                                                                  ▼
                     127.0.0.1:8765  closer_ai.live.server  (stdlib HTTP, loopback only)
                                                                                  │
LiveSalesSession: utterances → rolling window → trigger → classify_call (E1) → live emission policy
                  → guide_episode (exact-category knowledge + grounding, fail closed) → one recommendation
                                                                                  │ GET /recommendation (0.5 s poll)
                                                                                  ▼
                                     dock on the Meet tab (shadow DOM): suggestion + history + advanced
```

What is reused unchanged: the classifier (`classify_call`, `validate_predictions`, E0/E1/E2), the 8
guidance knowledge units, exact-category retrieval, `guide_episode` / CommercialGuidance, the
grounding validator, the Ollama provider and the `ContextGuard`.
What is new: `src/closer_ai/live/` (session + server) and `extensions/google-meet/`.

## Pieces

| Piece | File | Responsibility |
|---|---|---|
| MeetCaptionAdapter | `extensions/google-meet/meet_adapter.js` | The only code that knows Meet's DOM. Selectors live in `SELECTORS`, with structural fallbacks. A speaker it cannot read is `unknown`. |
| CaptionTracker | same file (pure, no DOM) | Emits a caption block once it has been stable for 1.5 s, or when it disappears. Only new words when a block keeps growing. Never emits the same text twice. Sequence is monotonic. |
| content.js | `extensions/google-meet/content.js` | Wiring: scans captions every 0.5 s, polls the runtime every 0.5 s, draws the dock and its panels, keeps it above the captions. Nothing is stored in the browser. |
| dockView / dockReducer | `extensions/google-meet/sidebar_view.js` | Pure: runtime answer → what the dock shows (tone, status, suggestion, history, advanced lines); which panel is open, badge and toast. Never adds text of its own. |
| background.js | `extensions/google-meet/background.js` | Relays requests to `127.0.0.1:8765`, allowed by `host_permissions` (not by the page's CORS). |
| Runtime | `src/closer_ai/live/server.py` | `POST /live-utterance`, `GET /recommendation`, `POST /dismiss`. One analysis thread per meeting, single flight. Also replays a synthetic stream. |
| LiveSalesSession | `src/closer_ai/live/session.py` | In-memory state, rolling window, trigger, emission policy, recommendation lifecycle, latency timings. |

## Live policy (v0)

- **Speaker → role:**
  - `--closer` names and Meet's "Você"/"You" → closer;
  - `unknown` stays unknown;
  - anyone else → lead (v0 assumes a 1:1 sales call).
- **Rolling context:** the last `--window-seconds` (90), at most `--window-utterances` (12). The
  whole call is never sent.
- **Trigger:** only the *current* utterance can trigger, and only if it is a new lead line of at
  least 12 chars, not ≥ 85 % similar to the last analyzed one. A closer line never triggers, even
  with a lead line still waiting (`[TRIGGER] reason=NOT_LEAD`).
- **Queue (latest-wins):** one pending slot per meeting. A newer eligible lead line replaces the
  pending one (`superseded_leads`), so an objection waits for at most the analysis already running
  (an Ollama call is never cancelled). All utterances stay in the transcript and the window.
- **Emission:** conservative. A recommendation needs all of the following, otherwise
  `NO_RECOMMENDATION`:
  1. a valid classifier run. Context cited from *before* the anchor is dropped first (the trigger is
     always the newest line), then the classifier's own validator runs again;
  2. `OBJECTIONS_FOUND`;
  3. a PRESENT category with guidance knowledge (not OTHER);
  4. an objection segment that is a *new* lead utterance, so an old objection still in the window is
     not shown again;
  5. a single candidate category. NEED_VALUE_FIT becomes PRICE_BUDGET only when the objection words
     themselves contain an explicit price word (caro, preço, orçamento, budget, custo...) and do not
     also deny the need (`price_override`; real Meet: E1 labeled "achei muito caro" NEED_VALUE_FIT
     after a pain line). TIMING_PRIORITY becomes AUTHORITY_INTERNAL_BUY_IN only when the objection
     words state an explicit third-party decision dependency ("falar/validar/aprovar com o meu sócio /
     chefe / diretoria", "quem decide é…", "aprovação do…") and contain no time marker ("mês que vem",
     "viajando", a month, "safra"); a role word alone never counts (`authority_override`; real Meet:
     the caption came as "Preciso falar com o meu sócio antes" and E1 labeled it TIMING_PRIORITY, 4/4
     when reproduced). Both run before retrieval, so the knowledge unit follows the normalized
     category. Logged as `category_before`;
  6. guidance status GUIDED, i.e. grounded. An invented date, number, person or condition rejects it.
     Guidance gets two evidence scopes: *objection evidence* (the episode's segments) and *allowed
     factual call evidence* (every captured segment of the window), so a fact the lead said earlier
     ("Hoje a gente perde tempo...") can be reused. Knowledge never counts as call evidence.
- **One at a time:**
  - same category inside `--cooldown` (25 s) → kept, with no guidance call;
  - another category, or the same one after the cooldown → replaces the current one (REPLACED);
  - after `--ttl` (90 s) → EXPIRED;
  - "Dispensar" → DISMISSED.
  - An analysis that ends in NO_RECOMMENDATION (e.g. a neutral line) does **not** clear the active
    recommendation: it stays ACTIVE until replaced, expired or dismissed, while
    `last_completed_analysis` shows the newer, empty result. Intentional (validated in the real Meet:
    neutral `seg_5` NO_RECOMMENDATION next to the ACTIVE recommendation of `seg_4`).
- **Debug counters (extension):** `captions_seen` = distinct Meet caption blocks (DOM nodes; Meet
  reuses one block per speaking turn and keeps growing its text). `utterances_sent` = utterances the
  tracker emitted and the runtime answered (closer and lead; each stable stretch of a growing block
  is one utterance). So `captions_seen: 2, utterances_sent: 5` is normal.
- **Dock** (bottom left, above Meet's control bar; dark theme). Always visible and small:
  `[● status] [Sugestão] [Histórico] [•••]`. Each button opens one panel above the dock; only one
  panel is open at a time, the same button or "–" closes it, and nothing opens on its own.
  - **Sugestão**, in order of visual weight: what to say now (`suggested_question`, the largest
    text), what the client said (`lead_said`, small, above it), `Objetivo: <move>` (`objective`), the
    objection label and "Dispensar". While a lead line is analyzed it shows "Analisando: “…”"
    (yellow); once the policy has a category and the guidance is still running, "Objeção detectada ·
    <label>" (red dot only). With no active recommendation: "Nenhuma sugestão ativa.";
  - **Histórico**: the last 8 utterances as the runtime accepted them, Closer and Lead labeled, the
    lead's lines brighter, internal scroll;
  - **•••** (Avançado): runtime online/offline, captions on/off and status; with `--debug` also the
    category code, knowledge unit, move, grade, grounding, recommendation state, active segment,
    last completed analysis, last latencies, counters and meeting id. Never opens by itself.
  - States (dot + status text): gray = offline / captions off / error; yellow = "Ouvindo" and
    "Analisando…"; red = "Objeção detectada"; blue = "Sugestão pronta". Only the dot, one label and
    the Sugestão button are colored.
  - A new ACTIVE recommendation does not open a panel: the Sugestão button turns blue with a dot
    and "Nova sugestão" shows for 4 s. If the Sugestão panel is already open it just updates. After
    the closer opens it, the button stays blue (reopen any time) until the recommendation is
    replaced, expires or is dismissed; then the highlight goes away and the history stays.
  - Placement: if Meet's captions reach the dock's column (small windows, long captions), the dock
    moves up above them; panels shrink to the window height. Chat and the right-side controls are on
    the other side.

  Not shown to the seller by default: category code, knowledge unit, move id, grade, grounding,
  segment ids, rationale, latencies. Everything comes from one
  `GET /recommendation` (polled every 0.5 s):
  - `transcript`: the last 8 utterances *as LiveSalesSession accepted them* (`Lead:` / `Closer:`;
    with `--debug`, `raw speaker → role`). A caption that did not reach the session is not shown;
  - `status`: `CAPTURING | ANALYZING | RECOMMENDATION_READY | NO_RECOMMENDATION | ERROR`;
  - `active_analysis` (the lead line being analyzed now: sequence, segment_id, speaker, role,
    text_preview, started_at, and `detected_category`/`label` once the policy decided to emit, before
    the guidance is ready; shown as "Analisando" / "Objeção detectada") and `last_completed_analysis` (sequence,
    segment_id, category, outcome, reason, finished_at; debug "Última análise concluída"). Kept apart
    so an old result is never read as the current line's; a finished analysis swaps both and the
    recommendation under one lock;
  - the active recommendation: `lead_said`, `question`, `objective`, `label`; plus, for debug,
    `category`, `move` (action line), `rationale`, `knowledge_unit`, `move_id`/`move_code`, `grade`,
    `grounding`. Never the whole unit;
  - with `--debug`: those technical fields, counters, `active_segment`, the last completed analysis
    and `debug.latency` (the last analysis' queue/classifier/guidance/end-to-end/displayed ms).
- **Latency:** one JSON line per analysis on stderr, technical fields only: sequence, timestamps,
  outcome/reason, category, prompt/output tokens.
  - `queue_wait_ms` = lead caption received → its analysis started (waiting for a running analysis);
  - `classifier_latency_ms` = analysis started → classifier done;
  - `guidance_latency_ms` = classifier done → guidance done;
  - `end_to_end_latency_ms` = caption received → outcome ready;
  - `displayed_latency_ms` = caption received → first time the panel fetched the recommendation;
  - per stage (v1): `caption_stable_wait_ms` (browser: last caption change → utterance emitted, from
    the extension's `changed_at`), `caption_to_runtime_ms`, `policy_ms`, and per Ollama call
    `ollama_load_ms` / `ollama_prompt_eval_ms` / `ollama_eval_ms` / `ollama_total_ms`;
    `classifier_local_ms` / `guidance_local_ms` = time outside Ollama (prompt build, parse,
    retrieval, validation, grounding).

## Latency v1 (`feat/live-copilot-v1`, 2026-10-21)

Benchmark (reproducible, real Ollama, synthetic lines, model already loaded):
`python -m closer_ai.live.bench --runs 5` and `python -m closer_ai.live.bench --precision`.
RTX 4050 Laptop 6 GB, qwen3:8b Q4_K_M, `num_ctx` 4096.

Where the time goes (price line, before):

| Stage | Time |
|---|---|
| browser: caption stable → emitted (`stableMs`) | 1.5 s (+ up to 0.5 s scan) |
| emitted → runtime, trigger, queue (idle) | ~0 ms |
| classifier prompt build + parse + validation | 10–30 ms |
| Ollama classifier: prompt eval / generation | 0.06–1.0 s / **~8.0 s (135 tokens)** |
| policy + retrieval | 0–1 ms |
| guidance prompt build + validation + grounding | 6–20 ms |
| Ollama guidance: prompt eval / generation | 0.06–0.7 s / **~7.0 s (120 tokens)** |
| recommendation ACTIVE → browser poll | 0–1 s (1 s poll) |

The bottleneck is token generation at ~17 tok/s: `ollama ps` shows the model 30 % on CPU / 70 % on
GPU (6.0 GB with 4k context, ~1.3 GB of the 6 GB VRAM already used by other apps). Smaller
`num_ctx` (3072, 2048) or `num_batch` 128 moved it only to 73–75 % GPU, within noise; not changed.

Applied (each measured; none changes the model, taxonomy, knowledge, grounding or `price_override`):
1. **Guidance output, live only** (`guide_episode(..., live=True)`): one-sentence rationale (it is
   debug-only in the sidebar now) and Ollama structured outputs with `GUIDANCE_SCHEMA` (all keys,
   segment ids as strings). Validation and grounding run unchanged. Output ~118 → ~93 tokens.
2. **Model kept warm:** the runtime loads the model at start (warm-up) and sends `keep_alive` 30m
   (`--keep-alive`). A cold load measured 6.7 s here (23 s in the first real Meet).
3. **Sidebar poll 1 s → 0.5 s.**

| Case (5 runs) | end_to_end median / max, before → after | displayed median / max, before → after |
|---|---|---|
| price | 15.6 / 16.3 s → **13.3 / 14.0 s** | 16.0 / 17.0 s → **13.5 / 14.0 s** |
| authority ("Preciso falar com meu sócio antes de fechar.") | 16.2 / 17.4 s → **14.2 / 15.0 s** | 17.0 / 18.0 s → **14.5 / 15.0 s** |
| neutral ("Hoje temos cinco pessoas no time.") | 1.7 / 2.7 s → 1.6 / 2.5 s, no recommendation | — |

Precision probe (14 invented lines, 8 objections, 6 non-objections; same classifier):
before **4/8** objections shown, 0 false; after **7/8**, 0 false (displayed median 14.0 s). Most
rejected guidance before was `evidence_segment_ids` written as integers; the remaining miss
(NEED_VALUE_FIT) is grounding rejecting an invented "hoje" (fail-closed, as intended).

Real Meet (v1, 2026-10-22, test accounts): "Bom gostei da proposta, mas achei muito caro." →
PRICE_BUDGET / GUIDED / VALID / ACTIVE, correct. "Preciso falar com o meu sócio antes de fechar." →
TIMING_PRIORITY (wrong; caption cut at "antes"), fixed with `authority_override`; after the fix the
same text gives AUTHORITY_INTERNAL_BUY_IN → `guidance.AUTHORITY_INTERNAL_BUY_IN` (M5, WEAK) → GUIDED
→ ACTIVE. "Hoje temos cinco pessoas no time." → NO_RECOMMENDATION, correct. The real-Meet latency
of the corrected authority path was not re-measured. Re-run after the fix (same probe): 7/8, 0 false,
displayed median 16.0 s; the extra ~1.5 s vs the table above is slower generation on the machine
(15.9 vs 17.8 tok/s, same tokens, neutral lines slower too); the normalization itself costs ~4 µs.

Tested and **not** applied:
- compact JSON for the classifier (135 → 85 tokens, −3 s): the model dropped a required key;
  with a schema on the classifier too, one false recommendation (a pain line shown as
  TIMING_PRIORITY) and one invalid run on a neutral line → classifier decisions changed;
- compact JSON for the guidance (−1.3 s more): one worse suggestion out of 8;
- skipping the classifier on "clearly neutral" lines: neutral lines already cost only ~1.7 s
  (28 output tokens); a pre-filter would add false-negative risk for little gain.

Seller-perceived time also includes the browser's 1.5 s caption-stability wait (unchanged: a shorter
wait splits sentences mid-way in Meet's self-revising captions; not measured in a real meeting).

## Reliability (P0)

### Why the dock showed `failed: 4`

Before P0, `utterances_failed` was incremented in `content.js` once per utterance whose single send
did not come back `ok`. Each utterance was sent exactly once, never retried, so every `failed` was an
utterance **lost for good, without saying why**. The ways to get there:
- `background.js`: `fetch` rejected (nothing on 127.0.0.1:8765, e.g. the runtime was being restarted
  while the Meet tab stayed open), or the body was not JSON (another program on the port);
- `chrome.runtime.sendMessage` answered nothing (background service worker restarting).

Two more holes: an HTTP 400 from the runtime was counted as *sent* (its body is JSON), and after the
extension was reloaded under an open tab `sendMessage` throws, so the utterance was neither sent nor
failed. There was no fetch timeout. Any lost line can be a lead objection.

### Delivery contract

`utterance -> id (sequence, unique per tab) -> sent -> one terminal state`, in `delivery.js`:

| Terminal state | Meaning |
|---|---|
| CONFIRMED | runtime answered `ACCEPTED` |
| DUPLICATE | runtime answered `DUPLICATE_SEQUENCE` (a retry of something it already has) or `DUPLICATE_TEXT` (same caption repeated by the same speaker): delivered, never added twice |
| REJECTED | runtime refused it (`EMPTY`, HTTP 4xx); not retried |
| LOST | not delivered, with a reason: `<error>:RETRIES_EXHAUSTED`, `TOO_OLD`, `QUEUE_OVERFLOW`, `EXTENSION_CONTEXT_INVALIDATED` |

Attempt errors (classified by `background.js` / `content.js`, never lumped): `RUNTIME_UNAVAILABLE`,
`HTTP_TIMEOUT` (3 s), `HTTP_<5xx>`, `INVALID_RESPONSE`, `EXTENSION_UNAVAILABLE` (retried);
`REJECTED:HTTP_<4xx>`, `REJECTED:EMPTY`, `EXTENSION_CONTEXT_INVALIDATED` (terminal). Caption capture
itself is reported as state (`Ative as legendas (CC)` when the captions region is missing).

Invariant (tested): `created = confirmed + duplicates + rejected + lost + in_flight`.

- **Retry:** same id, at most 4 attempts, backoff 0.5 / 1 / 2 s, given up after 10 s or when more
  than 20 utterances are pending (oldest first). Each utterance is sent independently, so a line being
  retried never delays a newer one; the runtime only analyzes the newest lead line anyway.
- **Idempotency (runtime):** `(meeting_id, sequence)`; a repeated id answers `DUPLICATE_SEQUENCE` and
  changes nothing. `POST /live-utterance` returns `{accepted, status, id, role}`.
- **Never silent:** a LOST utterance shows `⚠ N` in the dock (tooltip "N falas não entregues ao
  runtime") and a line in the ••• panel; with `--debug` the panel lists counters and reasons.

### Other P0 fixes

- **One runtime per port:** exclusive bind on Windows (`SO_EXCLUSIVEADDRUSE`; Windows otherwise let a
  second process bind 8765 and the extension talked to whichever answered). The second runtime exits
  with `ERROR: AI Closer runtime already running on 127.0.0.1:8765 (...)`.
- **`GET /health`** (no header, no call data): `{"status", "runtime", "model", "model_state"}`;
  `model_state` is `unknown | ready | unavailable`, from the warm-up and every analysis. The dock
  polls it every 5 s: `Runtime offline` vs `Modelo indisponível`.
- **Consistent snapshot:** the `GET /recommendation` status is derived only from session state under
  the session lock (a lead line waiting for the worker counts as ANALYZING); the extension keeps one
  GET in flight at a time, so an older answer never overwrites a newer one.
- **Never stuck analyzing:** any unexpected error inside an analysis ends it as
  `NO_RECOMMENDATION / ERROR:UNEXPECTED:<type>`; `active_analysis` is always cleared.
- **Counters** (debug): extension `captions_seen, utterances_created, utterances_sent,
  utterances_accepted, utterances_retried, duplicates_suppressed, utterances_rejected,
  utterances_failed, in_flight, attempt_errors, failed_reasons`; runtime `received, accepted,
  duplicates_suppressed, rejected, analyses_started, analyses_completed, analysis_errors,
  recommendations_created, model_state`.

### Session recovery after a runtime restart

Real Meet (2026-10-22): after a 2–3 s runtime restart the extension delivered again, but the runtime
started an empty session for the same `meeting_id` (sessions live only in the runtime's memory, and
the extension only resends utterances that were never confirmed), so the history restarted from zero.

Minimal recovery, with the extension as the buffer (no database, not the P5 Call Memory):
- every runtime process has a random `instance` id, returned by `/health` and every
  `GET /recommendation`;
- `delivery.js` keeps, for the open tab, the utterances the runtime holds (ACCEPTED, or
  DUPLICATE_SEQUENCE; not DUPLICATE_TEXT), at most 1,000;
- when the `instance` changes, `Rehydrator` sends them once to `POST /rehydrate {meeting_id,
  utterances}` (retried at the next poll if it fails);
- `LiveSalesSession.rehydrate` inserts them in sequence order with their original ids, speaker and
  text (role recomputed from the runtime's closer names). Context only: no trigger, no pending
  analysis, no recommendation, not counted in `received/accepted` (own counter `rehydrated`);
  idempotent per sequence; anything at or before the newest rehydrated id is never analyzed again.

Not recovered (not reconstructible without inventing): the active recommendation, the last completed
analysis, timings, cooldown, an analysis that was running at the crash. A new lead line after the
restart is analyzed normally, with the rehydrated lines as context.

Verified against the real runtime (`recovery_e2e`): 3 utterances (PRICE_BUDGET ACTIVE) -> runtime killed
2.5 s -> restarted (new instance) -> rehydrated 3, `analyses_started: 0`, history identical -> a new
line became the 4th and was analyzed; delivery 4/4 confirmed, 0 lost, 0 duplicates.

**Validated in a real Google Meet test (2026-10-22, own accounts):** dock UX, delivery (0 silent loss, 0
duplicate by retry), runtime restart with the history restored, no old line re-analyzed, new lines
continuing after it, counters consistent, recommendation lifecycle unchanged.

### Follow-up (separate, not P0): latest-utterance anchoring / precision

Real Meet (2026-10-22): "Preciso falar com meu sócio antes de fechar." → `NO_QUALIFYING_EPISODE` while
the older PRICE_BUDGET recommendation stayed ACTIVE. With an earlier objection in the window, E1
annotates the old line and not the new one (also 52.5 % of the analyses in the 30-min soak ended in
NO_QUALIFYING_EPISODE). Precision work, tracked apart from reliability.

**Fix (branch `feat/latest-utterance-anchoring`): the new lead utterance is the classification target,
the older transcript is context.** Root cause: the classifier got the whole window with "annotate
objections in one sales call" and no notion of which line was new, so an older, still "open" objection
competed with (and often replaced) the new line; the policy then dropped it (`NO_QUALIFYING_EPISODE`) —
or, if the model folded the new line into the old episode, could have repeated the old category.
- **Input contract:** `classify_call(..., target_segment_ids=...)` adds a short `LIVE TARGET` block:
  the lead lines new since the last analysis (the trigger, plus any superseded while waiting) are what
  is analyzed; earlier segments are context for references, short answers and continuations; every
  episode must include a target; pains, facts, current process or agreement are NO_OBJECTION unless
  stated as a reason not to move forward. Eval / post-call prompts are unchanged.
- **Deterministic rule (policy):** an episode qualifies only if it includes a new lead segment and
  every objection segment lies in the same uninterrupted lead turn as one (a continuation). An
  objection from an earlier turn — alone or folded with the new line — never satisfies the current
  analysis.
- Measured (`python -m closer_ai.live.bench --sequences`, 12 live sequences): 9/12 → 12/12 correct
  (0 false positives, 0 wrong categories; false negatives 3 → 0); isolated-line probe unchanged
  (7/8, 0 false). A first wording of the block made "A gente perde bastante tempo com isso." a TIMING
  false positive (3/3); the "pains/facts are NO_OBJECTION" line fixed it (back to the gated
  IMPLEMENTATION, as before).

### Long-call soak

`python -m closer_ai.live.soak --minutes 30` (real runtime over HTTP + real Ollama, invented lines,
retries and repeated captions injected, snapshot checks every 0.5 s, resources every 30 s; output in
`artifacts/live_soak/`). Every 30 s sample also carries the runtime counters, analysis error reasons
and client counters, so a run stopped early still has its data.

First run (2026-10-22, RTX 4050 6 GB, 15.6 GB RAM): planned 30 min, **stopped at 20.5 min by the
host (system RAM critically low)**, so no final summary. From the 42 samples:
- runtime never crashed; health `ready` throughout; model loaded the whole time (70 % GPU);
- runtime RSS 17–39 MB; **Ollama `llama-server` RSS grew 3.5 → 5.9–6.8 GB**; VRAM 5.2–5.4 GB;
- 204 utterances received, 155 accepted, 49 duplicates suppressed (injected retries + repeated
  captions), 0 rejected; 65 analyses started, 64 completed, **27 ended in ERROR** (reasons were not
  yet counted per type; the 1-minute smoke run's one error was `MalformedResponseError`, i.e. model
  JSON off the contract); 5 recommendations.

Second run (2026-10-22, Chrome closed, 5.4 GB free at start): **30.4 min completed**. 0 crash, 0
silent loss, 0 duplicate ids in the transcript, 0 inconsistent snapshots in 3,542 polls; 267
utterances posted, 224 accepted, 69 duplicates suppressed (26 injected retries + repeated captions), 0
rejected; 93 analyses, 14 recommendations. Analysis outcomes, by class:

| class | type | count | % analyses |
|---|---|---:|---:|
| technical error | SCHEMA_VALIDATION (classifier) | 41 | 44.1 |
| fail-closed | NO_QUALIFYING_EPISODE | 29 | 31.2 |
| recommended | GUIDED | 14 | 15.1 |
| fail-closed | UNCORROBORATED_CATEGORY | 3 | 3.2 |
| fail-closed | CLASSIFIER_INVALID | 3 | 3.2 |
| no objection | NO_OBJECTION | 2 | 2.2 |
| fail-closed | AMBIGUOUS_CATEGORIES | 1 | 1.1 |

Root cause (100 % of technical errors): on long windows (up to 12 utterances, several objections) the
classifier answered valid, complete JSON (`done_reason: stop`, not truncated) with an episode that
dropped `category_candidates` (5/7 bad episodes when reproduced) or a corrupted key
(`"obj,ection_segment_ids"`, 2/7). Fix: the live copilot asks Ollama to enforce the classifier's own
output schema (`CLASSIFIER_SCHEMA`: exact keys, types, segment ids as strings, no enums; prompt
unchanged; `classify_call(..., structured=True)`; post-call/eval unchanged). Measured on the same 10
long windows with the live pipeline: malformed 6/10 -> 0/10 (1/10 CLASSIFIER_INVALID, fail-closed);
precision probe unchanged (7/8, 0 false, 0 technical errors).

Memory (Ollama `llama-server`, sampled every 30 s): committed (private) memory flat at ~14.8–15.0 GB
the whole run (no leak); working set 1.7 GB -> ~9.3 GB by minute 14, then a plateau (8.2–9.5 GB) while
system swap fell 7.9 -> 1.5 GB, i.e. pages of the same allocation coming back from swap. The earlier
"3.5 -> 6.8 GB growth" was the same effect. The footprint itself is large for a 15.6 GB machine
(system free RAM ~0.4 GB during most of the run, Chrome closed); that is the model runner's
allocation, not the runtime (26–46 MB). Under that pressure the classifier median was 16.9 s.

Third run, with the fix (2026-10-22, **Chrome open**, 0.3 GB free at start): **30.4 min completed**.
0 crash, 0 silent loss, 0 duplicate ids, 0 inconsistent snapshots in 3,556 polls, health `ready`
throughout; same 267 utterances / 224 accepted / 69 duplicates suppressed. **80 analyses, 0
technical errors** (was 41/93), 20 recommendations (was 14). Fail-closed: NO_QUALIFYING_EPISODE 42
(52.5 %), UNCORROBORATED_CATEGORY 10, CLASSIFIER_INVALID 3, AMBIGUOUS_CATEGORIES 1; NO_OBJECTION 2;
KEPT (cooldown) 2. Ollama committed memory flat (14.7–15.0 GB); working set 4.4–8.0 GB going up and
down with Chrome; system free RAM 0.3–2.0 GB. Latency under that pressure: classifier median 19.7 s
(p95 30.4 s), queue wait median 6.6 s (max 21.4 s), recommendation end to end median 33.2 s (max
66.1 s) — the P1 latency work, not changed here.

Delivery under a runtime outage (real runtime over HTTP, `delivery.js` + the `background.js`
classification, runtime killed for ~3.3 s and restarted): 30 utterances, 58 attempts, 28 retries
(`RUNTIME_UNAVAILABLE`), **30/30 confirmed, 0 lost, 0 duplicates**. A restarted runtime starts with an
empty session (no persistence by design).

## Commercial State v0 (`feat/commercial-state-v0`, 2026-10-23)

The copilot keeps more than objections: an evidence-backed state of the ongoing conversation.

```
Transcript → CommercialEvent (typed, cites segment ids) → CommercialState (deduplicated, incremental)
```

Code: `src/closer_ai/live/commercial_state.py`. This is not `closer_ai.domain.commercial_state`, which
is the post-call Call → current match → Deal → Outcome composition.

**Events (v0, 8 types):** PAIN_IDENTIFIED, IMPACT_IDENTIFIED, STAKEHOLDER_IDENTIFIED,
DECISION_PROCESS_IDENTIFIED, BUYING_SIGNAL_DETECTED, OBJECTION_IDENTIFIED, COMMERCIAL_TERM_MENTIONED,
NEXT_STEP_IDENTIFIED. Each event carries `event_type`, `value` (the lead's own words), `segment_ids`
(canonical evidence), `source_role` (lead), `status` and, for stakeholders only, a `stakeholder_role`.
- `status` is OBSERVED when the fact came from a grounded extraction, CONFIRMED when it came from the
  objection engine.
- `stakeholder_role` is one of mentioned < decision_participant < final_decision_maker.

**State:** the fields `pain_points`, `impacts`, `stakeholders`, `decision_process`, `buying_signals`,
`objections`, `commercial_terms` and `next_steps`. Each field holds one fact per dedup key, with
`value`, `segment_ids` (all evidence ever seen for it, in call order, never removed), `status` and
`role` (stakeholders only). There is also an audit log of the accepted events and what each one did
(ADDED / UPDATED / UNCHANGED).

**Sources, with no duplicated intelligence:**
- OBJECTION_IDENTIFIED comes only from the live objection engine's decision. It is recorded once a
  category passes the policy (anchoring, single category, normalizations, corroboration), with the
  episode's objection segments. It is never classified again.
- Every other fact comes from **one small structured LLM call per pause in the conversation**: the same
  provider and model, with a closed enum schema (~3 s median). The call
  reads the lead lines not read yet, plus up to 6 earlier lines as context.
  - It never runs while a lead line waits for objection analysis, and it waits for 4 s with no new
    utterance and no just-finished analysis (`facts_idle_seconds`). That way it does not hold Ollama
    while the conversation flows, and lines spoken close together share one call.
  - Single-word lead lines ("Ok.", "Sim.") cost no call.
  - `--no-commercial-state` turns it off.

**Grounding (deterministic, fail-closed; `parse_facts`):** a fact is kept only if all of these hold.
1. It is a known non-objection type. The model cannot emit OBJECTION_IDENTIFIED.
2. Its `segment_ids` exist in the call.
3. Its value is an exact span of the cited segments' text, folded for accents, case and punctuation
   and matched on whole words. Any target line that contains the value is added as evidence.
4. The span is in a new lead line or in the other speaker's turn right before it (the question being
   answered); earlier lines of the lead's own turn do not count (Post-call Brief fix, below).
   This way an old fact cannot be re-extracted as new from context.
   - The only exception is a stronger role for a stakeholder already in the state, when the role cue
     is in the new line ("Ele é quem dá a palavra final.").
5. Type-specific rules:
   - a COMMERCIAL_TERM must name an amount, plan, payment, contract or discount, so "achei caro"
     stays the objection engine's;
   - a DECISION_PROCESS must say how the decision is made, so "agora não é o momento" is not one;
   - a stakeholder role above "mentioned" needs a decision cue in that scope, otherwise it is
     downgraded (so "sócio" never becomes "CFO" or "final decision maker" unless it was said).

**Dedup v0:** the key is the folded value without determiners or fillers, so "sócio", "meu sócio" and
"Meu sócio também" are one fact. A repeat adds evidence; a stronger stakeholder role updates the role.
Paraphrases ("tudo manual" vs "fazemos tudo manualmente") stay separate items.

**No UX change:** the state is in the GET `/recommendation` answer (`commercial_state`) and is shown
only in the dock's ••• → Avançado panel (COMMERCIAL STATE, each fact with its `[seg_n]`). The
technical counters appear with `--debug`. The state never produces a suggestion.

**Recovery:** after a restart, `/rehydrate` restores the transcript as before. The background worker
then rebuilds the non-objection facts by extraction only, in chunks over the rehydrated lines:
- no analysis and no recommendation;
- counted as `rebuild_extractions`, not live work;
- idempotent: a resent rehydrate adds nothing and extracts nothing again.

Objections from before the restart are not rebuilt, because that would mean classifying them again;
the state's `objections` restarts empty.

**Measured** (real qwen3:8b, `python -m closer_ai.live.bench --commercial`, 11 invented cases, 17 lead
lines):

| Run | Cases exact | Facts missed | Facts invented/unexpected |
|---|---|---|---|
| first prompt | 6/11 | 4 | 3 |
| final (3 runs) | **10/11** each | 1 | **0** |

- The miss is always DECISION_PROCESS "validar com meu sócio": the stakeholder is recorded, the step
  is not.
- The gates rejected, among others, "achei (muito) caro" as COMMERCIAL_TERM and one ungrounded value
  on the neutral line.
- Objection behavior is unchanged: anchoring sequences 12/12, precision probe 7/8 with 0 false
  recommendations.
- Recommendation latency, one meeting at a realistic pace (on vs off, 2 runs each), was comparable.
  When a lead line arrives while an extraction is already running, it waits for it (up to ~4.5 s seen
  once).

## Post-call Brief v0 (`feat/post-call-brief-v0`, 2026-10-23)

### AUTHORITY gate: stakeholder discovery is not an objection

**Problem:** E1 labeled a short answer to a discovery question AUTHORITY_INTERNAL_BUY_IN.
- Example: "Além de você, alguém participa da decisão?" → "Sim, meu sócio."
- The policy accepted the label, which produced a live recommendation, an `OBJECTION_IDENTIFIED` and
  an `OBJECTION_RAISED` risk in the brief.
- Root cause: no gate checked the category's defining condition. `authority_override` only turns
  TIMING into AUTHORITY.

**Rule:** AUTHORITY_INTERNAL_BUY_IN is now in `CORROBORATION`, the same mechanism as the
IMPLEMENTATION gate. The lead's own objection words must state a dependency that **blocks moving
forward**. Any of these counts:
- an obligation to consult or get approval ("preciso falar com", "precisa aprovar", "vou conversar
  com");
- not being able to decide alone ("não posso decidir", "decidir sozinho");
- moving only after someone's approval ("depois da aprovação");
- a dependency ("depende do").

Naming a stakeholder ("Meu sócio.", "Eu e meu diretor.", "Sou eu e a minha sócia.") is a Commercial
State fact. It gets `UNCORROBORATED_CATEGORY`: no recommendation and no objection event.

**qwen3:8b matrix** (`python -m closer_ai.live.bench --authority --repeat 2`; 6 discovery answers and 6
blocking objections):

| | Discovery false positives | Blocking objections shown |
|---|---|---|
| before | 6/12 | 12/12 |
| after | **0/12** | **12/12** (incl. the real-Meet "Preciso falar com um sócio antes de fechar." and the cut "…sócio antes") |


```
Commercial State = facts        Post-call Brief = presentation of those facts
CommercialState → build_brief → PostCallBrief → JSON (to_json) / Markdown (render_markdown)
```

Code: `src/closer_ai/live/post_call_brief.py`. The brief makes no LLM call and runs no classification.
It reads only the meeting's `CommercialState` and the session's own analysis records.

- **Model:**
  - `meeting_id`, `finalized_at`, `summary`;
  - the 8 state fields, copied as they are: each fact keeps `value`, `segment_ids`, `status` and `role`;
  - `risks` (`code`, `label`, `segment_ids`);
  - `recommendation_stats`: `recommendations_created`, `recommendations_by_category`,
    `categories_detected`, `analyses_completed`;
  - `notes`, which carries coverage caveats.
- **Summary:** deterministic. One fixed pt-BR phrase per non-empty field, with the state values in
  quotes, exactly as they are. It has no coaching and makes no inference, so it can only say what the
  state has.
  - `summary_is_grounded` re-checks that every quoted span is a state value; if not, the summary is
    replaced by "Resumo indisponível (validação de grounding falhou)." (fail-closed).
  - It is the guard an LLM summary would have to pass later.
- **Risks** (deterministic and conservative; knowing a stakeholder is a fact, not a risk):
  - `OBJECTION_RAISED`, one per objection in the state: the copilot does not track resolution;
  - `DECISION_PROCESS_NOT_RECORDED`: a stakeholder with role decision_participant or
    final_decision_maker exists and no decision process was recorded;
  - `NO_NEXT_STEP_RECORDED`: no next step in the state.
  - A "no buying signal" risk was left out on purpose: it would be a judgment, not a fact.
- **Finalize:**
  - `POST /finalize {"meeting_id"}` (or `Runtime.finalize`) waits up to 60 s for the analysis or
    extraction in progress (503 if it is still busy, 404 for an unknown meeting).
  - It then reads the lead lines not read yet, without waiting for a pause, and builds the brief.
  - It is **idempotent**: the first brief is kept on the session and returned again unchanged, with no
    new LLM call and no change to the state or counters.
  - Lines spoken after finalize still feed the live state but not that brief.
- **UI:** the ••• → Avançado panel has a "Finalizar call · brief" button. After finalize, the brief's
  Markdown is shown at the top of that panel (`post_call_brief` in GET `/recommendation`). The main UX
  is unchanged.
- **Persistence:** none. The brief lives in the runtime's memory and is returned by the endpoint.
- **Recovery:** after a restart, the rebuilt state (non-objection facts) gives a valid brief.
  - No objection is analyzed again and no recommendation is created.
  - `notes` says that objections and recommendations from before the restart are not included. That
    is the known Commercial State limitation, and `recommendation_stats` cover this runtime only.

Fix found by the real qwen3:8b run: in "Sim, meu sócio." → "Fazemos tudo manualmente." the model
re-emitted the stakeholder, citing the new line. It passed the grounding because both lines were the
same lead turn. The scope is now the new lead line(s) plus the other speaker's turn right before each
of them. The re-cite is rejected (`NOT_IN_TARGET`), and the commercial bench is unchanged at 10/11
with 0 invented.

## Latency P1 (`perf/live-latency-v1`, 2026-10-23)

Bottleneck (measured with `python -m closer_ai.live.bench --latency`): output tokens, not the prompt.
- The classifier generates ~136 tokens at ~16 tok/s (~8.4 s).
- Guidance generates ~96 tokens (~5.5 s).
- qwen3:8b has only 27/37 layers on the GPU (6 GB).
- Prompt eval is ~1 s for ~1.3–1.5k tokens.
- `think: false` was already sent.

**Kept: the deterministic fast path** (`fast_path_category` in `session.py`, on by default,
`--no-fast-path` turns it off).
- **What it does:** one new lead line that clearly states a price objection ("achei muito caro",
  "não tenho orçamento") or a blocking third-party decision ("preciso falar com meu sócio antes de
  fechar") skips the LLM classifier call.
- **What still runs:** validation, anchoring, the CORROBORATION gates, cooldown, retrieval, guidance
  and grounding run unchanged.
- **What goes to the LLM, as before:**
  - negations ("não achei caro");
  - "caro, mas vale";
  - questions and competitor comparisons;
  - discovery answers ("sim, meu sócio");
  - timing markers and continuations (more than one target line).
- **Observability:** `classification_source` (`deterministic_fast_path | llm`) in each analysis; the
  `fast_path` counters (attempts / hits / llm_calls_saved / by_category) in the `--debug` view.

Matrix: 14 invented scenarios × 5 runs, warm, Commercial State off.

| Config | Classifier median | Guidance median | Displayed median / p90 | Accuracy | Discovery FP | Authority |
|---|---|---|---|---|---|---|
| A: baseline 8b | 8.6 s | 5.9 s | 14.8 / 15.8 s | 60/70 | 0 | 15/15 |
| C: + fast path | 0 s on hits (9.0 s LLM) | 5.9 s | **~6.0 s on hits**, 15.0 s overall | 60/70 | 0 | 15/15 |
| D: qwen3:4b classifier + 8b guidance | 2.9 s | 12.7 s (6.6 s reload) | 15.9 / 19.8 s | **40/70** | 0 | **5/15** |
| E1: KV cache q8_0, 24 of 70 runs | 8.3 s | 5.4 s | 13.7 / 14.5 s | same errors as A | 0 | 6/6 |

- **C:** the fast path hit 20 of 70 runs (obvious price, 3 authority blockers). On those runs,
  displayed went from ~14.5 s to ~6 s.
- **The 10 errors in A and C are the same:**
  - 5 FPs, "Não achei caro" → PRICE: the LLM's error; the fast path sends it to the LLM.
  - 5 FNs on need/value: guidance failed grounding (fail-closed).
- **Rejected:**
  - **Smaller classifier (D).** qwen3:4b and qwen3:8b do not fit in 6 GB together, so every
    guidance call reloads the 8b. It was also much worse at detecting.
  - **Classifier context cut to the last turn.** Same accuracy and a shorter output tail
    (classifier p90 19.6 s → 9.9 s with 10 history lines). But the displayed gain (16.8 s → 15.5 s)
    was mostly Ollama's prompt cache, and only one context-reference case was measured.
- **Optional, environment only (no code):** `OLLAMA_KV_CACHE_TYPE=q8_0` with
  `OLLAMA_FLASH_ATTENTION=1`.
  - Effect: KV cache 576 → 306 MB, 28/37 layers on the GPU, about −1 s displayed.
  - The measurement was cut at 24 of 70 runs by RAM pressure on the dev machine, so it is not
    validated.
  - A separate classifier `num_ctx` on the same model would make Ollama reload the model, so it was
    not tried.

## Runtime configuration (measured)

Default: qwen3:8b, arm **E1**, `num_ctx` **4096**, 1024 tokens kept for the output. Measured on
12 invented one-line streams (5 non-objections, 7 objections; RTX 4050 6 GB, Ollama default config):

| Config | Objections shown correctly | False recommendations | Median detection | Median guidance |
|---|---|---|---|---|
| E1 @ 4k (+ IMPLEMENTATION gate) | **6/7** | **0/5** | 9.3 s | 6.8 s |
| E1 @ 4k (no gate) | 6/7 | 3/5 (all IMPLEMENTATION_INTEGRATION) | 9.3 s | 6.8 s |
| E1 @ 8k | 6/7 | 3/5 | 11.1 s | 7.3 s |
| E0 @ 4k | 5/7 | 3/5 | 8.6 s | 6.5 s |
| E2 @ 12k (does not fit 8k) | 3/7 (+2 wrong category) | 1/5 | 30.9 s | 9.4 s |

- Prompts: ~1.1k tokens for the classifier, ~0.6–0.85k for guidance.
- Outputs: ~140 tokens for the classifier when there is an objection, 28 when there is none;
  ~90–130 tokens for guidance.
- 8k only adds CPU offload. E2's knowledge block (~6k tokens) is too slow for live use.
- The 7th objection (NEED_VALUE_FIT) was detected correctly, but its guidance failed grounding, so
  nothing was shown: this is the fail-closed rule working.

Smoke stream (`examples/live/smoke_price.txt`):
- the pain line → IMPLEMENTATION_INTEGRATION, not shown (`UNCORROBORATED_CATEGORY`);
- "Gostei da proposta, mas achei muito caro." → **PRICE_BUDGET**, shown;
- detection 10.0 s + guidance 7.4 s = **17.4 s** from caption to recommendation;
- classifier 1148 → 148 tokens, guidance 846 → 120 tokens.

Known weakness: "Eu preciso falar com meu sócio antes." (short, no context) was classified
TIMING_PRIORITY. The longer "…antes de fechar qualquer coisa" was correctly AUTHORITY. Accuracy on
short live lines is not measured beyond these 12 synthetic cases.

## Run it

```bash
# 1. synthetic stream, no browser (needs local Ollama with qwen3:8b)
python -m closer_ai.live.server --replay examples/live/smoke_price.txt --delay 2

# 2. runtime for the extension (keep it open; timings go to stderr)
python -m closer_ai.live.server --closer "Matheus"

# 3. latency / precision benchmark (synthetic lines, real Ollama)
python -m closer_ai.live.bench --runs 5
python -m closer_ai.live.bench --precision
python -m closer_ai.live.bench --commercial     # Commercial State: facts found / invented
python -m closer_ai.live.bench --latency --repeat 5 --out lat.jsonl   # per-stage latency matrix
```

Options:
- `--window-seconds`, `--window-utterances`, `--cooldown`, `--ttl`: the live policy above;
- `--arm`, `--num-ctx`, `--reserve-tokens`: the model configuration;
- `--no-fast-path`: always use the LLM classifier (no deterministic fast path for obvious PRICE/AUTHORITY);
- `--no-commercial-state`: no commercial facts extraction (no extra LLM call); objection analysis is
  unchanged;
- `--keep-alive` (default `30m`): how long Ollama keeps the model loaded; the runtime also loads it at
  start;
- `--debug` (temporary, test meetings only): logs every stage to stderr (`[CAPTION] [HTTP] [RUNTIME]
  [TRIGGER] [CLASSIFIER] [POLICY] [GUIDANCE] [GROUNDING] [STATE] [POLL]`, including caption text)
  and fills the dock's ••• panel (raw speaker → role, retrieval provenance, latencies, counters). On
  Windows run `set PYTHONIOENCODING=utf-8` first so names like "Você" print correctly;
- `--port`: the default is 8765. Changing it also requires editing `background.js` and
  `host_permissions` in `manifest.json`.

## Install the extension (unpacked)

1. Open `chrome://extensions` and turn on **Developer mode**.
2. Click **Load unpacked** and select `extensions/google-meet/`.
3. After editing a file, click the reload icon on the extension card, then reload the Meet tab.

## Test meeting (no client)

1. Close any old runtime first. On Windows two processes can bind 8765 at the same time, and the
   extension may keep talking to the old one.
2. Start the runtime: `python -m closer_ai.live.server --closer "<your caption name>" --debug`.
3. Create a Meet with your account plus a second test account or device. Do not use a client or real
   client data.
4. Reload the extension in `chrome://extensions`, then reload the Meet tab. Turn on captions (CC) in
   Portuguese.
5. The AI Closer dock appears at the bottom left, above Meet's controls. Its status goes from
   `Runtime offline` to `Ative as legendas (CC)`, then `Ouvindo`.
6. The test participant says "Gostei da proposta, mas achei muito caro." → `Analisando…` (yellow),
   `Objeção detectada` (red), then, after ~14–16 s, `Sugestão pronta` (blue): the Sugestão button
   gets a dot; open it to read the suggestion.
7. If the status stays at `Ative as legendas` with captions on, or speakers come out as `unknown`,
   update `SELECTORS` in `meet_adapter.js`. Inspect the captions element in DevTools; that file is the
   only place that knows Meet's DOM.

## Current limitations (v0)

- **Latency:** v1 median ~13.5–14.5 s from caption to the sidebar (synthetic, model warm, idle
  queue), plus 1.5 s of caption stability in the browser. Still two sequential LLM calls (~8 s
  classifier + ~5–6 s guidance) at ~17 tok/s, because the model runs 30 % on CPU on a 6 GB GPU. A
  lead line analyzed just before (e.g. a pain line the classifier tags IMPLEMENTATION, ~8–9 s) adds
  queue wait. Not yet re-measured in a real Meet.
- **Classifier accuracy:** the classifier can still pick the wrong category. Accuracy on short live
  lines is measured only on 12 synthetic one-liners plus the one real-meeting line above.
- **Caption segmentation:** a pause of ≥ 1.5 s inside a sentence splits it ("Preciso falar com o
  meu sócio antes" + "de fechar."); the tail is often too short to trigger, so the first half is what
  gets classified. `authority_override` covers the case seen in the real Meet; the splitting itself
  is unchanged.
- **New objection after an old one in the window:** with a price objection earlier in the window, E1
  sometimes annotates only the old line and the new authority line yields `NO_QUALIFYING_EPISODE`
  (reproduced 2/2 synthetically). Not fixed.
- **`authority_override` is a conservative normalization**, same rules as `price_override`:
  TIMING_PRIORITY → AUTHORITY_INTERNAL_BUY_IN only on explicit third-party decision phrases; other
  confusions are not corrected.
- **`price_override` is a conservative normalization**, not a classifier: NEED_VALUE_FIT →
  PRICE_BUDGET only with an explicit price word in the objection text and no need denial. Other
  category confusions are not corrected.
- **Retrieval is deterministic by category** (one knowledge unit per category), not vector or
  semantic search.
- **Only objection guidance is validated** in a real meeting, and only for PRICE_BUDGET. The other 7
  categories were tested on synthetic streams only.
- **Long real calls are not validated** live (a whole sales call, several objections, recommendations
  replacing each other).
- The Meet selectors were verified in real test meetings only; Meet can change its DOM.
- Any non-closer speaker is treated as the lead (1:1 calls only).
- The AUTHORITY gate is a phrase-pattern list: an authority objection phrased without an obligation,
  inability or approval-sequencing verb is not shown (`ponytail:` in `session.py`).
- The IMPLEMENTATION_INTEGRATION gate is a stem list with a recall ceiling (`ponytail:` in
  `session.py`).
- One analysis runs at a time (an Ollama call is never cancelled); latest-wins keeps at most one lead
  line waiting.
- **Post-call Brief v0:** only presents the state, so it inherits its recall misses. In the real
  validation run, "Fazemos tudo manualmente." right after "Sim, meu sócio." gave no pain (2/2; alone it
  gives the pain 2/2). Finalize is explicit (no end-of-Meet detection) and nothing is persisted.
- **Commercial State v0:** facts are the lead's literal words, with small closed type rules (the
  COMMERCIAL_TERM and DECISION_PROCESS cue lists are `ponytail:` word lists). Measured only on 11
  synthetic cases. Dedup is exact-key, so paraphrases are separate items. Closer-stated facts are
  not extracted (the lead's agreement is). Objections are not rebuilt after a restart. An
  extraction already running can delay the next objection analysis by its duration (~3 s).
- No persistence, no audio, no STT, no bot. Captions are the only input.
- **Not built yet:** Playbook Compliance, Opportunity Detection, Manager Intelligence.

## Backlog (from the 2026-10-21 meeting; not implemented)

### B1 — Last utterance + recommendation UX (done in v1, `feat/live-copilot-v1`)

Make this pair the main thing on screen:

```text
Última fala do cliente
+
Sugestão para quebra da objeção
```

### B2 — Playbook Compliance

During the call, for each expected stage: was it covered? → evidence → score / status.

```text
Diagnóstico ✅
Dor ✅
Impacto ❌
Decisor ✅
Proposta ✅
Próximo passo ❌
```

Depends on the **AgroTalento commercial playbook**, which Gabriel is writing.

### B3 — Opportunity Detection

Detect commercial opportunities the closer forgot during the call, for example:
- did not mention payment in 7 installments;
- did not mention the discount for recurring purchases;
- a relevant commercial condition was not presented;
- an important playbook argument was not used yet.

Source: the same future playbook (B2). Not implemented now.
