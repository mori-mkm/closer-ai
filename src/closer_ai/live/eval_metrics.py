"""Metrics, error patterns, inspectors and the Markdown report for `closer_ai.live.eval`.

Only what is annotated is scored, and a dimension nobody reviewed is reported UNLABELED, never as a
number. The call record's `scope` says how complete each dimension's labels are:
- **COMPLETE:** every lead line was reviewed, so an unlabeled detection is a false positive.
- **PARTIAL:** only the labeled lines count (recall, plus explicit negatives).
- **NONE:** not reviewed.

Matching rules (documented in evals/real_calls/README.md):
- **Objection:** a detection matches a label when its lines meet the label's `{sequence} ∪ accept_at`. A
  second detection of the same label is a duplicate, not a false positive. AMBIGUOUS lines are not scored.
- **Opportunity:** the same OP id, with trigger lines meeting the label's span. Extra instances are
  duplicates.
- **Fact:** the same type, lines meeting the span, and the label's words inside the value (folded), or the
  value's words inside the label.
"""
from __future__ import annotations

import json
import math
import re
import statistics
from pathlib import Path
from typing import Any

from closer_ai.live.commercial_state import fold

SCHEMA = Path(__file__).resolve().parents[3] / "evals" / "real_calls" / "annotation.schema.json"
FACT_TYPES = {"pain": "pain_points", "impact": "impacts", "stakeholder": "stakeholders",
              "decision_process": "decision_process", "buying_signal": "buying_signals",
              "commercial_term": "commercial_terms", "next_step": "next_steps"}
UNLABELED = "UNLABELED"


# --- annotations ------------------------------------------------------------------------------------

def _check(value: Any, schema: dict[str, Any], path: str) -> list[str]:
    """The subset of JSON Schema the annotation schema uses: type, enum, required, properties,
    additionalProperties (bool or schema), items, anyOf."""
    if "anyOf" in schema:
        return [] if any(not _check(value, s, path) for s in schema["anyOf"]) else [f"{path}: no anyOf branch matches"]
    if "enum" in schema:
        return [] if any(value == e and type(value) is type(e) for e in schema["enum"]) else [
            f"{path}: {value!r} not in {schema['enum']}"]
    kinds = {"string": str, "integer": int, "boolean": bool, "object": dict, "array": list}
    if (t := schema.get("type")) and (not isinstance(value, kinds[t]) or (t == "integer" and isinstance(value, bool))):
        return [f"{path}: expected {t}"]
    errors = []
    if isinstance(value, dict):
        props = schema.get("properties", {})
        errors += [f"{path}: missing {k}" for k in schema.get("required", []) if k not in value]
        extra = schema.get("additionalProperties", True)
        for k, v in value.items():
            if k in props:
                errors += _check(v, props[k], f"{path}.{k}")
            elif extra is False:
                errors.append(f"{path}: unknown field {k}")
            elif isinstance(extra, dict):
                errors += _check(v, extra, f"{path}.{k}")
    if isinstance(value, list) and "items" in schema:
        for i, v in enumerate(value):
            errors += _check(v, schema["items"], f"{path}[{i}]")
    return errors


def validate_annotation(record: dict[str, Any], schema: dict[str, Any] | None = None) -> list[str]:
    schema = schema or json.loads(SCHEMA.read_text(encoding="utf-8"))
    errors = _check(record, schema, "$")
    call_only = ("scope", "expected_rules")
    utt_only = ("expected_objection", "accept_at", "expected_opportunities", "expected_facts",
                "expected_seller_action", "seller_action_quality")
    if "sequence" in record:
        errors += [f"$: {k} belongs to the call record" for k in call_only if k in record]
    else:
        errors += [f"$: {k} needs a sequence" for k in utt_only if k in record]
    return errors


def load_annotations(inputs: list[Path], explicit: list[Path]) -> list[dict[str, Any]]:
    """Explicit files, plus *.annotations.jsonl inside input directories / next to input files; the kit
    .md uses the hand-encoded reference answers in evals/real_calls/fixtures. Invalid records raise."""
    from closer_ai.live.eval import FIXTURES, read_jsonl
    files = list(explicit)
    for p in inputs:
        if p.is_dir():
            files += sorted(p.rglob("*.annotations.jsonl"))
        elif p.suffix == ".jsonl":
            files.append(p.with_name(p.stem + ".annotations.jsonl"))
        elif p.name.startswith("SYNTHETIC_CASES"):
            files.append(FIXTURES / "calibration_kit_v0_1.annotations.jsonl")
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    out, seen = [], set()
    for f in dict.fromkeys(files):
        if not f.exists():
            continue
        for i, rec in enumerate(read_jsonl(f)):
            if errors := validate_annotation(rec, schema):
                raise ValueError(f"{f}:{i + 1}: " + "; ".join(errors))
            key = json.dumps(rec, sort_keys=True)
            if key not in seen:
                seen.add(key)
                out.append(rec)
    return out


def index(annotations: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    calls: dict[str, dict[str, Any]] = {}
    utts: dict[str, list[dict[str, Any]]] = {}
    for a in annotations:
        if "sequence" in a:
            utts.setdefault(a["meeting_id"], []).append(a)
        else:
            c = calls.setdefault(a["meeting_id"], {})
            for k, v in a.items():
                c[k] = {**c.get(k, {}), **v} if isinstance(v, dict) else v
    return calls, utts


def scope(calls: dict[str, dict[str, Any]], utts: dict[str, list[dict[str, Any]]], mid: str, dim: str,
          field: str) -> str:
    s = calls.get(mid, {}).get("scope", {}).get(dim)
    if s:
        return s
    return "PARTIAL" if any(field in u for u in utts.get(mid, [])) else "NONE"


# --- small helpers ----------------------------------------------------------------------------------

def stats(values: list[float]) -> dict[str, Any] | None:
    """n, median, p90, p95 (nearest rank), max. None when there is nothing to measure (never 0)."""
    v = sorted(x for x in values if x is not None)
    if not v:
        return None

    def pct(p: float) -> float:
        return v[min(len(v), max(1, math.ceil(p / 100 * len(v)))) - 1]

    return {"n": len(v), "median": round(statistics.median(v), 1), "p90": pct(90), "p95": pct(95), "max": v[-1]}


def ratio(a: int, b: int) -> float | None:
    return round(a / b, 3) if b else None


def _words(text: str) -> set[str]:
    return set(fold(text).split())


def _seqmap(trace: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    """meeting -> segment id (seg_n) -> sequence."""
    out: dict[str, dict[str, int]] = {}
    for e in trace:
        if e["kind"] == "utterance" and e.get("segment_id"):
            out.setdefault(e["meeting_id"], {})[e["segment_id"]] = e["sequence"]
    return out


def _span(label: dict[str, Any]) -> set[int]:
    return {label["sequence"], *label.get("accept_at", [])}


# --- dimensions -------------------------------------------------------------------------------------

def objection_metrics(calls, utts, trace, issues) -> dict[str, Any]:
    seqs = _seqmap(trace)
    tp = fp = fn = dup = amb = cat_ok = cat_scored = negatives = unlabeled = 0
    fp_by: dict[str, int] = {}
    fn_by: dict[str, int] = {}
    confusion: dict[str, int] = {}
    meetings = sorted({e["meeting_id"] for e in trace})
    for mid in meetings:
        sc = scope(calls, utts, mid, "objections", "expected_objection")
        labels = [u for u in utts.get(mid, []) if "expected_objection" in u]
        present = [u for u in labels if u["expected_objection"]["present"] is True]
        explicit_neg = {u["sequence"] for u in labels if u["expected_objection"]["present"] is False}
        ambiguous = {u["sequence"] for u in labels if u["expected_objection"]["present"] == "AMBIGUOUS"}
        covered = set().union(*(_span(u) for u in present)) if present else set()
        leads = [e for e in trace if e["meeting_id"] == mid and e["kind"] == "utterance" and e["role"] == "lead"]
        if sc == "COMPLETE":
            negatives += sum(e["sequence"] not in covered | ambiguous for e in leads)
        elif sc == "PARTIAL":
            negatives += len(explicit_neg)
        matched: set[int] = set()
        for e in trace:
            if e["meeting_id"] != mid or e["kind"] != "analysis" or not _detected(e):
                continue
            lines = {seqs.get(mid, {}).get(s) for s in e["timing"].get("target_segment_ids", [])} | {e["sequence"]}
            cat = e["timing"]["category"]
            hit = next((i for i, u in enumerate(present) if _span(u) & lines and i not in matched), None)
            again = next((i for i, u in enumerate(present) if _span(u) & lines), None)
            if hit is not None:
                matched.add(hit)
                tp += 1
                exp = present[hit]["expected_objection"]
                if exp.get("category", "UNKNOWN") != "UNKNOWN":
                    cat_scored += 1
                    ok = cat == exp["category"] or cat in exp.get("acceptable_categories", [])
                    cat_ok += ok
                    if not ok:
                        confusion[f"{exp['category']} -> {cat}"] = confusion.get(f"{exp['category']} -> {cat}", 0) + 1
                        issues.append(_issue(mid, "objection", "WRONG_CATEGORY", e["sequence"],
                                             expected=exp["category"], actual=cat))
            elif again is not None:
                dup += 1
            elif lines & ambiguous:
                amb += 1
            elif lines & explicit_neg or sc == "COMPLETE":
                fp += 1
                fp_by[cat] = fp_by.get(cat, 0) + 1
                issues.append(_issue(mid, "objection", "FP", e["sequence"], actual=cat,
                                     source=e["timing"].get("classification_source")))
            else:
                unlabeled += 1
        for i, u in enumerate(present):
            if i not in matched:
                fn += 1
                cat = u["expected_objection"].get("category", "UNKNOWN")
                fn_by[cat] = fn_by.get(cat, 0) + 1
                issues.append(_issue(mid, "objection", "FN", u["sequence"], expected=cat))
    labeled = tp + fn + negatives
    if not labeled:
        return {"status": UNLABELED, "unlabeled_detections": unlabeled}
    return {"status": "LABELED", "tp": tp, "fp": fp, "fn": fn, "duplicates": dup, "ambiguous_hits": amb,
            "labeled_negatives": negatives, "unlabeled_detections": unlabeled,
            "precision": ratio(tp, tp + fp), "recall": ratio(tp, tp + fn),
            "false_positive_rate": ratio(fp, negatives), "false_negative_rate": ratio(fn, tp + fn),
            "category_accuracy": ratio(cat_ok, cat_scored), "fp_by_category": fp_by, "fn_by_category": fn_by,
            "category_confusion": confusion}


def _detected(e: dict[str, Any]) -> bool:
    from closer_ai.live.eval import detected
    return detected(e["timing"])


def _issue(mid: str, dim: str, kind: str, seq: int | None, **detail: Any) -> dict[str, Any]:
    return {"meeting_id": mid, "dimension": dim, "kind": kind, "sequence": seq, **detail}


def opportunity_metrics(calls, utts, trace, sessions, issues) -> dict[str, Any]:
    seqs = _seqmap(trace)
    per_op: dict[str, dict[str, int]] = {}
    tot = {"tp": 0, "fp": 0, "fn": 0, "duplicates": 0, "resolution_ok": 0, "resolution_scored": 0, "unlabeled": 0}

    def bump(op: str, k: str) -> None:
        per_op.setdefault(op, {"tp": 0, "fp": 0, "fn": 0, "duplicates": 0})
        per_op[op][k] += 1
        tot[k] += 1

    for sess in sessions:
        mid = sess["meeting_id"]
        sc = scope(calls, utts, mid, "opportunities", "expected_opportunities")
        labels = [(item if isinstance(item, dict) else {"id": item}, u)
                  for u in utts.get(mid, []) for item in u.get("expected_opportunities", [])]
        matched: set[int] = set()
        for o in sess["final"]["opportunities"]:
            lines = {seqs.get(mid, {}).get(s) for s in o["trigger_segment_ids"]}
            hit = next((i for i, (lab, u) in enumerate(labels)
                        if lab["id"] == o["playbook_op_id"] and _span(u) & lines and i not in matched), None)
            again = any(lab["id"] == o["playbook_op_id"] and _span(u) & lines for lab, u in labels)
            if hit is not None:
                matched.add(hit)
                bump(o["playbook_op_id"], "tp")
                want = labels[hit][0].get("final_status")
                if want:
                    tot["resolution_scored"] += 1
                    tot["resolution_ok"] += o["status"] == want
                    if o["status"] != want:
                        issues.append(_issue(mid, "opportunity", "WRONG_RESOLUTION", labels[hit][1]["sequence"],
                                             expected=f"{o['playbook_op_id']} {want}", actual=o["status"]))
            elif again:
                bump(o["playbook_op_id"], "duplicates")
            elif sc == "COMPLETE":
                bump(o["playbook_op_id"], "fp")
                issues.append(_issue(mid, "opportunity", "FP", min((x for x in lines if x), default=None),
                                     actual=o["playbook_op_id"], status=o["status"]))
            else:
                tot["unlabeled"] += 1
        for i, (lab, u) in enumerate(labels):
            if i not in matched:
                bump(lab["id"], "fn")
                issues.append(_issue(mid, "opportunity", "FN", u["sequence"], expected=lab["id"]))
    if not (tot["tp"] + tot["fn"] + any(scope(calls, utts, s["meeting_id"], "opportunities", "expected_opportunities")
                                        == "COMPLETE" for s in sessions)):
        return {"status": UNLABELED, "unlabeled_opportunities": tot["unlabeled"]}
    return {"status": "LABELED", **{k: v for k, v in tot.items() if k not in ("resolution_ok", "resolution_scored")},
            "precision": ratio(tot["tp"], tot["tp"] + tot["fp"]), "recall": ratio(tot["tp"], tot["tp"] + tot["fn"]),
            "false_opportunities": tot["fp"], "missed_opportunities": tot["fn"],
            "resolution_accuracy": ratio(tot["resolution_ok"], tot["resolution_scored"]),
            "by_op": {op: {**v, "precision": ratio(v["tp"], v["tp"] + v["fp"]),
                           "recall": ratio(v["tp"], v["tp"] + v["fn"])} for op, v in sorted(per_op.items())}}


def fact_metrics(calls, utts, trace, sessions, issues) -> dict[str, Any]:
    seqs = _seqmap(trace)
    by: dict[str, dict[str, int]] = {t: {"labels": 0, "found": 0, "predicted": 0, "correct": 0} for t in FACT_TYPES}
    any_label = False
    for sess in sessions:
        mid = sess["meeting_id"]
        sc = scope(calls, utts, mid, "facts", "expected_facts")
        labels = [(f, u) for u in utts.get(mid, []) for f in u.get("expected_facts", [])]
        any_label |= bool(labels) or sc == "COMPLETE"
        facts = sess["final"]["facts"]

        def match(lab: dict[str, Any], u: dict[str, Any], f: dict[str, Any], mid: str = mid) -> bool:
            lw, fw = _words(lab["value"]), _words(f["value"])
            lines = {seqs.get(mid, {}).get(s) for s in f["segment_ids"]}
            return bool(lines & _span(u)) and bool(lw) and (lw <= fw or fw <= lw)

        for lab, u in labels:
            by[lab["type"]]["labels"] += 1
            if any(match(lab, u, f) for f in facts.get(FACT_TYPES[lab["type"]], [])):
                by[lab["type"]]["found"] += 1
            else:
                issues.append(_issue(mid, "fact", "FN", u["sequence"], expected=f"{lab['type']}: {lab['value']}",
                                     actual=_fact_types_at(facts, seqs.get(mid, {}), _span(u))))
        if sc == "COMPLETE":
            for t, field in FACT_TYPES.items():
                for f in facts.get(field, []):
                    by[t]["predicted"] += 1
                    ok = any(lab["type"] == t and match(lab, u, f) for lab, u in labels)
                    by[t]["correct"] += ok
                    if not ok:
                        issues.append(_issue(mid, "fact", "FP", None, actual=f"{t}: {f['value']}"))
    if not any_label:
        return {"status": UNLABELED}
    return {"status": "LABELED", "by_type": {t: {**v, "recall": ratio(v["found"], v["labels"]),
                                                 "precision": ratio(v["correct"], v["predicted"])}
                                             for t, v in by.items() if v["labels"] or v["predicted"]},
            "recall": ratio(sum(v["found"] for v in by.values()), sum(v["labels"] for v in by.values())),
            "precision": ratio(sum(v["correct"] for v in by.values()), sum(v["predicted"] for v in by.values()))}


def _fact_types_at(facts: dict[str, list[dict[str, Any]]], seqs: dict[str, int], span: set[int]) -> list[str]:
    return [f"{k}: {f['value']}" for k, v in facts.items() for f in v
            if {seqs.get(s) for s in f["segment_ids"]} & span]


def compliance_metrics(calls, sessions, issues) -> dict[str, Any]:
    from closer_ai.live.playbook import load_playbook
    total_rules = len(load_playbook().rules)
    evaluated = sorted({r for s in sessions for r in s["final"]["rules"]})
    matrix: dict[str, dict[str, int]] = {}
    for sess in sessions:
        want = calls.get(sess["meeting_id"], {}).get("expected_rules", {})
        for rule, exp in want.items():
            got = sess["final"]["rules"].get(rule, "NOT_EVALUATED")
            row = matrix.setdefault(exp, {})
            row[got] = row.get(got, 0) + 1
            if got != exp:
                issues.append(_issue(sess["meeting_id"], "compliance", "WRONG_STATUS", None, rule=rule,
                                     expected=exp, actual=got))
    coverage = {"rules_in_playbook": total_rules, "rules_evaluated": len(evaluated),
                "evaluated_share": ratio(len(evaluated), total_rules),
                "rules_annotated": len({r for c in calls.values() for r in c.get("expected_rules", {})})}
    if not matrix:
        return {"status": UNLABELED, "coverage": coverage}
    return {"status": "LABELED", "coverage": coverage, "confusion": matrix,
            "correct_by_status": {exp: {"correct": row.get(exp, 0), "total": sum(row.values()),
                                        "accuracy": ratio(row.get(exp, 0), sum(row.values()))}
                                  for exp, row in matrix.items()},
            "accuracy": ratio(sum(r.get(e, 0) for e, r in matrix.items()), sum(sum(r.values()) for r in matrix.values()))}


def _card_key(e: dict[str, Any]) -> str | None:
    sa = e["seller_action"]
    if not sa:
        return None
    return f"OBJECTION:{(e.get('recommendation') or {}).get('category')}" if sa["source"] == "OBJECTION" \
        else sa["source_id"].split(":")[0]


def _episodes_of_cards(trace, utts, mid: str) -> dict[str, int | None]:
    """rec:<id> -> the labeled objection episode its analysis lines fall in (index), or None."""
    seqs = _seqmap(trace).get(mid, {})
    present = [u for u in utts.get(mid, []) if (u.get("expected_objection") or {}).get("present") is True]
    out: dict[str, int | None] = {}
    for e in trace:
        if e["meeting_id"] == mid and e["kind"] == "analysis" and e["timing"].get("recommendation_id") is not None:
            lines = {e["sequence"], *(seqs.get(s) for s in e["timing"].get("target_segment_ids", []))}
            out[f"rec:{e['timing']['recommendation_id']}"] = next(
                (i for i, u in enumerate(present) if _span(u) & lines), None)
    return out


def seller_metrics(calls, utts, trace, issues, ttl: float = 90.0) -> dict[str, Any]:
    stale = repeat = 0
    for mid in sorted({e["meeting_id"] for e in trace}):
        evs = [e for e in trace if e["meeting_id"] == mid]
        episode = _episodes_of_cards(trace, utts, mid)
        displaced: set[str] = set()
        seen: dict[str, tuple[str, float]] = {}  # key -> (source_id, visible_at) of the last card with that key
        last = None
        for e in evs:
            sa = e["seller_action"]
            if last and last["source"] == "OBJECTION" and sa and sa["source"] == "OPPORTUNITY":
                displaced.add(last["source_id"])
            if sa and (not last or last["source_id"] != sa["source_id"]):
                if sa["source_id"] in displaced:
                    stale += 1
                    issues.append(_issue(mid, "seller_action", "STALE_CARD", e.get("sequence"), actual=sa["source_id"]))
                key = _card_key(e)
                prev = seen.get(key)
                # two labeled objection episodes of the same category are two cards, not a duplicate
                distinct = (sa["source"] == "OBJECTION" and episode.get(prev[0]) is not None
                            and episode.get(sa["source_id"]) is not None
                            and episode[prev[0]] != episode[sa["source_id"]]) if prev else False
                if prev and prev[0] != sa["source_id"] and e["visible_at"] - prev[1] < ttl and not distinct:
                    repeat += 1
                    issues.append(_issue(mid, "seller_action", "DUPLICATE_CARD", e.get("sequence"), actual=key))
                seen[key] = (sa["source_id"], e["visible_at"])
            last = sa
    labeled = [(u, mid) for mid, us in utts.items() for u in us if "expected_seller_action" in u]
    out: dict[str, Any] = {"stale_card": stale, "duplicate_card": repeat}
    quality: dict[str, int] = {}
    for us in utts.values():
        for u in us:
            if "seller_action_quality" in u:
                quality[u["seller_action_quality"]] = quality.get(u["seller_action_quality"], 0) + 1
    out["quality_labels"] = quality or UNLABELED
    if not labeled:
        return {"status": UNLABELED, **out}
    src_ok = prio_ok = prio_n = needed = available = 0
    for u, mid in labeled:
        e = card_before_next(trace, mid, u["sequence"])
        exp = u["expected_seller_action"]
        got = (e or {}).get("seller_action")
        got_src = got["source"] if got else "NONE"
        src_ok += got_src == exp["source"]
        if exp["source"] != "NONE":
            needed += 1
            available += got is not None
        if exp.get("id"):
            prio_n += 1
            ok = got is not None and exp["id"] in (got["source_id"].split(":")[0],
                                                   ((e or {}).get("recommendation") or {}).get("category"))
            prio_ok += ok
        else:
            ok = True
        if got_src != exp["source"] or not ok:
            issues.append(_issue(mid, "seller_action", "WRONG_CARD", u["sequence"],
                                 expected=f"{exp['source']} {exp.get('id', '')}".strip(),
                                 actual=f"{got_src} {got['source_id'] if got else ''}".strip()))
    return {"status": "LABELED", **out, "labeled_moments": len(labeled),
            "correct_source": ratio(src_ok, len(labeled)), "correct_priority": ratio(prio_ok, prio_n),
            "action_available_when_needed": ratio(available, needed)}


def card_before_next(trace: list[dict[str, Any]], mid: str, seq: int) -> dict[str, Any] | None:
    """The last event of this meeting before the utterance after `seq` arrived: what was on screen then."""
    evs = [e for e in trace if e["meeting_id"] == mid]
    start = next((i for i, e in enumerate(evs) if e["kind"] == "utterance" and e["sequence"] == seq), None)
    if start is None:
        return None
    end = next((i for i in range(start + 1, len(evs)) if evs[i]["kind"] == "utterance"), len(evs))
    return evs[end - 1]


def latency_metrics(trace, sessions) -> dict[str, Any]:
    """Utterance received -> seller action available, by path. A line with no recommendation is its own
    path ("time to decide nothing"), never a 0 ms latency."""
    paths: dict[str, list[float]] = {"FAST_PATH": [], "LLM_CLASSIFIER": []}
    stages: dict[str, dict[str, list[float]]] = {p: {"classifier_ms": [], "guidance_ms": []} for p in paths}
    none = []
    for e in trace:
        if e["kind"] != "utterance" or e["objection"]["analyzed"] != "ANALYZED":
            continue
        path = "FAST_PATH" if e["objection"]["source"] == "deterministic_fast_path" else "LLM_CLASSIFIER"
        if e["objection"]["recommendation"]:
            paths[path].append(e["timings"]["displayed_ms"])
            for k in ("classifier_ms", "guidance_ms"):
                stages[path][k].append(e["timings"][k])
    for e in trace:
        if e["kind"] == "analysis" and e["timing"].get("recommendation_id") is None:
            none.append(e["timing"].get("end_to_end_latency_ms"))
    op_only = []
    for sess in sessions:
        mid = sess["meeting_id"]
        evs = [e for e in trace if e["meeting_id"] == mid]
        t_by_sid = {e["segment_id"]: e["t"] for e in evs if e["kind"] == "utterance" and e.get("segment_id")}
        trig = {o["id"]: o["trigger_segment_ids"][0] for o in sess["final"]["opportunities"] if o["trigger_segment_ids"]}
        first: dict[str, float] = {}
        for e in evs:
            sa = e["seller_action"]
            if sa and sa["source"] == "OPPORTUNITY" and sa["source_id"] not in first:
                first[sa["source_id"]] = e["visible_at"]
        for oid, at in first.items():
            if oid in trig and trig[oid] in t_by_sid:
                op_only.append(round((at - t_by_sid[trig[oid]]) * 1000))
    return {"FAST_PATH": stats(paths["FAST_PATH"]), "LLM_CLASSIFIER": stats(paths["LLM_CLASSIFIER"]),
            "NO_RECOMMENDATION": stats(none), "OPPORTUNITY_ONLY": stats(op_only),
            "stages": {p: {k: stats(v) for k, v in s.items()} for p, s in stages.items()},
            "note": "displayed = caption received -> card ready (virtual time, the dock's <=0.5 s poll excluded); "
                    "OPPORTUNITY_ONLY = trigger line received -> first shown as the card; NO_RECOMMENDATION = time "
                    "to decide nothing (never mixed with the others)"}


# --- error patterns + inspectors --------------------------------------------------------------------

_NEG = re.compile(r"\b(?:nao|nem|nunca)\b")
_PRICE = re.compile(r"\b(?:caro|cara|caros|preco|valor|orcamento|investimento)\b")
_ASKED = re.compile(r"\?|^(?:e |mas |entao )?(?:quem|qual|quais|quando|quanto|como|o que|onde|por que)\b")


def pattern(issue: dict[str, Any], ctx: dict[str, Any]) -> str:
    """Heuristic error pattern (a starting point for review, not ground truth)."""
    from closer_ai.live import signals as sig
    dim, kind = issue["dimension"], issue["kind"]
    text, prev = fold(ctx.get("text", "")), ctx.get("previous", [])
    if dim == "objection" and kind == "FP":
        if _NEG.search(text) and (_PRICE.search(text) or issue.get("actual") == "PRICE_BUDGET"):
            return "NEGATION"
        if any(sig.LEAD[k].search(text) for k in ("OWNER_DEPENDENCY", "FINANCIAL_BLINDNESS", "CASH_TIGHT")) \
                or any(f.startswith("pain_points") for f in ctx.get("facts", [])):
            return "PAIN_AS_OBJECTION"
        asked = prev and prev[-1]["role"] == "closer" and (
            "?" in prev[-1]["text"] or _ASKED.search(fold(prev[-1]["text"])))
        if asked and len(text.split()) <= 8:
            return "DISCOVERY_AS_OBJECTION"
        if issue.get("actual") in ctx.get("earlier_categories", []):
            return "CONTEXT_LEAK"
        return "OTHER_FALSE_OBJECTION"
    if dim == "objection" and kind == "FN":
        if ctx.get("analyzed") == "COALESCED":  # read in a later batch (the model or a gate missed it) or never
            return "MODEL_FN_IN_BATCH" if ctx.get("covered_by") else "PIPELINE_COALESCED"
        if ctx.get("analyzed") == "LEAD_UTTERANCE_TOO_SHORT":
            return "TOO_SHORT"
        if issue.get("expected") == "AUTHORITY_INTERNAL_BUY_IN":
            return "MISSED_DECISION_DEPENDENCY"
        return "MISSED_OBJECTION"
    if dim == "objection":
        return "WRONG_CATEGORY"
    if dim == "opportunity" and kind == "FN":
        return {"OP-14": "MISSED_BUYING_SIGNAL", "OP-03": "MISSED_DECISION_DEPENDENCY"}.get(
            issue.get("expected"), "MISSED_OPPORTUNITY")
    if dim == "opportunity":
        return "FALSE_OPPORTUNITY" if kind == "FP" else "WRONG_RESOLUTION"
    if dim == "fact" and kind == "FN":
        return "MISSED_BUYING_SIGNAL" if str(issue.get("expected", "")).startswith("buying_signal") \
            else f"MISSED_FACT:{str(issue.get('expected', '')).split(':')[0]}"
    if dim == "fact":
        return "FALSE_FACT"
    if dim == "seller_action" and kind == "WRONG_CARD" and str(
            (ctx.get("objection") or {}).get("reason") or "").startswith("GUIDANCE_"):
        return "GUIDANCE_FAILED"  # the objection was detected; its guidance failed closed, so no card
    if dim == "seller_action":
        return {"STALE_CARD": "STALE_OBJECTION", "DUPLICATE_CARD": "DUPLICATE_CARD"}.get(kind, "WRONG_CARD")
    return "WRONG_RULE_STATUS"


def context(trace: list[dict[str, Any]], mid: str, seq: int | None, n: int = 5) -> dict[str, Any]:
    """Text, the previous n utterances, and the copilot state when that line's analysis finished."""
    utt = [e for e in trace if e["meeting_id"] == mid and e["kind"] == "utterance"]
    i = next((k for k, e in enumerate(utt) if e["sequence"] == seq), None)
    if i is None:
        return {}
    evs = [e for e in trace if e["meeting_id"] == mid]
    upto = next((k for k, e in enumerate(evs) if e["kind"] == "analysis" and e["sequence"] == seq),
                next(k for k, e in enumerate(evs) if e["kind"] == "utterance" and e["sequence"] == seq))
    facts, ops = [], {}
    for e in evs[:upto + 1]:
        facts += e["commercial_state_delta"]
        ops.update(dict.fromkeys(e["opportunities_created"], "ACTIVE"))
        ops.update(dict.fromkeys(e["opportunities_resolved"], "RESOLVED"))
    earlier = [e["objection"]["category"] for e in utt[:i] if e["objection"]["detected"]]
    # a coalesced line still reaches the next analysis as one of its targets (latest-wins keeps every new lead
    # line): which analysis read it, if any
    sid = utt[i].get("segment_id")
    covered = next(({"sequence": e["sequence"], "category": e["timing"].get("category"),
                     "reason": e["timing"].get("reason")} for e in evs
                    if e["kind"] == "analysis" and sid in e["timing"].get("target_segment_ids", [])), None)
    return {"text": utt[i]["text"], "role": utt[i]["role"], "analyzed": utt[i]["objection"]["analyzed"],
            "covered_by": covered,
            "previous": [{"sequence": e["sequence"], "role": e["role"], "text": e["text"]} for e in utt[max(0, i - n):i]],
            "objection": utt[i]["objection"], "facts": facts, "opportunities": ops,
            "earlier_categories": earlier, "seller_action": evs[upto]["seller_action"]}


# --- all together -----------------------------------------------------------------------------------

def compute(calls_in: dict[str, list[dict[str, Any]]], annotations: list[dict[str, Any]],
            trace: list[dict[str, Any]], sessions: list[dict[str, Any]]) -> dict[str, Any]:
    calls, utts = index(annotations)
    issues: list[dict[str, Any]] = []
    m: dict[str, Any] = {
        "objections": objection_metrics(calls, utts, trace, issues),
        "opportunities": opportunity_metrics(calls, utts, trace, sessions, issues),
        "commercial_state": fact_metrics(calls, utts, trace, sessions, issues),
        "compliance": compliance_metrics(calls, sessions, issues),
        "seller_action": seller_metrics(calls, utts, trace, issues),
        "latency": latency_metrics(trace, sessions)}
    for it in issues:
        ctx = context(trace, it["meeting_id"], it["sequence"]) if it["sequence"] is not None else {}
        it["pattern"] = pattern(it, ctx)
        it["_ctx"] = ctx
    known = {mid: next((u["known_failure"] for u in utts.get(mid, []) if u.get("known_failure")),
                       calls.get(mid, {}).get("known_failure")) for mid in calls_in}
    regress = []
    for mid in sorted(calls_in):
        if calls.get(mid, {}).get("source") != "synthetic_fixture":
            continue
        errs = [f"{i['dimension']} {i['kind']} @{i['sequence']}: {i.get('expected', '')} -> {i.get('actual', '')}"
                for i in issues if i["meeting_id"] == mid]
        kf = known[mid]
        status = ("KNOWN_FAILURE" if errs else "UNEXPECTED_PASS") if kf else ("FAIL" if errs else "PASS")
        regress.append({"case": mid, "status": status, "known_failure": kf, "errors": errs})
    m["known_regressions"] = regress
    counts: dict[str, int] = {}
    for it in issues:
        counts[it["pattern"]] = counts.get(it["pattern"], 0) + 1
    m["confusion_report"] = dict(sorted(counts.items(), key=lambda x: -x[1]))
    labeled = {mid for mid in calls_in if mid in calls or mid in utts}
    m["summary"] = {
        "calls": len(calls_in), "labeled_calls": len(labeled), "unlabeled_calls": sorted(set(calls_in) - labeled),
        "utterances": sum(len(r) for r in calls_in.values()),
        "objections": {k: m["objections"].get(k) for k in ("status", "precision", "recall", "false_positive_rate",
                                                           "category_accuracy")},
        "opportunities": {k: m["opportunities"].get(k) for k in ("status", "precision", "recall")},
        "commercial_state": {k: m["commercial_state"].get(k) for k in ("status", "precision", "recall")},
        "compliance": {k: m["compliance"].get(k) for k in ("status", "accuracy")},
        "seller_action": {k: m["seller_action"].get(k) for k in ("status", "correct_source", "stale_card",
                                                                 "duplicate_card")},
        "known_regressions": {s: sum(r["status"] == s for r in regress)
                              for s in ("PASS", "FAIL", "KNOWN_FAILURE", "UNEXPECTED_PASS")},
        "issues": len(issues)}
    fps = [i for i in issues if i["kind"] == "FP"]
    fns = [i for i in issues if i["kind"] in ("FN", "WRONG_CATEGORY", "WRONG_RESOLUTION", "WRONG_CARD")]
    m["_false_positives"] = [_inspect(i) for i in fps]
    m["_false_negatives"] = [_inspect(i) for i in fns]
    m["issues"] = [{k: v for k, v in i.items() if k != "_ctx"} for i in issues]
    return m


def _inspect(it: dict[str, Any]) -> dict[str, Any]:
    ctx = it["_ctx"]
    return {"meeting_id": it["meeting_id"], "sequence": it["sequence"], "dimension": it["dimension"],
            "kind": it["kind"], "pattern": it["pattern"], "expected": it.get("expected"), "actual": it.get("actual"),
            "text": ctx.get("text"), "previous": ctx.get("previous", []),
            "classifier_source": (ctx.get("objection") or {}).get("source"),
            "engine": ctx.get("objection"), "commercial_state": ctx.get("facts", []),
            "opportunities": ctx.get("opportunities", {}), "seller_action": ctx.get("seller_action")}


def review_template(trace: list[dict[str, Any]], labeled: set[str]) -> list[dict[str, Any]]:
    """Annotation stubs for UNLABELED calls: one call record + one record per line where the copilot did
    something (to confirm or correct). Nothing is pre-filled as truth: every expectation is left out."""
    out = []
    for mid in sorted({e["meeting_id"] for e in trace} - labeled):
        out.append({"meeting_id": mid, "source": "human", "scope": {"objections": "NONE", "opportunities": "NONE",
                                                                    "facts": "NONE", "seller_action": "NONE"},
                    "notes": "set each scope to COMPLETE/PARTIAL once reviewed"})
        for e in trace:
            if e["meeting_id"] == mid and e["kind"] == "utterance" and (
                    e["objection"]["detected"] or e["opportunities_created"]):
                out.append({"meeting_id": mid, "sequence": e["sequence"],
                            "notes": f"copilot: objection={e['objection']['category']} "
                                     f"opportunities={e['opportunities_created']} :: {e['text'][:80]}"})
    return out


# --- report -----------------------------------------------------------------------------------------

def _fmt(v: Any) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.3f}"
    return str(v)


def _lat(s: dict[str, Any] | None) -> str:
    return "n=0" if not s else f"n={s['n']} · mediana {s['median']} · p90 {s['p90']} · p95 {s['p95']} · max {s['max']}"


def report(meta: dict[str, Any], m: dict[str, Any], sessions: list[dict[str, Any]], out: Path | None = None) -> str:
    sm, o, op, f, c, sa, lat = (m["summary"], m["objections"], m["opportunities"], m["commercial_state"],
                                m["compliance"], m["seller_action"], m["latency"])
    L = [f"# Eval report — {meta['label']}", "",
         (f"- run: {meta.get('created_at')} · git `{meta.get('git_sha')}` · model `{meta.get('model')}` · fast path "
         f"{meta.get('fast_path')} · commercial facts {meta.get('commercial_facts')}"),
         f"- calls: {sm['calls']} ({sm['labeled_calls']} labeled) · utterances: {sm['utterances']}",
         "- Only labeled dimensions are scored; UNLABELED means nobody reviewed it (never a number).", "",
         "## Summary", "", "| Dimension | Status | Precision | Recall | Other |", "|---|---|---|---|---|",
         (f"| Objections | {o['status']} | {_fmt(o.get('precision'))} | {_fmt(o.get('recall'))} | FPR "
         f"{_fmt(o.get('false_positive_rate'))} · category acc {_fmt(o.get('category_accuracy'))} |"),
         (f"| Opportunities | {op['status']} | {_fmt(op.get('precision'))} | {_fmt(op.get('recall'))} | "
         f"resolution acc {_fmt(op.get('resolution_accuracy'))} · duplicates {_fmt(op.get('duplicates'))} |"),
         f"| Commercial State | {f['status']} | {_fmt(f.get('precision'))} | {_fmt(f.get('recall'))} | |",
         (f"| Compliance | {c['status']} | | | accuracy {_fmt(c.get('accuracy'))} · evaluated "
         f"{c['coverage']['rules_evaluated']}/{c['coverage']['rules_in_playbook']} rules |"),
         (f"| Seller action | {sa['status']} | | | correct source {_fmt(sa.get('correct_source'))} · stale "
         f"{sa['stale_card']} · duplicate {sa['duplicate_card']} |"), ""]
    L += ["## Objections", ""]
    if o["status"] == UNLABELED:
        L += [f"UNLABELED ({o.get('unlabeled_detections', 0)} detections in unlabeled calls).", ""]
    else:
        L += [(f"TP {o['tp']} · FP {o['fp']} · FN {o['fn']} · duplicates {o['duplicates']} · ambiguous hits "
              f"{o['ambiguous_hits']} · labeled negatives {o['labeled_negatives']} · unlabeled detections "
              f"{o['unlabeled_detections']}"),
              f"- FP by category: {o['fp_by_category'] or '—'}", f"- FN by category: {o['fn_by_category'] or '—'}",
              f"- category confusion (expected -> predicted): {o['category_confusion'] or '—'}", ""]
    L += ["## Opportunities", ""]
    if op["status"] == UNLABELED:
        L += ["UNLABELED.", ""]
    else:
        L += ["| OP | TP | FP | FN | dup | precision | recall |", "|---|---|---|---|---|---|---|"]
        L += [f"| {k} | {v['tp']} | {v['fp']} | {v['fn']} | {v['duplicates']} | {_fmt(v['precision'])} | "
              f"{_fmt(v['recall'])} |" for k, v in op["by_op"].items()] + [""]
    L += ["## Commercial State", ""]
    if f["status"] == UNLABELED:
        L += ["UNLABELED.", ""]
    else:
        L += ["| type | labels | found | recall | predicted | precision |", "|---|---|---|---|---|---|"]
        L += [f"| {k} | {v['labels']} | {v['found']} | {_fmt(v['recall'])} | {v['predicted']} | "
              f"{_fmt(v['precision'])} |" for k, v in f["by_type"].items()] + [""]
    L += ["## Compliance", "", f"Coverage: {c['coverage']}", ""]
    if c["status"] != UNLABELED:
        L += [f"- {exp}: {v['correct']}/{v['total']} correct" for exp, v in c["correct_by_status"].items()]
        L += [f"- confusion: {c['confusion']}", ""]
    else:
        L += ["UNLABELED.", ""]
    L += ["## Seller Actions", "", (f"- stale cards: {sa['stale_card']} · duplicate cards: {sa['duplicate_card']} · "
          f"quality labels: {sa['quality_labels']}")]
    if sa["status"] != UNLABELED:
        L += [(f"- correct source {_fmt(sa['correct_source'])} · correct priority {_fmt(sa['correct_priority'])} · "
              f"action available when needed {_fmt(sa['action_available_when_needed'])} "
              f"({sa['labeled_moments']} labeled moments)")]
    L += ["", "## Latency (ms, utterance received -> seller action available)", ""]
    L += [f"- **{p}:** {_lat(lat[p])}" for p in ("FAST_PATH", "LLM_CLASSIFIER", "OPPORTUNITY_ONLY", "NO_RECOMMENDATION")]
    L += [f"- {p} stages: classifier {_lat(s['classifier_ms'])}; guidance {_lat(s['guidance_ms'])}"
          for p, s in lat["stages"].items()]
    L += [f"- {lat['note']}", "", "## Error patterns", ""]
    L += [f"- {k}: {v}" for k, v in m["confusion_report"].items()] or ["- none"]
    L += ["", "## Top False Positives", ""]
    fps = [i for i in m["issues"] if i["kind"] == "FP"][:10]
    L += [f"- `{i['meeting_id']}` @{i['sequence']} {i['dimension']} {i.get('actual')} [{i['pattern']}]" for i in fps] \
        or ["- none"]
    L += ["", "## Top False Negatives", ""]
    fns = [i for i in m["issues"] if i["kind"] != "FP"][:10]
    L += [f"- `{i['meeting_id']}` @{i['sequence']} {i['dimension']} {i['kind']}: {i.get('expected')} -> "
          f"{i.get('actual')} [{i['pattern']}]" for i in fns] or ["- none"]
    L += ["", "## Known Failures (regression suite)", "", "| case | status | known failure | errors |", "|---|---|---|---|"]
    L += [f"| {r['case']} | {r['status']} | {r['known_failure'] or ''} | {'; '.join(r['errors']) or ''} |"
          for r in m["known_regressions"]] or ["| — | | | |"]
    L += ["", "## Sessions", "", ("| call | dur s | utt | lead | obj | rec | OPs | resolved | not seized | req ok | "
          "req pending | cards |"), "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    L += [f"| {s['meeting_id']} | {s['call_duration_s']} | {s['utterances']} | {s['lead_utterances']} | "
          f"{s['objections_detected']} | {s['recommendations_created']} | {s['opportunities_detected']} | "
          f"{s['opportunities_resolved']} | {','.join(s['opportunities_missed']) or '—'} | "
          f"{s['required_compliance_satisfied']} | {s['required_compliance_pending']} | {s['seller_actions_shown']} |"
          for s in sessions]
    if sm["unlabeled_calls"]:
        L += ["", f"UNLABELED calls: {', '.join(sm['unlabeled_calls'])} (stubs in review_template.annotations.jsonl)"]
    if out:
        L += ["", (f"Files: `{out.name}/` trace.jsonl · sessions.jsonl · metrics.json · false_positives.jsonl · "
              "false_negatives.jsonl · config.json")]
    return "\n".join(L) + "\n"


COMPARE_KEYS = [("objections", "precision"), ("objections", "recall"), ("objections", "false_positive_rate"),
                ("objections", "category_accuracy"), ("opportunities", "precision"), ("opportunities", "recall"),
                ("commercial_state", "precision"), ("commercial_state", "recall"), ("compliance", "accuracy"),
                ("seller_action", "correct_source"), ("seller_action", "stale_card"),
                ("seller_action", "duplicate_card")]


def compare(base: Path, cand: Path) -> str:
    """Baseline vs candidate run directories (read only). Same inputs are required for a fair compare."""
    a, b = (json.loads((d / "metrics.json").read_text(encoding="utf-8")) for d in (base, cand))
    ca, cb = (json.loads((d / "config.json").read_text(encoding="utf-8")) for d in (base, cand))
    L = [f"# Compare — {ca['label']} vs {cb['label']}", ""]
    if ca["calls"] != cb["calls"]:
        L += ["**Warning:** different call sets; the comparison is not like for like.", ""]
    L += ["| metric | baseline | candidate | delta |", "|---|---|---|---|"]
    for sec, k in COMPARE_KEYS:
        x, y = a[sec].get(k), b[sec].get(k)
        d = round(y - x, 3) if isinstance(x, int | float) and isinstance(y, int | float) else None
        L.append(f"| {sec}.{k} | {_fmt(x)} | {_fmt(y)} | {_fmt(d)} |")
    for p in ("FAST_PATH", "LLM_CLASSIFIER", "OPPORTUNITY_ONLY", "NO_RECOMMENDATION"):
        for q in ("median", "p90"):
            x, y = ((r["latency"][p] or {}).get(q) for r in (a, b))
            d = round(y - x, 1) if x is not None and y is not None else None
            L.append(f"| latency.{p}.{q} | {_fmt(x)} | {_fmt(y)} | {_fmt(d)} |")
    ka, kb = ({r["case"]: r["status"] for r in r_["known_regressions"]} for r_ in (a, b))
    changed = [f"{c}: {ka.get(c)} -> {kb.get(c)}" for c in sorted(set(ka) | set(kb)) if ka.get(c) != kb.get(c)]
    L += ["", "Regression suite changes: " + ("; ".join(changed) if changed else "none")]
    return "\n".join(L) + "\n"
