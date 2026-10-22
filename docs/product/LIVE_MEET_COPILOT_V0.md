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
                                     sidebar on the Meet tab (shadow DOM): transcript + recommendation
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
| content.js | `extensions/google-meet/content.js` | Wiring: scans captions every 0.5 s, polls the runtime every 0.5 s, draws the sidebar. Nothing is stored in the browser. |
| sidebarView | `extensions/google-meet/sidebar_view.js` | Pure: runtime answer → what the sidebar shows (status, transcript lines, recommendation, debug lines). Never adds text of its own. |
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
- **Sidebar** (right side, above Meet's controls; "–" minimizes). Order, top to bottom (v1):
  1. **Cliente disse**: the lead's objection words, verbatim (`lead_said`);
  2. **Sugestão**: what to say now (CommercialGuidance's grounded `suggested_question`), the largest
     text on the panel; under it, small, `Objetivo: <move>` (`objective`) and the objection label;
  3. "Analisando agora" while a lead line is being analyzed;
  4. the transcript, smaller (context only);
  5. the debug section, only with `--debug`.

  Not shown to the seller by default: category code, knowledge unit, move id, grade, grounding,
  segment ids, rationale. All of them stay in the debug section. Everything comes from one
  `GET /recommendation` (polled every 0.5 s):
  - `transcript`: the last 8 utterances *as LiveSalesSession accepted them* (`Lead:` / `Closer:`;
    with `--debug`, `raw speaker → role`). A caption that did not reach the session is not shown;
  - `status`: `CAPTURING | ANALYZING | RECOMMENDATION_READY | NO_RECOMMENDATION | ERROR`;
  - `active_analysis` (the lead line being analyzed now: sequence, segment_id, speaker, role,
    text_preview, started_at; shown as "Analisando agora") and `last_completed_analysis` (sequence,
    segment_id, category, outcome, reason, finished_at; debug "Última análise concluída"). Kept apart
    so an old result is never read as the current line's; a finished analysis swaps both and the
    recommendation under one lock;
  - the active recommendation: `lead_said`, `question`, `objective`, `label`; plus, for debug,
    `category`, `move` (action line), `rationale`, `knowledge_unit`, `move_id`/`move_code`, `grade`,
    `grounding`. Never the whole unit;
  - with `--debug`: those technical fields, counters, `active_segment`, the last completed analysis.
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
```

Options:
- `--window-seconds`, `--window-utterances`, `--cooldown`, `--ttl`: the live policy above;
- `--arm`, `--num-ctx`, `--reserve-tokens`: the model configuration;
- `--keep-alive` (default `30m`): how long Ollama keeps the model loaded; the runtime also loads it at
  start;
- `--debug` (temporary, test meetings only): logs every stage to stderr (`[CAPTION] [HTTP] [RUNTIME]
  [TRIGGER] [CLASSIFIER] [POLICY] [GUIDANCE] [GROUNDING] [STATE] [POLL]`, including caption text)
  and adds the debug section to the sidebar (raw speaker → role, retrieval provenance, counters). On
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
5. The AI CLOSER sidebar appears on the right, above Meet's controls. Its status goes from
   `Runtime offline` to `Ative as legendas (CC)`, then `Capturando`.
6. The test participant says "Gostei da proposta, mas achei muito caro." → `Analisando fala do
   lead…`, then, after ~16–25 s, the PRICE_BUDGET recommendation.
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
- The IMPLEMENTATION_INTEGRATION gate is a stem list with a recall ceiling (`ponytail:` in
  `session.py`).
- One analysis runs at a time (an Ollama call is never cancelled); latest-wins keeps at most one lead
  line waiting.
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
