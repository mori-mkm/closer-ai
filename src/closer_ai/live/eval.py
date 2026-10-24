"""Real Call Validation & Calibration v1: replay calls through the live runtime, one utterance at a time.

    calls (canonical JSONL | calibration kit) -> replay (virtual time, single-flight worker)
      -> trace.jsonl -> metrics vs annotations (eval_metrics.py) -> EVAL_REPORT.md

Measurement only: nothing here changes production behavior. The replay drives the real `Runtime` /
`LiveSalesSession` (latest-utterance anchoring, fast path, classifier, guidance, Commercial State,
compliance, opportunities, arbitration) exactly like the extension does:

- **One utterance at a time**, in sequence order, never the whole transcript.
- **Virtual time.** The session clock follows the call's timestamps, plus the real time each model job
  took, so TTL, cooldown, the 90 s window and the facts pause behave as in the call.
- **Single-flight worker, latest wins** (mirrors `Runtime._kick`). A lead line that arrives while an
  analysis is running waits in the pending slot, and a newer one replaces it. Commercial facts are
  extracted only after a `facts_idle_seconds` pause.

ponytail: a job runs to completion before the lines that arrived during it are added (its input is
exact). Those lines' snapshots are therefore taken at `visible_at = max(arrival, job end)`. The
recommendation timings come from the session itself and are exact; the dock's 0.5 s poll is not added.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from closer_ai.live.server import Runtime, parse_utterance
from closer_ai.live.session import REJECTION_REASONS, LiveConfig

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "evals" / "real_calls" / "fixtures"
KIT = ROOT / "docs" / "evals" / "calibration" / "SYNTHETIC_CASES_V0_1.md"
REAL_CALLS = ROOT / "data" / "raw" / "real_calls"  # gitignored (data/raw/): real calls never enter Git
RUNS = ROOT / "artifacts" / "eval"  # gitignored: traces contain call text
ROLES = ("closer", "lead", "other")
DEFAULT_GAP = 6.0  # seconds between utterances when a call has no timestamps


# --- import -----------------------------------------------------------------------------------------

def validate_rows(rows: list[dict[str, Any]]) -> list[str]:
    """Canonical utterance rows: meeting_id, speaker, role, text, sequence (+ optional timestamp)."""
    errors = []
    for i, r in enumerate(rows):
        for k, kind in (("meeting_id", str), ("speaker", str), ("role", str), ("text", str), ("sequence", int)):
            if not isinstance(r.get(k), kind) or isinstance(r.get(k), bool):
                errors.append(f"row {i}: {k} must be {kind.__name__}")
        if r.get("role") not in ROLES:
            errors.append(f"row {i}: role must be one of {ROLES}")
        if "timestamp" in r and not isinstance(r["timestamp"], int | float | str):
            errors.append(f"row {i}: timestamp must be a number or ISO-8601")
    seqs = [(r.get("meeting_id"), r.get("sequence")) for r in rows]
    if len(seqs) != len(set(seqs)):
        errors.append("duplicate (meeting_id, sequence)")
    return errors


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def kit_calls(path: Path = KIT) -> list[dict[str, Any]]:
    """Adapter: the Synthetic Calibration Kit v0.1 tables (CALnn) -> canonical rows (read in place)."""
    rows, call = [], None
    for line in path.read_text(encoding="utf-8").splitlines():
        if m := re.match(r"^- call_id: `(CAL\d+)`", line):
            call = m.group(1)
        elif call and (m := re.match(r"^\| (CAL\d+_S\d+) \| (\d+) \| (\w+) \| (.*) \|$", line)):
            rows.append({"meeting_id": call, "speaker": f"{call}_{m.group(3).upper()}", "role": m.group(3),
                         "text": m.group(4).strip(), "sequence": int(m.group(2)) + 1,
                         "segment_ref": m.group(1)})
    return rows


def load_calls(path: Path) -> dict[str, list[dict[str, Any]]]:
    """A canonical .jsonl file, the kit .md, or a directory of them (annotation files are skipped)."""
    files = sorted(path.rglob("*")) if path.is_dir() else [path]
    rows: list[dict[str, Any]] = []
    for f in files:
        if f.suffix == ".jsonl" and not f.name.endswith(".annotations.jsonl"):
            rows += read_jsonl(f)
        elif f.suffix == ".md" and f.name.startswith("SYNTHETIC_CASES"):
            rows += kit_calls(f)
    if errors := validate_rows(rows):
        raise ValueError(f"{path}: " + "; ".join(errors[:5]))
    calls: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        calls.setdefault(r["meeting_id"], []).append(r)
    return {mid: sorted(rs, key=lambda r: r["sequence"]) for mid, rs in calls.items()}


# --- sampling ---------------------------------------------------------------------------------------

_TAGS = {"price": r"\b(?:caro|preco|valor|investimento|orcamento|r\$)",
         "authority": r"\b(?:socio|socia|diretor|diretoria|aprovar|aprovacao|decid)",
         "think": r"\b(?:vou pensar|pensar melhor|analisar com calma)"}


def call_tags(rows: list[dict[str, Any]]) -> list[str]:
    from closer_ai.live.commercial_state import fold
    text = fold(" ".join(r["text"] for r in rows if r["role"] == "lead"))
    tags = [t for t, rx in _TAGS.items() if re.search(rx, text)]
    tags.append("short" if len(rows) < 40 else "long" if len(rows) > 150 else "medium")
    outcome = next((r["outcome"] for r in rows if r.get("outcome")), None)  # optional call metadata
    return tags + ([f"outcome:{outcome}"] if outcome else [])


def select_calls(calls: dict[str, list[dict[str, Any]]], n: int, seed: str = "v1") -> list[str]:
    """Deterministic, diverse sample: round-robin over tags, each tag ordered by sha256(seed + id)."""
    if n <= 0 or n >= len(calls):
        return sorted(calls)
    key = {mid: hashlib.sha256(f"{seed}:{mid}".encode()).hexdigest() for mid in calls}
    by_tag: dict[str, list[str]] = {}
    for mid in sorted(calls, key=key.get):
        for t in call_tags(calls[mid]):
            by_tag.setdefault(t, []).append(mid)
    chosen: list[str] = []
    while len(chosen) < n:
        for t in sorted(by_tag):
            nxt = next((m for m in by_tag[t] if m not in chosen), None)
            if nxt and len(chosen) < n:
                chosen.append(nxt)
        if all(m in chosen for ms in by_tag.values() for m in ms):
            break
    return chosen


# --- replay -----------------------------------------------------------------------------------------

class VirtualClock:
    """Call time. Frozen between jobs; while a model job runs it advances with the real elapsed time."""

    def __init__(self, t: float) -> None:
        self.t, self._mark = t, None

    def __call__(self) -> float:
        return self.t if self._mark is None else self.t + (time.perf_counter() - self._mark)

    @contextmanager
    def running(self):
        self._mark = time.perf_counter()
        try:
            yield
        finally:
            self.t, self._mark = self(), None


def _ts(rows: list[dict[str, Any]], gap: float) -> list[float]:
    from closer_ai.live.server import _timestamp
    if all("timestamp" in r for r in rows):
        return [_timestamp(r["timestamp"]) for r in rows]
    return [1_000.0 + i * gap for i in range(len(rows))]


def snapshot(runtime: Runtime, mid: str) -> dict[str, Any]:
    """What the copilot knows and shows right now (one poll of GET /recommendation)."""
    view = runtime.recommendation(mid)
    s = runtime.sessions[mid]
    sa = view.get("seller_action")
    return {"rec": None if view["state"] == "NONE" else {"id": view["id"], "category": view["category"],
                                                         "question": view.get("question")},
            "seller_action": sa and {k: sa[k] for k in ("source", "source_id", "priority", "title", "action")},
            "facts": {f"{k}|{f['value']}": f["segment_ids"] for k, v in view["commercial_state"].items() for f in v},
            "rules": {r["rule_id"]: r["status"] for r in view["playbook_compliance"]["rule_results"]},
            "ops": {o["id"]: o["status"] for o in view["opportunities"]["opportunities"]},
            "ms": {"compliance_ms": s.compliance_ms, "opportunity_ms": s.opportunity_ms}}


def delta(prev: dict[str, Any] | None, cur: dict[str, Any]) -> dict[str, Any]:
    prev = prev or {"facts": {}, "rules": {}, "ops": {}, "seller_action": None}
    return {"commercial_state_delta": [k for k in cur["facts"] if k not in prev["facts"]],
            "compliance_delta": {r: [prev["rules"].get(r), st] for r, st in cur["rules"].items()
                                 if prev["rules"].get(r) != st},
            "opportunities_created": [o for o in cur["ops"] if o not in prev["ops"]],
            "opportunities_resolved": [o for o, st in cur["ops"].items()
                                       if st == "RESOLVED" and prev["ops"].get(o) != "RESOLVED"]}


def replay_call(runtime: Runtime, mid: str, rows: list[dict[str, Any]], gap: float = DEFAULT_GAP) -> dict[str, Any]:
    """Replay one call; returns {"events": [...], "session": LiveSalesSession, "recs": {id: Recommendation}}."""
    runtime.closer_names |= {r["speaker"].strip().lower() for r in rows if r["role"] == "closer"}
    times = _ts(rows, gap)
    clock = VirtualClock(times[0])
    s = runtime.session(mid)
    s.clock = clock
    events: list[dict[str, Any]] = []
    recs: dict[int, Any] = {}
    state = {"free_at": float("-inf"), "prev": None}
    sids: dict[int, str] = {}

    def record(kind: str, **fields: Any) -> dict[str, Any]:
        snap = snapshot(runtime, mid)
        ev = {"kind": kind, "meeting_id": mid, **fields, "visible_at": round(clock(), 3), **delta(state["prev"], snap),
              "seller_action": snap["seller_action"], "recommendation": snap["rec"], **snap["ms"]}
        state["prev"] = snap
        events.append(ev)
        return ev

    def job(kind: str, start: float) -> None:
        clock.t = max(clock.t, start)
        with clock.running():
            t = s.analyze() if kind == "analysis" else s.extract()
        state["free_at"] = clock.t
        if kind == "analysis":
            runtime._done(t)
            if t.get("recommendation_id") is not None:
                recs[t["recommendation_id"]] = s.current_recommendation
            record("analysis", sequence=t.get("sequence"), started_at=round(start, 3), timing=_timing(t))
        elif t.get("outcome") != "NOTHING":
            record("facts", started_at=round(start, 3), outcome=t.get("outcome"))

    def drain(until: float) -> None:
        """Run the worker jobs that START before `until` (analysis first; facts only after a pause)."""
        while True:
            start = max(clock.t, state["free_at"])
            if start > until:
                return
            if s.should_analyze():
                job("analysis", start)
            elif s.should_extract():
                last = max([u.received_at for u in s.utterances] + [s._analysis_done_at])
                start = max(start, last + s.config.facts_idle_seconds)
                if start > until:
                    return
                job("facts", start)
            else:
                return

    for r, ts in zip(rows, times, strict=True):
        drain(ts)
        clock.t = max(clock.t, ts)
        status = _add(runtime, s, r, ts)
        if r["sequence"] in s._short_ids:
            sids[r["sequence"]] = s._sid(r["sequence"])
        added = next((u for u in s.utterances if u.sequence == r["sequence"]), None)
        record("utterance", sequence=r["sequence"], segment_id=sids.get(r["sequence"]), speaker=r["speaker"],
               role=r["role"], runtime_role=added.role if added else None, text=r["text"],
               t=round(ts, 3), delivery=status, trigger=s.last_trigger_reason if status == "ACCEPTED" else status)
        drain(ts)  # an idle worker starts right away
    drain(float("inf"))
    with clock.running():
        s.finalize()
    s.current()  # applies a lazy expiry to the last recommendation
    return {"events": _annotate(events, s, recs), "session": s, "recs": recs, "times": dict(
        zip((r["sequence"] for r in rows), times, strict=True))}


def _add(runtime: Runtime, s: Any, r: dict[str, Any], ts: float) -> str:
    """Runtime.receive without its inline analysis: the virtual worker (drain) runs the jobs."""
    utt = parse_utterance({k: r[k] for k in ("meeting_id", "speaker", "text", "sequence")} | {"timestamp": ts},
                          runtime.closer_names, ts)
    with s.lock:
        s.add(utt)
        return s.last_add_status


def _timing(t: dict[str, Any]) -> dict[str, Any]:
    keep = ("classification_source", "outcome", "reason", "category", "target_segment_ids", "recommendation_id",
            "classifier_latency_ms", "guidance_latency_ms", "end_to_end_latency_ms", "queue_wait_ms",
            "superseded_leads", "error_type", "guard_ms", "category_before", "guidance_rejection")
    return {k: t[k] for k in keep if k in t}


def detected(timing: dict[str, Any]) -> bool:
    """The engine decided there is an objection (recorded in the Commercial State): it passed the
    classifier, validation, anchoring, the non-objection guard and the gates. Guidance may still have failed."""
    return bool(timing.get("category")) and timing.get("reason") not in REJECTION_REASONS


def _annotate(events: list[dict[str, Any]], s: Any, recs: dict[int, Any]) -> list[dict[str, Any]]:
    """Fill each utterance row with what the engine did for it (its analysis may finish lines later)."""
    by_seq = {e["sequence"]: e for e in events if e["kind"] == "analysis"}
    displayed = {t["recommendation_id"]: t for t in s.timings if t.get("recommendation_id") is not None}
    for e in events:
        if e["kind"] != "utterance":
            continue
        a = by_seq.get(e["sequence"])
        t = a["timing"] if a else {}
        rid = t.get("recommendation_id")
        rec = recs.get(rid)
        shown = displayed.get(rid, {})
        e["objection"] = {
            "analyzed": "ANALYZED" if a else ("COALESCED" if e["trigger"] is None else e["trigger"]),
            "detected": detected(t), "category": t.get("category"), "source": t.get("classification_source"),
            "outcome": t.get("outcome"), "reason": t.get("reason"),
            "recommendation": rec and {"id": rec.id, "question": rec.question},
            "recommendation_state": rec.state if rec else None,
            "superseded_by": getattr(rec, "superseded_by", None)}
        e["timings"] = {"classifier_ms": t.get("classifier_latency_ms"), "guidance_ms": t.get("guidance_latency_ms"),
                        "displayed_ms": (round((shown["displayed_at"] - shown["caption_received_at"]) * 1000)
                                         if shown.get("displayed_at") else None),
                        "compliance_ms": e["compliance_ms"], "opportunity_ms": e["opportunity_ms"]}
    return events


def session_summary(mid: str, rows: list[dict[str, Any]], result: dict[str, Any]) -> dict[str, Any]:
    s, events = result["session"], result["events"]
    comp, ops, _ = s.intelligence()
    times = list(result["times"].values())
    return {"meeting_id": mid, "call_duration_s": round(times[-1] - times[0], 1), "utterances": len(rows),
            "lead_utterances": sum(r["role"] == "lead" for r in rows),
            "objections_detected": sum(e["kind"] == "analysis" and detected(e["timing"]) for e in events),
            "recommendations_created": s.counters["recommendations_created"],
            "opportunities_detected": len(ops.opportunities),
            "opportunities_resolved": len(ops.by_status("RESOLVED")),
            "opportunities_missed": [o.playbook_op_id for o in ops.by_status("ACTIVE")],
            "required_compliance_satisfied": len(comp.completed_required),
            "required_compliance_pending": len(comp.pending_required),
            "seller_actions_shown": len({e["seller_action"]["source_id"] for e in events if e["seller_action"]}),
            "analysis_errors": s.counters["analysis_errors"], "tags": call_tags(rows),
            "final": {"opportunities": [{k: o.view()[k] for k in ("id", "playbook_op_id", "status", "trigger_segment_ids")}
                                        for o in ops.opportunities],
                      "facts": s.commercial.view(), "rules": {r.rule_id: r.status for r in comp.rule_results}}}


# --- run --------------------------------------------------------------------------------------------

def _git_sha() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False,
                              timeout=5).stdout.strip() or None
    except OSError:
        return None


def run(calls: dict[str, list[dict[str, Any]]], provider: Any, config: LiveConfig, gap: float = DEFAULT_GAP,
        progress=lambda _m: None, out: Path | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Replay every call in a fresh runtime; returns (trace events, session summaries). With `out`, each
    finished call is appended to trace.jsonl / sessions.jsonl at once, so an interrupted run keeps what it
    did (`--rescore` / `--resume`)."""
    trace, sessions = [], []
    for mid, rows in calls.items():
        runtime = Runtime(provider, config, set(), log=lambda _s: None)
        t0 = time.time()
        result = replay_call(runtime, mid, rows, gap)
        trace += result["events"]
        sessions.append(session_summary(mid, rows, result))
        if out is not None:
            for name, items in (("trace", result["events"]), ("sessions", sessions[-1:])):
                with (out / f"{name}.jsonl").open("a", encoding="utf-8") as f:
                    f.writelines(json.dumps(x, ensure_ascii=False) + "\n" for x in items)
        progress(f"{mid}: {len(rows)} utterances in {time.time() - t0:.1f}s")
    return trace, sessions


def new_run_dir(label: str, base: Path = RUNS) -> Path:
    """artifacts/eval/<label>-<timestamp>: a run never overwrites another one."""
    stem = base / f"{label}-{datetime.now():%Y%m%d-%H%M%S}"
    d, n = stem, 1
    while d.exists():
        n += 1
        d = stem.with_name(f"{stem.name}-{n}")
    d.mkdir(parents=True)
    return d


def write_run(out: Path, label: str, calls: dict[str, list[dict[str, Any]]], annotations: list[dict[str, Any]],
              trace: list[dict[str, Any]], sessions: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
    from closer_ai.live import eval_metrics as em
    metrics = em.compute(calls, annotations, trace, sessions)
    (out / "trace.jsonl").write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in trace), encoding="utf-8")
    (out / "sessions.jsonl").write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in sessions),
                                        encoding="utf-8")
    for name in ("false_positives", "false_negatives"):
        (out / f"{name}.jsonl").write_text("".join(json.dumps(x, ensure_ascii=False) + "\n"
                                                   for x in metrics.pop(f"_{name}")), encoding="utf-8")
    meta = {"label": label, "created_at": datetime.now().isoformat(timespec="seconds"), "git_sha": _git_sha(),
            "calls": sorted(calls), **config}
    (out / "config.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False), encoding="utf-8")
    labeled = {a["meeting_id"] for a in annotations}
    if stubs := em.review_template(trace, labeled):
        (out / "review_template.annotations.jsonl").write_text(
            "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in stubs), encoding="utf-8")
    (out / "metrics.json").write_text(json.dumps(metrics, indent=1, ensure_ascii=False), encoding="utf-8")
    (out / "EVAL_REPORT.md").write_text(em.report(meta, metrics, sessions, out), encoding="utf-8")
    return metrics


def main(argv: list[str] | None = None) -> int:
    from closer_ai.live import eval_metrics as em
    p = argparse.ArgumentParser(prog="python -m closer_ai.live.eval", description=__doc__.splitlines()[0])
    p.add_argument("--input", type=Path, action="append",
                   help="canonical .jsonl, the kit SYNTHETIC_CASES_*.md, or a directory (repeatable)")
    p.add_argument("--fixtures", action="store_true", help="the known regression suite + the calibration kit")
    p.add_argument("--real", action="store_true", help=f"the real calls in {REAL_CALLS.relative_to(ROOT)}")
    p.add_argument("--annotations", type=Path, action="append", default=[],
                   help="annotation .jsonl (default: *.annotations.jsonl next to the inputs)")
    p.add_argument("--label", default="baseline")
    p.add_argument("--out", type=Path, help=f"run directory (default: {RUNS.relative_to(ROOT)}/<label>-<time>)")
    p.add_argument("--sample", type=int, default=0, help="deterministic diverse sample of N calls")
    p.add_argument("--seed", default="v1")
    p.add_argument("--calls", default="", help="comma-separated meeting ids (after loading)")
    p.add_argument("--gap", type=float, default=DEFAULT_GAP, help="seconds between lines without timestamps")
    p.add_argument("--model", default="qwen3:8b")
    p.add_argument("--num-ctx", type=int, default=4096)
    p.add_argument("--no-fast-path", action="store_true")
    p.add_argument("--no-commercial", action="store_true")
    p.add_argument("--compare", type=Path, nargs=2, metavar=("BASELINE", "CANDIDATE"),
                   help="compare two run directories (writes nothing, prints Markdown)")
    p.add_argument("--rescore", type=Path, metavar="RUN_DIR",
                   help="recompute metrics + report from a saved (even partial) run, e.g. after new annotations; "
                        "no model call")
    p.add_argument("--resume", type=Path, metavar="RUN_DIR", help="continue an interrupted run (skips finished calls)")
    a = p.parse_args(argv)

    if a.compare:
        print(em.compare(*a.compare))
        return 0
    saved = a.rescore or a.resume
    if saved:
        prev = json.loads((saved / "config.json").read_text(encoding="utf-8"))
        a.label, a.sample, a.seed, a.gap = prev["label"], prev["sample"], prev["seed"], prev["gap_s"]
        a.model, a.num_ctx = prev["model"], prev["num_ctx"]
        a.no_fast_path, a.no_commercial = not prev["fast_path"], not prev["commercial_facts"]
        a.input, a.fixtures, a.real, a.out = [Path(x) for x in prev["inputs"]], False, False, saved
    inputs = list(a.input or []) + ([FIXTURES, KIT] if a.fixtures else []) + ([REAL_CALLS] if a.real else [])
    if not inputs:
        p.error("--input, --fixtures or --real")
    calls: dict[str, list[dict[str, Any]]] = {}
    for path in inputs:
        if not path.exists():
            print(json.dumps({"input": str(path), "calls": 0, "status": "NOT_FOUND"}))
            continue
        calls |= load_calls(path)
    annotations = em.load_annotations(inputs, a.annotations)
    if a.calls:
        calls = {m: calls[m] for m in a.calls.split(",") if m in calls}
    selected = select_calls(calls, a.sample, a.seed)
    calls = {m: calls[m] for m in selected}
    if not calls:
        print(json.dumps({"calls": 0, "status": "NO_CALLS"}))
        return 1
    meta = {"model": a.model, "num_ctx": a.num_ctx, "fast_path": not a.no_fast_path,
            "commercial_facts": not a.no_commercial, "gap_s": a.gap, "sample": a.sample, "seed": a.seed,
            "inputs": [str(x) for x in inputs]}
    out = a.out or new_run_dir(a.label)
    out.mkdir(parents=True, exist_ok=True)
    done_trace = read_jsonl(out / "trace.jsonl") if (out / "trace.jsonl").exists() else []
    done = read_jsonl(out / "sessions.jsonl") if (out / "sessions.jsonl").exists() else []
    finished = {x["meeting_id"] for x in done}
    if a.rescore:
        partial = sorted(set(calls) - finished)
        calls = {m: r for m, r in calls.items() if m in finished}
        metrics = write_run(out, a.label, calls, annotations, done_trace, done, {**meta, "not_replayed": partial})
        print(json.dumps({"out": str(out), "not_replayed": partial, "summary": metrics["summary"]},
                         ensure_ascii=False, indent=1))
        return 0
    if not (out / "config.json").exists():  # written first: an interrupted run can be rescored / resumed
        (out / "config.json").write_text(json.dumps({"label": a.label, "status": "RUNNING", **meta}, indent=1),
                                         encoding="utf-8")
    todo = {m: r for m, r in calls.items() if m not in finished}

    from closer_ai.ai.ollama_provider import OllamaClassificationProvider
    from closer_ai.demo.analyze_call import ContextGuard
    ollama = OllamaClassificationProvider(a.model, timeout=120.0, num_ctx=a.num_ctx)
    provider = ContextGuard(ollama, num_ctx=a.num_ctx, reserve_tokens=1024)
    ollama.classify('Return {"ok": true} as JSON.')  # warm-up: load the model (not measured)
    config = LiveConfig(commercial_facts=not a.no_commercial, fast_path=not a.no_fast_path)
    trace, sessions = run(todo, provider, config, a.gap, progress=lambda m: print(m, flush=True), out=out)
    metrics = write_run(out, a.label, calls, annotations, done_trace + trace, done + sessions, meta)
    print(json.dumps({"out": str(out), "summary": metrics["summary"]}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
