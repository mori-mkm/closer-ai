"""Evaluation harness for objection extraction v0.

Runs `RuleBasedObjectionExtractor` against the synthetic golden set in `golden_set.py` and
prints the metrics chosen in the Evaluator's design-phase report (see
docs/agents/tasks/objection-event-v0.md and evals/objection_v0/README.md for the rationale):

- schema validity: every emitted item is a real, already-validated `ObjectionEvent`.
- evidence grounding: every emitted event's segment_id resolves to a real segment on the
  source call, spoken by a role='lead' participant.
- detection precision/recall: emitted events vs. the golden set's expected events, compared
  by objection_id (itself a function of call_id + segment_id + category, so this is an exact
  identity comparison, not fuzzy matching).
- unsupported/extra-extraction rate: emitted events not present in the expected set (false
  positives), as a fraction of everything emitted — the operationalization of "hallucination"
  available at this stage, since there is no separate human-labeled corpus to judge against
  (see the design-phase report for why that's out of scope for v0).

Run: `python evals/objection_v0/run_eval.py`
"""
from __future__ import annotations

import sys

from golden_set import build_golden_set

from closer_ai.ai.objection_extraction import RuleBasedObjectionExtractor
from closer_ai.domain.objection import ObjectionEvent


def run() -> int:
    extractor = RuleBasedObjectionExtractor()
    golden_set = build_golden_set()

    total_expected = 0
    total_emitted = 0
    true_positives = 0
    schema_failures: list[str] = []
    grounding_failures: list[str] = []
    false_positives: list[str] = []
    false_negatives: list[str] = []

    for entry in golden_set:
        call = entry.call
        expected_ids = {e.objection_id for e in entry.expected}
        total_expected += len(expected_ids)

        events = extractor.extract(call)
        total_emitted += len(events)

        segment_by_id = {s.segment_id: s for s in call.segments}
        lead_ids = {p.id for p in call.participants if p.role == "lead"}

        emitted_ids: set[str] = set()
        for event in events:
            if not isinstance(event, ObjectionEvent):
                schema_failures.append(f"{entry.name}: non-ObjectionEvent output {event!r}")
                continue

            emitted_ids.add(event.objection_id)

            segment = segment_by_id.get(event.segment_id)
            if segment is None or segment.speaker_id not in lead_ids:
                grounding_failures.append(
                    f"{entry.name}: event {event.objection_id} "
                    f"segment_id={event.segment_id!r} does not resolve to a real lead segment"
                )

        true_positives += len(expected_ids & emitted_ids)
        false_negatives += [
            f"{entry.name}: missing expected objection_id={missing}"
            for missing in sorted(expected_ids - emitted_ids)
        ]
        false_positives += [
            f"{entry.name}: unexpected objection_id={extra}"
            for extra in sorted(emitted_ids - expected_ids)
        ]

    precision = true_positives / total_emitted if total_emitted else 1.0
    recall = true_positives / total_expected if total_expected else 1.0
    unsupported_rate = len(false_positives) / total_emitted if total_emitted else 0.0
    schema_validity = 1.0 - (len(schema_failures) / total_emitted) if total_emitted else 1.0
    grounding_rate = 1.0 - (len(grounding_failures) / total_emitted) if total_emitted else 1.0

    print(f"Golden set entries:   {len(golden_set)}")
    print(f"Expected objections:  {total_expected}   Emitted: {total_emitted}")
    print(f"Schema validity:      {schema_validity:.0%}  ({len(schema_failures)} failures)")
    print(f"Evidence grounding:   {grounding_rate:.0%}  ({len(grounding_failures)} failures)")
    print(f"Precision:            {precision:.0%}")
    print(f"Recall:               {recall:.0%}")
    print(
        f"Unsupported rate:     {unsupported_rate:.0%}  "
        f"({len(false_positives)} false positives)"
    )

    for label, items in (
        ("Missed objections (false negatives)", false_negatives),
        ("Unexpected objections (false positives)", false_positives),
        ("Grounding failures", grounding_failures),
        ("Schema failures", schema_failures),
    ):
        if items:
            print(f"\n{label}:")
            for line in items:
                print(f"  - {line}")

    ok = not (false_negatives or false_positives or grounding_failures or schema_failures)
    print(f"\nResult: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(run())
