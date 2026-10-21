# Objection Guidance Engine v0 + Post-call Intelligence v0

Status: **v0.1 (grounding hardening), Value Sprint vertical slice.** It runs only on synthetic data, uses a local Ollama and
has no quality evaluation. It answers one question:
*given a call, what happened commercially, and what should the closer do next?*

## Flow

```
transcript .txt ─► Call (normalize_call)                              demo/analyze_call.py
Call ─► classify_call(E2) ─► EpisodePrediction[]                      objection_classifier (unchanged)
episode.category ─► ObjectionKnowledge.retrieve(category) ─► unit     objection_guidance
episode + unit ─► 1 LLM call (choose move id, phrase rationale/question) ─► CommercialGuidance
Call ─► 1 LLM call ─► lead end position, stakeholders, next steps     post_call
structure ─► deterministic rules ─► risks
PostCallIntelligence ─► JSON + Markdown
```

Per call: 1 classifier call, plus 1 call per episode that has knowledge, plus 1 extraction call. All
three go through the existing `ClassificationProvider` (prompt → JSON object).

## Knowledge (`docs/knowledge/sales/guidance/`)

There is one JSON unit per CIT-O1 category, plus `SOURCES.json`. The units are transcribed from
section 3 of [Gabriel's research](../research/AI_CLOSER_OBJECOES_DE_VENDAS_E_CONTORNOS_2026_10_14.md)
(sha256 recorded in `SOURCES.json`).

Each unit has these fields: `typical_phrases`, `recommended_moves[]`, `do_not[]` (required, never
empty), `evidence_source_ids` and `notes`. Each move or do-not item carries `id`, `code` (a v0.1
response code, or null), `guidance`, `evidence_grade`, `grade_note` and `source_ids`.

- **Grades:** `STRONG | MODERATE | WEAK | NOT_SUPPORTED_BY_CURRENT_SOURCES`.
  - A grade split as "MODERATE (mecanismo); WEAK (venda)" is stored as the **sales** grade (WEAK). The
    research text is kept in `grade_note`.
  - A do-not item with no grade in the research gets the playbooks' WEAK prior, and its note says so.
- **Why JSON and not the Markdown cards:** the classification KB's line-scanner contract does not
  model per-move grades. A sibling directory also leaves the E2 corpus and its digest unchanged.
- **Malformed knowledge fails loudly.** Any of these is an error:
  - unknown key, grade, code or source id;
  - a missing category;
  - an extra file;
  - an empty `do_not`;
  - a duplicate id.

## Guarantees

- **Retrieval v0** is an exact category lookup. `OTHER`, AMBIGUOUS and UNKNOWN episodes get no knowledge
  (`NO_KNOWLEDGE`), and the provider is not called for them.
- **Call evidence vs sales knowledge:**
  - they are separate prompt blocks (`CALL EVIDENCE` / `SALES KNOWLEDGE — NOT FROM THIS CALL`) and
    separate output fields;
  - every quote is copied from the Call by `segment_id`.
- **The model only chooses** a move id from the retrieved unit, and writes a rationale, a question and
  the supporting segment ids. Grade, sources and `avoid` are copied from the unit, so the model cannot
  upgrade a WEAK move or drop negative knowledge.
- **Three separate parts in the output** of `CommercialGuidance`:
  - CALL EVIDENCE: `objection_evidence`;
  - SALES KNOWLEDGE: `knowledge_unit_id`, `knowledge_move_id`, `recommended_move`, `avoid`,
    `knowledge_grade`, `knowledge_sources`;
  - MODEL-GENERATED GUIDANCE: `generated_guidance` (rationale, question, `generated_by`).
  The Markdown labels each part.
- **Grounding (v0.1, `ai/grounding.py`, fail closed).** `rationale` and `suggested_question` may not
  introduce anything that the CALL EVIDENCE shown to the model does not contain:
  - a date, weekday, month or deadline;
  - a number or amount;
  - a decision stakeholder (sócio, CFO, diretoria…);
  - a commercial condition (desconto, parcela, garantia…);
  - a proper name or acronym.

  A template placeholder (`[..]`, `{..}`, `<..>`, TODO, TBD) is always rejected. Sales knowledge is
  not a fact source, so a template's "30 dias" cannot become a promise to this lead. Generic phrasing
  ("uma data objetiva") passes.
- **Invalid answers are rejected, not repaired:**
  - an unknown move, a move from another category, ungrounded text, segment ids outside the episode,
    or extra keys → `INVALID_RESPONSE`, with errors;
  - an invalid classifier run → no objections, and the errors are listed.
- **Next steps are grounded in the segments they cite.** A violating step is rejected with an error:
  - `owner` lead/closer/both must have spoken them;
  - `action` must share a word with them and add no ungrounded fact;
  - `due_date` must appear verbatim and be a real date or deadline ("depois", "mais pra frente" →
    rejected; the model is told to use null).
- **`lead_end_position`** is one of: ACCEPTED, DECLINED, CONSIDERING, CONDITIONAL, DEFERRED,
  NO_PROPOSAL, UNKNOWN. UNKNOWN is valid when the call does not support a position.
  - v0 had ADVANCING / UNDECIDED / DECLINED / UNKNOWN, and the model answered UNKNOWN for all three
    demo calls, which ended conditional, considering and deferred.
  - Diagnosis: the schema had no value for those endings. It was not a prompt, parsing or provider
    problem.
- **Risks are rules over extracted facts:**
  - `OPEN_OBJECTION` (resolution ≠ resolved);
  - `NEXT_STEP_WITHOUT_DATE`;
  - `DECISION_STAKEHOLDER_ABSENT`;
  - `NO_CLEAR_NEXT_STEP`;
  - `LEAD_DECLINED`.
- **`pipeline_status`:** SUCCESS when no model output was rejected, otherwise INVALID (see
  `errors`).

## Demo

```bash
python -m closer_ai.demo.analyze_call examples/calls/authority_partner.txt   # one call
python -m closer_ai.demo.analyze_call examples/calls/ --continue-on-error   # batch, sequential
```

Writes `<name>.json`, `<name>.md` and `review_sheet.csv` to `artifacts/demo/` (gitignored), and a
SUCCESS / INVALID / ERROR summary.
- Input: a `<speaker>: <text>` file with synthetic timestamps. Speakers are `closer|lead|other`, or
  labels mapped with `--roles "Name=lead,..."`.
- Requires a local Ollama; the tests use a fake provider.
- Real calls: [`docs/product/REAL_CALL_PILOT.md`](../product/REAL_CALL_PILOT.md).

## Limits (v0.1)

- There is no quality evaluation of classification or guidance. "It runs" does not mean "it is
  right".
- Every move is a hypothesis: no move in the research has a measured success rate.
- **Grounding is lexical, not semantic.** It catches invented dates, numbers, amounts, listed
  stakeholder roles, listed commercial conditions and capitalized names. It does **not** catch an
  invented problem, product or claim written with common lowercase words, a stakeholder role outside
  the list, or a misreading of what the lead meant.
- **False rejections are possible.** Generated text is rejected (never repaired) when it mentions,
  for example, "segunda opção" (read as a weekday) or a role the call names with a different word.
  INVALID is the fail-closed outcome.
- **Fact base is narrow.** Guidance is grounded only in the episode's objection and context segments,
  so a fact said elsewhere in the call cannot be reused in the guidance.
- The `.txt` format is a demo input, not a source contract (no Zoom/Agro parser). Long real calls go
  through the same full-transcript classifier prompt (`num_ctx` 16384); a call longer than that
  context window is truncated by Ollama.
- Stakeholders and end position are not validated against gold; only ids, owners, actions and dates
  are checked deterministically.
- Gabriel's open decisions (#1–#7 in the research) are not implemented. One example: the rule for
  "vou pensar".
