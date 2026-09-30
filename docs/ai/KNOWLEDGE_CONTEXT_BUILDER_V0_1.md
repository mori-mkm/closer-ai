# Knowledge Context Builder v0.1

Status: **IMPLEMENTED** — `src/closer_ai/ai/knowledge_context.py`, tests in
`tests/unit/ai/test_knowledge_context.py`. Full-context knowledge assembly only: no retriever, no LLM,
no embeddings, no vector DB, no RAG eval. (Used by the E2 arm of the
[classifier](OBJECTION_CLASSIFIER_RUNNER_V0_1.md), which was implemented later.)

## Purpose

First code step of the [Sales Knowledge Retrieval & RAG v0.1 proposal](SALES_KNOWLEDGE_RETRIEVAL_RAG_V0_1_PROPOSAL.md)
(the "Context Builder" of E2): turn the Sales Knowledge Base Markdown into a deterministic
**EXTERNAL KNOWLEDGE** block plus the provenance a future extraction/eval run needs.

```
docs/knowledge/sales/objections/*.md → validate/parse → KnowledgeUnit × 8 → classification cards
  → EXTERNAL KNOWLEDGE block → sha256
```

## Input

A directory with exactly one `<NAME>.md` per concept in `CONCEPT_ORDER` (today
`docs/knowledge/sales/objections/`) and no other `.md` file. The builder reads only this directory:
no transcript, Deal, Outcome, CRM, network or environment.

## Output

`build_knowledge_context(knowledge_root, concept_ids=None, sections=CARD_SECTIONS) -> KnowledgeContext`

| Field | What | Goes into the LLM context? |
|---|---|---|
| `text` | header + one card per concept | yes (this *is* the block) |
| `sha256` | hex SHA-256 of `text.encode("utf-8")` | no — run provenance |
| `units` | parsed `KnowledgeUnit`s, in rendered order | no — run provenance |
| `concept_ids`, `concept_versions` | derived from `units` | no — run provenance |

`KnowledgeUnit` holds only what the files contain: `name`, `concept_id`, `version`, `status`,
`source_strength`, `source_ids` (`SRC_*` from `## Sources`) and every `## ` section body. Also public:
`load_knowledge_units(root)` and `render_card(unit, sections)`. Errors raise `KnowledgeBaseError`
(`ValueError` subclass).

## Card projection

Default `CARD_SECTIONS` (exact headings from the corpus):

```
Definition · Use when · Do not use when · Minimum transcript evidence ·
Negative / falsifying signals · Often confused with · Ambiguous examples · Observed vs inferred risks
```

A card is `=== NAME ===`, then `concept_id` / `version` / `status`, then `### <heading>` + body for
each projected section. Not projected: Positive signals, Positive examples, Counterexamples, Framework
mappings, Source-backed notes, Sources, Open questions. Sources, source strength and URLs stay in the
unit for provenance, never in the card.

**RAG-O4 stays open.** Positive examples/signals are parsed but not projected by default; an eval arm
can pass another `sections` tuple without changing the parser.

## Invariants

- **Negative knowledge is mandatory.** Every unit must have non-empty `NEGATIVE_SECTIONS` (Do not use
  when, Negative / falsifying signals, Often confused with, Ambiguous examples, Observed vs inferred
  risks); `render_card` rejects any projection that drops one. A card is never positive-only.
- **Fail explicit.** Wrong first line, text before the first section, duplicate section, missing or
  empty required section (card sections, `Metadata`, `Sources`), missing metadata key, `concept_id`
  not equal to `objection_category.<file stem>`, no `SRC_*` id, missing concept file or unknown `.md`
  file → `KnowledgeBaseError`. Nothing is skipped or partially rendered. A UTF-8 BOM fails as a wrong
  first line (not silently stripped).
- **Evidence boundary.** The header states the block defines provisional annotation categories, is not
  evidence of anything in the call, that only transcript `segment_id`s support occurrence, and that
  examples are synthetic. The builder never adds transcript, Deal, Outcome, CRM or stage content.
- **Taxonomy ≠ domain enum.** `CONCEPT_ORDER` is the CIT-O1 annotation order, defined once in the
  module; it is not derived from `ObjectionCategory`.

## Deterministic ordering

Output order is `CONCEPT_ORDER`, never filesystem order, mtime or set/dict iteration of file listings.
A caller subset is re-sorted into canonical order.

## Newlines and digest

Files are read with Python universal newlines, so CRLF (Windows `core.autocrlf`) and LF checkouts
yield identical text. Section bodies are kept verbatim except for leading/trailing blank lines. The
digest is SHA-256 over the UTF-8 bytes of `text` exactly as returned; it contains no timestamp,
absolute path or machine data. Editing projected content changes the digest; editing a non-projected
section (e.g. Open questions) does not.

## Git / versioning boundary

The builder does not call Git. A future run layer records the knowledge commit SHA and rejects a
dirty knowledge tree (proposal RAG-M6); the builder supplies `sha256`, `concept_ids` and
`concept_versions`.

## Future E3 compatibility

`concept_ids` accepts an explicit, caller-chosen subset (names such as `"PRICE_BUDGET"`). `None` = all
(E2). Empty, duplicated or unknown selections fail; `[]` never means "all". The builder never selects,
ranks or scores — any E3 selection logic lives outside it.

## Explicitly deferred

Selection/retrieval (lexical, semantic, hybrid), embeddings, vector DB, cache, prompt assembly (task
rules + call facts + knowledge + output requirements), LLM classifier, run/provenance record and Git
SHA capture, cross-check of `SRC_*` ids against `SOURCES.md`, token counting, eval harness E0–E4.

## Smoke test (real corpus, 2026-09-29)

8 units in canonical order; 19,693 characters; 20,497 UTF-8 bytes; 3,004 whitespace-separated words
(not LLM tokens — token count not measured); sha256
`3f458699c95e5689662c8e4c6687d04cbd3057bd9d89ef88105533cd044d95f6`.
