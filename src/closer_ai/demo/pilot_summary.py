"""Product Validation Metrics from a completed pilot `review_sheet.csv`.

    python -m closer_ai.demo.pilot_summary <private_out_dir>/review_sheet.csv > <private_out_dir>/summary.md

Reads the human columns filled in by the reviewers and prints Markdown: usefulness (0/1/2), trust
(grounded), understanding (category, next step), failure modes (error taxonomy) and the free-text
feedback. These are product-validation numbers over a handful of calls: not a model benchmark, not
accuracy certification, not a Golden Set, not causal evidence.

Fail closed: any human cell with a value outside its allowed set is reported and no metrics are
printed, so a typo never becomes a silently dropped vote. Empty cells mean "not reviewed".
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

ERROR_CATEGORIES: tuple[str, ...] = (
    "WRONG_OBJECTION", "WRONG_MOVE", "GENERIC_GUIDANCE", "UNGROUNDED_GUIDANCE", "BAD_SUGGESTED_QUESTION",
    "MISSED_NEXT_STEP", "WRONG_NEXT_STEP", "WRONG_END_POSITION", "INSUFFICIENT_CONTEXT", "OTHER",
)
YES_NO_FIELDS = ("human_category_correct", "human_guidance_grounded", "human_next_step_correct")
_YES, _NO = {"yes", "y", "sim", "s"}, {"no", "n", "nao", "não"}


def _yes_no(value: str) -> bool | None:
    v = value.strip().lower()
    return True if v in _YES else False if v in _NO else None


def validate(rows: list[dict[str, str]]) -> list[str]:
    problems = []
    for i, r in enumerate(rows, start=2):  # line 1 is the header
        where = f"line {i} ({r.get('source_file', '?')})"
        for field in YES_NO_FIELDS:
            if r.get(field, "").strip() and _yes_no(r[field]) is None:
                problems.append(f"{where}: {field}={r[field]!r}, expected yes/no")
        useful = r.get("human_guidance_useful", "").strip()
        if useful and useful not in ("0", "1", "2"):
            problems.append(f"{where}: human_guidance_useful={useful!r}, expected 0, 1 or 2")
        for cat in filter(None, (c.strip().upper() for c in r.get("human_error_category", "").split(";"))):
            if cat not in ERROR_CATEGORIES:
                problems.append(f"{where}: human_error_category {cat!r} not in {ERROR_CATEGORIES}")
    return problems


def _rate(rows: list[dict[str, str]], field: str) -> str:
    votes = [_yes_no(r[field]) for r in rows if r.get(field, "").strip()]
    if not votes:
        return "n/a (not reviewed)"
    return f"{100 * sum(votes) / len(votes):.0f}% ({sum(votes)}/{len(votes)})"


def summarize(rows: list[dict[str, str]]) -> str:
    human = ("human_category_correct", "human_guidance_useful", *YES_NO_FIELDS[1:])
    reviewed = [r for r in rows if any(r.get(f, "").strip() for f in human)]
    status = Counter(r.get("pipeline_status", "") for r in rows)
    scores = [int(r["human_guidance_useful"]) for r in reviewed if r.get("human_guidance_useful", "").strip()]
    errors = Counter(c.strip().upper() for r in reviewed
                     for c in r.get("human_error_category", "").split(";") if c.strip())

    out = ["# Product Validation Metrics", "",
           ("_Pilot product validation over a handful of calls. Not a model benchmark, not accuracy "
            "certification, not a Golden Set, not causal evidence._"), "",
           f"- Calls in sheet: {len(rows)} ({', '.join(f'{k}={v}' for k, v in sorted(status.items()))})",
           f"- Calls reviewed: {len(reviewed)}", "",
           "## A. Usefulness: \"Depois de ler essa orientação, um closer saberia melhor o que fazer?\"", ""]
    if scores:
        out += [f"- score {s}: {100 * scores.count(s) / len(scores):.0f}% ({scores.count(s)}/{len(scores)})"
                for s in (2, 1, 0)]
        out.append(f"- average usefulness: {sum(scores) / len(scores):.2f} / 2")
    else:
        out.append("- n/a (not reviewed)")
    out += ["", "## B. Trust", "", f"- grounded rate: {_rate(reviewed, 'human_guidance_grounded')}",
            "", "## C. Understanding", "",
            f"- category accuracy: {_rate(reviewed, 'human_category_correct')}",
            f"- next-step accuracy: {_rate(reviewed, 'human_next_step_correct')}",
            "", "## D. Failure modes", ""]
    out += [f"- {cat}: {n}" for cat, n in errors.most_common()] or ["- none recorded"]

    def examples(score: int) -> list[str]:
        picked = [r for r in reviewed if r.get("human_guidance_useful", "").strip() == str(score)]
        return [f"- `{r['source_file']}`: {r.get('detected_category', '')} → {r.get('recommended_move', '')}"
                + (f" | better: {r['human_better_recommendation']}" if r.get("human_better_recommendation") else "")
                + (f" | notes: {r['human_notes']}" if r.get("human_notes") else "") for r in picked] or ["- none"]

    out += ["", "## E. Examples", "", "Scored 2 (useful and actionable):", *examples(2), "",
            "Scored 0 (useless or wrong):", *examples(0), "", "## Human feedback", ""]
    for field in ("human_better_recommendation", "human_notes"):
        texts = Counter(r[field].strip() for r in reviewed if r.get(field, "").strip())
        out += [f"{field}:", *([f"- ({n}x) {t}" for t, n in texts.most_common()] or ["- none"]), ""]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m closer_ai.demo.pilot_summary", description=__doc__.split("\n")[0])
    ap.add_argument("review_sheet", type=Path)
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles default to cp1252; keep accents
    with args.review_sheet.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    problems = validate(rows)
    if problems:
        print("review sheet has invalid human values; fix them, no metrics computed:", file=sys.stderr)
        print("\n".join(f"- {p}" for p in problems), file=sys.stderr)
        return 1
    print(summarize(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
