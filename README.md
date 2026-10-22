# AI Closer — Live Sales Copilot

A live sales copilot inside Google Meet for high-ticket sales operations.

[![CI](https://github.com/mori-mkm/closer-ai/actions/workflows/ci.yml/badge.svg)](https://github.com/mori-mkm/closer-ai/actions/workflows/ci.yml)
![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)

**North Star:**

```
Live Call → Commercial Intelligence → Seller Guidance → Manager Intelligence → Sales Learning
```

AI Closer listens to a sales call while it happens, recognizes the lead's objections, and shows the
closer one grounded suggestion of what to say next, built from the operation's own sales knowledge.
Post-call analysis still exists, but the product's first priority is now the live copilot.

> The intelligence can be complex; the seller interface should remain simple.

## Example

```text
Lead:
"Gostei da proposta, mas achei muito caro."

AI Closer:
"Caro em relação a quê: ao que você imaginava,
ao retorno que espera ou à outra opção?"
```

The suggestion comes from the PRICE_BUDGET knowledge unit, is checked against what was actually said
in the call (grounding), and is shown only if it passes.

## What works today

Validated end to end in real Google Meet test calls (own test accounts, no client data):

- **Capture:** Google Meet captions, incremental transcript, closer / lead identification from the
  caption name.
- **Analysis:** objection detection and classification (local `qwen3:8b`), deterministic
  normalization for known live confusions, exact-category knowledge retrieval, grounded Commercial
  Guidance.
- **Fail-closed:** an ungrounded, malformed or ambiguous answer produces no suggestion; showing
  nothing beats showing a false objection.
- **One recommendation at a time:** same category inside a cooldown is kept, another replaces it,
  it expires or can be dismissed.
- **Dock UI** (dark, retractable, bottom left of Meet): **Sugestão** (what to say now, what the
  client said, the objective), **Histórico** (last utterances), **Avançado** (technical data, only
  with `--debug`). States: yellow = listening / analyzing, red = objection detected, blue =
  suggestion ready.
- **Reliability:** delivery with bounded retry, deduplication, `GET /health`, protection against a
  second runtime on the same port, session recovery (history rehydrated after a runtime restart).
- **Evidence:** a 30-minute soak and real Google Meet test calls (see [Reliability](#reliability)).

Also implemented: a post-call pilot runner for transcripts (classification, guidance, next steps,
deterministic chunking for long calls) and the domain core described below.

## Architecture

```text
Google Meet captions
        ↓
Meet Caption Adapter
        ↓
Delivery / Retry / Dedup
        ↓
LiveSalesSession
        ↓
Objection Classifier
        ↓
Policy / Normalization
        ↓
Knowledge Retrieval
        ↓
Commercial Guidance
        ↓
Grounding
        ↓
Recommendation Lifecycle
        ↓
Meet Dock UI
```

Recovery after a runtime restart:

```text
Extension recovery buffer
        ↓
POST /rehydrate
        ↓
Session reconstruction
```

- Chrome extension (`extensions/google-meet/`): caption adapter, delivery, dock.
- Local runtime (`src/closer_ai/live/`): stdlib HTTP server on `127.0.0.1:8765`, one session per
  meeting, analysis in a background worker; nothing leaves the machine.
- AI layer (`src/closer_ai/ai/`): classifier, guidance engine, grounding validator, local Ollama
  provider.

Full description, measured numbers and decisions:
[`docs/product/LIVE_MEET_COPILOT_V0.md`](docs/product/LIVE_MEET_COPILOT_V0.md).

## Setup

### 1. Python package

```bash
git clone https://github.com/mori-mkm/closer-ai.git
cd closer-ai
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
```

### 2. Ollama

```powershell
$env:OLLAMA_FLASH_ATTENTION="1"
$env:OLLAMA_KV_CACHE_TYPE="q8_0"
ollama serve
```

Model: `qwen3:8b` (`ollama pull qwen3:8b`).

### 3. Runtime

```powershell
cd closer-ai
$env:PYTHONIOENCODING="utf-8"
python -m closer_ai.live.server --closer "Matheus" --debug
```

- `--closer`: the caption name(s) of the closer; Meet's "Você"/"You" is always the closer.
- `--debug`: stage logs on stderr and the dock's Avançado panel (test meetings only).
- A second runtime on the same port exits with a clear error. Check it with `GET /health`.

### 4. Chrome extension

1. Open `chrome://extensions`.
2. Turn on **Developer mode**.
3. Click **Load unpacked**.
4. Select `extensions/google-meet`.
5. Open or reload the Google Meet tab.
6. Turn on captions (CC).

## Tests

```bash
pytest -q
ruff check .
node --test extensions/google-meet/meet_adapter.test.js
node --test extensions/google-meet/sidebar_view.test.js
git diff --check
```

Current validated state: 744 Python tests, 12 Meet adapter / delivery tests, 15 dock tests. The
Python suite needs no Docker, database, network or Ollama. CI runs the import check, `ruff check .`
and `pytest -q` on every pull request and push to `main`
([`.github/workflows/ci.yml`](.github/workflows/ci.yml)).

Live benchmarks with a real local model (optional):

```bash
python -m closer_ai.live.bench --runs 5        # latency per stage
python -m closer_ai.live.bench --precision     # 14 invented probe lines
python -m closer_ai.live.soak --minutes 30     # long-call reliability soak
```

## Reliability

- **Bounded retry:** same utterance id, at most 4 attempts with a short backoff; an old line never
  holds back a new one.
- **Failure taxonomy:** every failed attempt and every undelivered utterance has a reason
  (`RUNTIME_UNAVAILABLE`, `HTTP_TIMEOUT`, `REJECTED`, `TOO_OLD`, …); a lost utterance is reported in
  the dock, never silent.
- **Idempotency and duplicate suppression:** the runtime accepts each `(meeting_id, sequence)` once.
- **Health:** `GET /health` reports runtime and model state, no call data.
- **Runtime instance id:** a new id per runtime process; the extension detects a restart from it.
- **Rehydration:** after a restart the extension sends the meeting's utterances back
  (`POST /rehydrate`); they are restored as context only, never re-analyzed.
- **Consistent snapshots:** each `GET /recommendation` is read under one lock; the dock never mixes
  states.

Current evidence:

```text
30-minute soak
0 silent utterance loss
0 retry duplicates
0 technical analysis errors after classifier schema fix
```

## Domain principles

The commercial unit of analysis is the **Deal**, not the call. A deal can span multiple calls, so:

```
Call outcome != Deal outcome
```

`Call` has no outcome field. The canonical commercial outcome lives on the Deal, as an append-only
evidence → assessment chain ([ADR-001](docs/decisions/ADR_001-outcome-contract-v0.md)). The
`Deal.outcome` field is only a legacy projection of the CRM state. Sales knowledge defines concepts;
it never proves that something happened in a call. Only the call's own segments are evidence.

Domain core (implemented with tests, synthetic data only): Canonical Call, Lead / Deal / StageEvent,
Deal Identity, Call ↔ Deal matching (CallDealMatch + MatchDecision), Outcome Domain v0, Sales
Knowledge Base. The durable decisions are in [`docs/decisions/`](docs/decisions/), the conceptual
model in [`docs/architecture/DATA_MODEL.md`](docs/architecture/DATA_MODEL.md).

## Repository structure

```
extensions/google-meet/  # Chrome MV3 extension: caption adapter, delivery/recovery, dock UI
src/closer_ai/
├── live/            # live runtime: session, HTTP server, benchmark, soak harness
├── ai/              # classifier (E0/E1/E2), guidance engine, grounding, post-call, Ollama provider,
│                    # knowledge context, experiment runner
├── demo/            # post-call pilot runner (transcripts, long-call chunking)
├── normalization/   # Canonical Call, Participant, TranscriptSegment, deterministic IDs
├── ingestion/       # Agro/Zoom source-boundary parser (synthetic-validated), source profiler
└── domain/          # Lead, Deal, StageEvent, Deal Identity, matching, Outcome, ObjectionEvent

tests/    # unit + integration tests, hermetic (no network, no Ollama, no real data)
evals/    # synthetic evaluation harness
docs/     # product, decisions (ADRs), architecture, domain, AI, evals, data, knowledge
data/     # local-only staging for real data (gitignored) — never committed
```

## Roadmap

### P0 — Reliability ✅

### P1 — Latency

Otávio is investigating a more robust architecture to reduce the objection → suggestion latency.

### P2 — AgroTalento Playbook

Gabriel is structuring the commercial playbook.

### P3 — Playbook Compliance

### P4 — Opportunity Detection

### P5 — Call Memory

### P6 — Post-call / Manager Intelligence

Full sequencing and the data / evaluation track (authorized real data, golden set, real Outcome
policy): [`docs/product/ROADMAP.md`](docs/product/ROADMAP.md) and
[`docs/context/CURRENT_STATE.md`](docs/context/CURRENT_STATE.md).

## Known limitations

- Latency still depends heavily on the hardware (two sequential local LLM calls; ~14 s median from
  caption to suggestion in the warm synthetic benchmark, higher under memory pressure).
- `qwen3:8b` running locally puts high RAM pressure on the current development machine.
- The active recommendation is not restored after a runtime restart (the history is).
- Follow-up: **Latest Utterance Anchoring / Precision**. With an earlier objection in context, a new
  objection can be ignored. Real case: "Preciso falar com meu sócio antes de fechar." was not
  recognized as a new objection.
- Playbook Compliance and Opportunity Detection are not implemented.
- Classifier accuracy is measured only on invented probe lines and test calls, not on real client
  calls.

## Data and privacy

Do not commit customer data or secrets. That covers transcripts, recordings, CRM exports, names,
emails, phone numbers, API keys and private notes. Treat everything in Git as potentially public.
Fixtures and datasets in the repository are synthetic. Processing real data requires explicit
authorization. The LLM provider is local-only (loopback), and the live runtime stores nothing.
Experiment artifacts go to the gitignored `artifacts/`. See
[ADR-004](docs/decisions/ADR_004-real-data-privacy-boundary.md) and
[`docs/data/PRIVACY_BOUNDARY.md`](docs/data/PRIVACY_BOUNDARY.md).

When a real-world edge case is found, it is recreated synthetically, never copied with names
swapped.

## Contributing / Development workflow

One task, one owner, one branch — one worktree when work runs in parallel. Architecture, schema,
and merge decisions stay human-reviewed; agents never merge their own work. Durable architecture
changes need an ADR ([`docs/decisions/README.md`](docs/decisions/README.md)). Details:
[`AGENTS.md`](AGENTS.md), [`CLAUDE.md`](CLAUDE.md), [`docs/agents/WORKFLOW.md`](docs/agents/WORKFLOW.md).

## Documentation

- [`docs/product/LIVE_MEET_COPILOT_V0.md`](docs/product/LIVE_MEET_COPILOT_V0.md) — live copilot:
  flow, policy, dock, reliability, recovery, measurements
- [`docs/context/CURRENT_STATE.md`](docs/context/CURRENT_STATE.md) — operational snapshot
- [`docs/decisions/`](docs/decisions/) — ADRs (durable decisions)
- [`docs/architecture/`](docs/architecture/) — architecture, data model, integrations
- [`docs/domain/`](docs/domain/) — domain contracts (Deal, identity, matching, outcome, objection)
- [`docs/ai/`](docs/ai/) — classifier, guidance engine, provider, experiment runner
- [`docs/evals/`](docs/evals/) — golden set protocol, annotation guideline, calibration kit
- [`docs/knowledge/sales/`](docs/knowledge/sales/) — Sales Knowledge Base
- [`docs/data/`](docs/data/) — real-data onboarding, privacy, OCI storage
- [`docs/product/`](docs/product/) — MVP scope, roadmap, real-call pilot
- [`docs/agents/`](docs/agents/) — multi-agent development workflow
