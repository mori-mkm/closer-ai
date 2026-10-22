"""Long-call reliability soak: the real HTTP runtime + real Ollama, a synthetic call of 30-60 minutes.

    python -m closer_ai.live.soak --minutes 30                 # real time
    python -m closer_ai.live.soak --minutes 5 --gap 2 6        # shorter / denser

What it does (synthetic, invented lines only):
- serves the real runtime (`LiveHTTPServer`, `make_handler`) on a free loopback port;
- a client posts a call: closer and lead lines every `--gap` seconds, objections of every category
  between pains, neutrals and noise. Like the extension it injects faults: a retry of the same id
  (`--retry-rate`, as if a reply was lost) and a caption repeated with a new id (`--repeat-rate`);
- a poller GETs /recommendation every 0.5 s (as the dock) and checks each snapshot for incompatible
  states; it also checks the transcript never holds the same utterance twice;
- every 30 s it samples process RAM, Ollama RAM, VRAM and the model's GPU/CPU split.

Writes `<out>/samples.jsonl` and `<out>/summary.json` (technical fields only, no caption text).
The default `--out` is under the gitignored `artifacts/`.
"""
from __future__ import annotations

import argparse
import json
import random
import statistics
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from closer_ai.ai.ollama_provider import OllamaClassificationProvider
from closer_ai.demo.analyze_call import ContextGuard
from closer_ai.live.server import Runtime, bind_or_explain, make_handler, warm_up
from closer_ai.live.session import LiveConfig

CLOSER = ["Como vocês fazem esse processo hoje?", "Entendi. E como isso impacta vocês?", "Faz sentido.",
          "Deixa eu te mostrar como funciona na prática.", "Quantas pessoas usariam no dia a dia?",
          "Qual seria o próximo passo do seu lado?", "Perfeito, anotei aqui.", "E hoje quem cuida disso?"]
LEAD_NEUTRAL = ["Hoje temos cinco pessoas no time.", "A gente usa uma planilha compartilhada.",
                "Faz sentido, gostei bastante da proposta.", "Hoje a gente perde bastante tempo com isso.",
                "Cada vendedor faz do seu jeito, não temos processo nenhum.", "Pera aí, travou tudo aqui.",
                "Isso ficou claro, obrigado.", "A operação roda de segunda a sábado."]
LEAD_OBJECTION = ["Gostei da proposta, mas achei muito caro.", "Preciso falar com meu sócio antes de fechar.",
                  "Agora não dá, estamos no meio da safra, só depois da colheita.",
                  "Já temos um fornecedor que atende a gente e estamos satisfeitos com ele.",
                  "Tenho medo de investir e não dar resultado, já me queimei antes com isso.",
                  "Não temos equipe pra implantar isso agora, integrar com nosso sistema seria muito trabalho.",
                  "Sinceramente não sei se a gente precisa disso, nosso volume é muito pequeno.",
                  "O contrato de vocês é de doze meses? A gente só assina mensal."]


def _req(base: str, path: str, body: dict | None = None, timeout: float = 3.0) -> tuple[int, Any]:
    headers = {"X-AI-Closer": "1"}
    data = None
    if body is not None:
        headers["Content-Type"], data = "application/json", json.dumps(body).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(base + path, data=data, headers=headers),
                                    timeout=timeout) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, None
    except (OSError, ValueError) as e:  # refused, timeout, bad JSON: a failure, never silent
        return 0, {"error": type(e).__name__}


def snapshot_problems(v: dict[str, Any]) -> list[str]:
    """Incompatible states inside ONE GET answer (what the dock would show at once)."""
    p = []
    a, last, status, state = v.get("active_analysis"), v.get("last_completed_analysis"), v.get("status"), v.get("state")
    if a is not None and status != "ANALYZING":
        p.append(f"active_analysis with status {status}")
    if status == "RECOMMENDATION_READY" and state != "ACTIVE":
        p.append(f"RECOMMENDATION_READY with state {state}")
    if state == "ACTIVE" and status not in ("ANALYZING", "RECOMMENDATION_READY"):
        p.append(f"ACTIVE recommendation with status {status}")
    if a and last and a.get("segment_id") == last.get("segment_id"):
        p.append("active and last completed are the same segment")
    return p


FAIL_CLOSED = {"CLASSIFIER_INVALID", "UNCORROBORATED_CATEGORY", "NO_QUALIFYING_EPISODE", "AMBIGUOUS_CATEGORIES",
               "GUIDANCE_NO_KNOWLEDGE"}


def outcome_class(t: dict[str, Any]) -> tuple[str, str]:
    """(class, type) of one finished analysis: technical error vs valid fail-closed rejection vs no objection."""
    reason = str(t.get("reason", ""))
    if t.get("outcome") == "RECOMMENDED":
        return "recommended", "GUIDED"
    if t.get("outcome") == "KEPT":
        return "kept", reason
    if reason.startswith("ERROR:"):
        return "technical_error", t.get("error_type", "OTHER")
    if reason == "GUIDANCE_INVALID_RESPONSE":
        return "fail_closed", t.get("guidance_rejection", "GUIDANCE_INVALID")
    if reason in FAIL_CLOSED:
        return "fail_closed", reason
    if reason == "NO_OBJECTION":
        return "no_objection", reason
    return "other", reason


def outcome_table(timings: list[dict[str, Any]]) -> dict[str, Any]:
    done = [t for t in timings if t.get("sequence") is not None]
    table: dict[str, dict[str, Any]] = {}
    for t in done:
        cls, typ = outcome_class(t)
        row = table.setdefault(f"{cls}:{typ}", {"class": cls, "type": typ, "count": 0})
        row["count"] += 1
        if cls == "technical_error":
            row.setdefault("example", t.get("error_detail", ""))
            for k in ("error_stage",):
                row.setdefault(f"{k}s", {}).setdefault(t.get(k), 0)
                row[f"{k}s"][t.get(k)] += 1
            dr = (t.get("error_usage") or {}).get("done_reason")
            row.setdefault("done_reasons", {}).setdefault(str(dr), 0)
            row["done_reasons"][str(dr)] += 1
            row.setdefault("output_tokens", []).append((t.get("error_usage") or {}).get("output_tokens"))
    for row in table.values():
        row["pct_analyses"] = round(100 * row["count"] / len(done), 1) if done else 0.0
    return {"analyses": len(done), "rows": sorted(table.values(), key=lambda r: -r["count"])}


def _resources(ollama_url: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    try:
        import psutil  # optional
        me = psutil.Process()
        out["runtime_rss_mb"] = round(me.memory_info().rss / 2**20)
        procs = [p for p in psutil.process_iter(["name"])
                 if "ollama" in (p.info["name"] or "").lower() or "llama-server" in (p.info["name"] or "").lower()]
        infos = [p.memory_info() for p in procs]
        # rss = working set (Windows trims it under pressure); private = committed memory (leak signal)
        out["ollama_rss_mb"] = round(sum(i.rss for i in infos) / 2**20)
        out["ollama_private_mb"] = round(sum(getattr(i, "private", i.vms) for i in infos) / 2**20)
        out["ollama_processes"] = len(procs)
        vm = psutil.virtual_memory()
        out["system_available_mb"] = round(vm.available / 2**20)
        out["swap_used_mb"] = round(psutil.swap_memory().used / 2**20)
    except Exception as exc:  # noqa: BLE001 - sampling must never stop the soak
        out["ram_error"] = type(exc).__name__
    try:
        q = subprocess.run(["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"],
                           capture_output=True, text=True, timeout=5, check=False).stdout.strip().split(",")
        out["vram_used_mb"], out["vram_total_mb"] = int(q[0]), int(q[1])
    except Exception as exc:  # noqa: BLE001
        out["vram_error"] = type(exc).__name__
    try:
        with urllib.request.urlopen(f"{ollama_url}/api/ps", timeout=3) as r:
            models = json.loads(r.read()).get("models", [])
        out["model_loaded"] = bool(models)
        if models:
            out["model_gpu_pct"] = round(models[0]["size_vram"] / models[0]["size"] * 100)
    except Exception:  # noqa: BLE001
        out["model_loaded"] = None
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--minutes", type=float, default=30.0)
    ap.add_argument("--gap", type=float, nargs=2, default=(4.0, 10.0), metavar=("MIN", "MAX"),
                    help="seconds between utterances")
    ap.add_argument("--objection-rate", type=float, default=0.25, help="share of lead lines that are objections")
    ap.add_argument("--retry-rate", type=float, default=0.10, help="re-post the same id (lost reply)")
    ap.add_argument("--repeat-rate", type=float, default=0.03, help="repeat a caption with a new id")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--model", default="qwen3:8b")
    ap.add_argument("--out", type=Path, default=Path("artifacts/live_soak"))
    a = ap.parse_args(argv)
    rnd = random.Random(a.seed)
    a.out.mkdir(parents=True, exist_ok=True)

    ollama = OllamaClassificationProvider(a.model, timeout=120.0, num_ctx=4096, keep_alive="30m")
    provider = ContextGuard(ollama, num_ctx=4096, reserve_tokens=1024)
    runtime = Runtime(provider, LiveConfig(), {"Closer Teste"}, log=lambda _s: None)
    server = bind_or_explain(0, make_handler(runtime))
    base = f"http://127.0.0.1:{server.server_address[1]}"
    threading.Thread(target=server.serve_forever, daemon=True).start()
    warm_up(ollama, lambda _s: None, runtime)

    mid, stop = "soak-call", threading.Event()
    c: dict[str, int] = dict.fromkeys(("posted", "post_attempts", "accepted", "duplicate_sequence", "duplicate_text",
                                       "rejected", "post_failures", "retries_injected", "repeats_injected", "polls",
                                       "poll_failures", "inconsistent_snapshots"), 0)
    problems: list[str] = []
    accepted_ids: set[int] = set()
    samples = (a.out / "samples.jsonl").open("w", encoding="utf-8")

    def post(seq: int, speaker: str, text: str) -> None:
        c["post_attempts"] += 1
        status, body = _req(base, "/live-utterance", {"meeting_id": mid, "speaker": speaker, "text": text,
                                                       "timestamp": time.time(), "sequence": seq})
        if status != 200:
            c["post_failures"] += 1
            return
        key = {"ACCEPTED": "accepted", "DUPLICATE_SEQUENCE": "duplicate_sequence",
               "DUPLICATE_TEXT": "duplicate_text"}.get(body.get("status"), "rejected")
        c[key] += 1
        if key == "accepted":
            accepted_ids.add(seq)

    def poller() -> None:
        while not stop.is_set():
            status, v = _req(base, f"/recommendation?meeting_id={mid}")
            c["polls"] += 1
            if status != 200:
                c["poll_failures"] += 1
            else:
                for p in snapshot_problems(v):
                    c["inconsistent_snapshots"] += 1
                    if len(problems) < 50:
                        problems.append(p)
            stop.wait(0.5)

    def sampler() -> None:
        while not stop.is_set():
            s = runtime.sessions.get(mid)
            row = {"t_s": round(time.time() - t0), **_resources("http://127.0.0.1:11434"),
                   "health": runtime.health()["model_state"], **(dict(s.counters) if s else {}),
                   # everything needed if the soak is stopped before its summary (e.g. low system memory)
                   "error_reasons": dict(s.error_reasons) if s else {}, "client": dict(c),
                   "outcomes": outcome_table(list(s.timings)) if s else None}
            samples.write(json.dumps(row) + "\n")
            samples.flush()
            stop.wait(30)

    t0 = time.time()
    threads = [threading.Thread(target=f, daemon=True) for f in (poller, sampler)]
    for t in threads:
        t.start()
    seq, end, last_text = 0, t0 + a.minutes * 60, ("", "")
    try:
        while time.time() < end:
            seq += 1
            closer = seq % 2 == 1
            if closer:
                speaker, text = "Closer Teste", rnd.choice(CLOSER)
            else:
                speaker = "Lead Teste"
                text = rnd.choice(LEAD_OBJECTION if rnd.random() < a.objection_rate else LEAD_NEUTRAL)
            if rnd.random() < a.repeat_rate and last_text[0]:  # the same caption again, new id
                speaker, text = last_text
                c["repeats_injected"] += 1
            post(seq, speaker, text)
            c["posted"] += 1
            last_text = (speaker, text)
            if rnd.random() < a.retry_rate:  # lost reply -> the extension retries the same id
                c["retries_injected"] += 1
                post(seq, speaker, text)
            time.sleep(rnd.uniform(*a.gap))
    finally:
        time.sleep(20)  # let the last analysis finish
        stop.set()
        for t in threads:
            t.join(5)
        samples.close()
        server.shutdown()
        server.server_close()

    s = runtime.sessions[mid]
    seqs = [u.sequence for u in s.utterances]
    timings = [t for t in s.timings if t.get("sequence") is not None]

    def stat(key: str) -> dict[str, Any] | None:
        vals = sorted(t[key] for t in timings if isinstance(t.get(key), int))
        if not vals:
            return None
        return {"n": len(vals), "median": statistics.median(vals), "p95": vals[min(len(vals) - 1, int(0.95 * len(vals)))],
                "max": vals[-1]}

    rec = [t for t in timings if t["outcome"] == "RECOMMENDED"]
    rows = [json.loads(line) for line in (a.out / "samples.jsonl").read_text(encoding="utf-8").splitlines()]
    summary = {
        "duration_min": round((time.time() - t0) / 60, 1),
        "client": c,
        "runtime_counters": dict(s.counters),
        "transcript_utterances": len(seqs),
        "transcript_duplicate_ids": len(seqs) - len(set(seqs)),
        # confirmed ACCEPTED by the runtime but missing from its transcript = silent loss
        "lost_silently": len(accepted_ids - set(seqs)),
        "outcomes": {o: sum(t["outcome"] + ":" + t["reason"] == o for t in timings)
                     for o in sorted({t["outcome"] + ":" + t["reason"] for t in timings})},
        "outcome_table": outcome_table(timings),
        "timeouts_or_errors": sum(str(t["reason"]).startswith("ERROR") for t in timings),
        "queue_wait_ms": stat("queue_wait_ms"),
        "classifier_latency_ms": stat("classifier_latency_ms"),
        "recommendation_end_to_end_ms": {"n": len(rec), **(
            {"median": statistics.median([t["end_to_end_latency_ms"] for t in rec]),
             "max": max(t["end_to_end_latency_ms"] for t in rec)} if rec else {})},
        "superseded_leads": sum(t.get("superseded_leads", 0) for t in timings),
        "resources": {k: {"min": min(r[k] for r in rows if k in r), "max": max(r[k] for r in rows if k in r)}
                      for k in ("runtime_rss_mb", "ollama_rss_mb", "ollama_private_mb", "system_available_mb",
                                "swap_used_mb", "vram_used_mb", "model_gpu_pct")
                      if any(k in r for r in rows)},
        "model_unloaded_samples": sum(r.get("model_loaded") is False for r in rows),
        "health_final": runtime.health(),
        "inconsistency_examples": problems[:10],
    }
    (a.out / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(json.dumps(summary, indent=1))
    return 0 if not (summary["transcript_duplicate_ids"] or summary["lost_silently"] or c["inconsistent_snapshots"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
