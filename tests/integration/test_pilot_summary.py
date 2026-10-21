"""Product Validation Metrics from a (synthetic) completed review sheet."""
from __future__ import annotations

import csv

from closer_ai.demo import pilot_summary
from closer_ai.demo.analyze_call import REVIEW_COLUMNS


def _sheet(tmp_path, rows):
    path = tmp_path / "review_sheet.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=REVIEW_COLUMNS)
        writer.writeheader()
        for r in rows:
            writer.writerow({**dict.fromkeys(REVIEW_COLUMNS, ""), **r})
    return path


ROWS = [
    {"source_file": "a.txt", "detected_category": "PRICE_BUDGET", "recommended_move": "PRICE_BUDGET.M2",
     "pipeline_status": "SUCCESS", "human_category_correct": "yes", "human_guidance_useful": "2",
     "human_guidance_grounded": "yes", "human_next_step_correct": "yes", "human_notes": "pergunta boa"},
    {"source_file": "b.txt", "detected_category": "TIMING_PRIORITY", "recommended_move": "TIMING_PRIORITY.M3",
     "pipeline_status": "SUCCESS", "human_category_correct": "no", "human_guidance_useful": "0",
     "human_guidance_grounded": "yes", "human_next_step_correct": "no",
     "human_better_recommendation": "explorar o critério de decisão",
     "human_error_category": "WRONG_OBJECTION; MISSED_NEXT_STEP", "human_notes": "pergunta boa"},
    {"source_file": "c.txt", "detected_category": "AUTHORITY_INTERNAL_BUY_IN", "pipeline_status": "INVALID",
     "human_category_correct": "sim", "human_guidance_useful": "1", "human_guidance_grounded": "não",
     "human_error_category": "generic_guidance"},
    {"source_file": "d.txt", "pipeline_status": "INPUT_TOO_LARGE"},  # not reviewable, not reviewed
]


def test_metrics_from_a_completed_sheet(tmp_path, capsys):
    assert pilot_summary.main([str(_sheet(tmp_path, ROWS))]) == 0
    md = capsys.readouterr().out
    assert md.startswith("# Product Validation Metrics")
    assert "Not a model benchmark" in md
    assert "Calls reviewed: 3" in md and "INPUT_TOO_LARGE=1" in md
    assert "score 2: 33% (1/3)" in md and "score 0: 33% (1/3)" in md and "average usefulness: 1.00 / 2" in md
    assert "grounded rate: 67% (2/3)" in md
    assert "category accuracy: 67% (2/3)" in md
    assert "next-step accuracy: 50% (1/2)" in md  # c.txt left it empty: not counted
    assert "- WRONG_OBJECTION: 1" in md and "- GENERIC_GUIDANCE: 1" in md and "- MISSED_NEXT_STEP: 1" in md
    assert "`a.txt`: PRICE_BUDGET → PRICE_BUDGET.M2" in md
    assert "better: explorar o critério de decisão" in md
    assert "- (2x) pergunta boa" in md


def test_invalid_human_values_fail_closed(tmp_path, capsys):
    bad = [{"source_file": "a.txt", "human_guidance_useful": "3", "human_category_correct": "talvez",
            "human_error_category": "BAD_VIBES"}]
    assert pilot_summary.main([str(_sheet(tmp_path, bad))]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""  # no metrics at all
    assert "human_guidance_useful='3'" in captured.err and "'talvez'" in captured.err and "BAD_VIBES" in captured.err


def test_unreviewed_sheet_reports_not_reviewed(tmp_path, capsys):
    assert pilot_summary.main([str(_sheet(tmp_path, [{"source_file": "a.txt", "pipeline_status": "SUCCESS"}]))]) == 0
    md = capsys.readouterr().out
    assert "Calls reviewed: 0" in md and "n/a (not reviewed)" in md
