"""Live latency benchmark: real Ollama, the real Runtime/LiveSalesSession path, synthetic lines only.

    python -m closer_ai.live.bench --runs 5
    python -m closer_ai.live.bench --runs 10 --cases price --poll 0.5
    python -m closer_ai.live.bench --precision      # 14 probe lines once each: shown right / false shown

Each run is a fresh meeting: one closer line, then the case's lead line. The lead line goes through
`Runtime.receive` (background worker, as from the extension), and a poller calls
`Runtime.recommendation` every `--poll` seconds, as the sidebar does. Per run it prints the session's
timing record (technical fields only); at the end, median and max per metric and case.
Browser-side time before the runtime (caption stability wait) is not simulated here; the extension
sends it as `changed_at` and the runtime records it as `caption_stable_wait_ms`.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import threading
import time

from closer_ai.ai.ollama_provider import OllamaClassificationProvider
from closer_ai.demo.analyze_call import ContextGuard
from closer_ai.live.server import Runtime, parse_utterance
from closer_ai.live.session import LiveConfig

CASES = {  # invented lines, no real person or company
    "price": "Gostei da proposta, mas achei muito caro.",
    "authority": "Preciso falar com meu sócio antes de fechar.",
    "neutral": "Hoje temos cinco pessoas no time.",
}
CLOSER_LINE = "Como vocês fazem isso hoje?"
PROBE = [  # (expected category or None, lead line): invented; 6 non-objections, 8 objections
    (None, "A gente perde bastante tempo com isso."),
    (None, "Hoje cada vendedor faz do seu jeito, não temos processo nenhum."),
    (None, "Faz sentido, gostei bastante da proposta."),
    (None, "Quantas pessoas da sua equipe usam a ferramenta hoje?"),
    (None, "Hoje usamos uma planilha, mas ninguém atualiza direito."),
    (None, "Hoje temos cinco pessoas no time."),
    ("PRICE_BUDGET", "Gostei da proposta, mas achei muito caro."),
    ("AUTHORITY_INTERNAL_BUY_IN", "Preciso falar com meu sócio antes de fechar."),
    ("AUTHORITY_INTERNAL_BUY_IN", "Eu preciso falar com meu sócio antes de fechar qualquer coisa."),
    ("TIMING_PRIORITY", "Agora não dá, estamos no meio da safra, só depois da colheita."),
    ("COMPETITION_EXISTING_SOLUTION", "Já temos um fornecedor que atende a gente e estamos satisfeitos com ele."),
    ("TRUST_RISK", "Tenho medo de investir e não dar resultado, já me queimei antes com isso."),
    ("IMPLEMENTATION_INTEGRATION", "Não temos equipe pra implantar isso agora, integrar com nosso sistema seria muito trabalho."),
    ("NEED_VALUE_FIT", "Sinceramente não sei se a gente precisa disso, nosso volume é muito pequeno."),
]
METRICS = ("queue_wait_ms", "classifier_latency_ms", "classifier_ollama_ms", "classifier_output_tokens",
           "policy_ms", "guidance_latency_ms", "guidance_ollama_ms", "guidance_output_tokens",
           "end_to_end_latency_ms", "displayed_latency_ms")


def flat(t: dict) -> dict:
    """The timing record with the Ollama usage fields lifted to top level."""
    out = {k: v for k, v in t.items() if not isinstance(v, dict)}
    for stage in ("classifier", "guidance"):
        u = t.get(stage) or {}
        out[f"{stage}_ollama_ms"] = u.get("ollama_total_ms")
        out[f"{stage}_output_tokens"] = u.get("output_tokens")
        out[f"{stage}_prompt_tokens"] = u.get("prompt_tokens")
        out[f"{stage}_ollama_load_ms"] = u.get("ollama_load_ms")
        out[f"{stage}_ollama_prompt_eval_ms"] = u.get("ollama_prompt_eval_ms")
        out[f"{stage}_ollama_eval_ms"] = u.get("ollama_eval_ms")
    return out


def run_once(runtime: Runtime, meeting_id: str, text: str, poll: float, timeout: float = 120.0,
             closer_line: str = CLOSER_LINE) -> dict:
    s = runtime.session(meeting_id)
    now = time.time()
    runtime.receive(parse_utterance({"meeting_id": meeting_id, "speaker": "Closer Teste", "text": closer_line,
                                     "timestamp": now, "sequence": 1}, runtime.closer_names, now))
    done = threading.Event()

    def poller() -> None:  # the sidebar: GET /recommendation every `poll` seconds until it shows the result
        while not done.is_set():
            view = runtime.recommendation(meeting_id)
            if s.timings and (view["state"] == "ACTIVE" or s.timings[-1]["outcome"] != "RECOMMENDED"):
                done.set()
                return
            time.sleep(poll)

    now = time.time()
    runtime.receive(parse_utterance({"meeting_id": meeting_id, "speaker": "Lead Teste", "text": text,
                                     "timestamp": now, "sequence": 2}, runtime.closer_names, now))
    th = threading.Thread(target=poller, daemon=True)
    th.start()
    if not done.wait(timeout):
        raise TimeoutError(f"{meeting_id}: no result in {timeout}s")
    t = flat(s.timings[-1])
    rec = s.current()
    t["question"] = rec.question if rec else None  # synthetic input: safe to print
    t["shown"] = rec.category if rec else None
    return t


def summarize(rows: list[dict]) -> dict:
    out = {}
    for m in METRICS:
        values = [r[m] for r in rows if isinstance(r.get(m), int | float)]
        if values:
            out[m] = {"median": round(statistics.median(values)), "max": max(values), "n": len(values)}
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--runs", type=int, default=5)
    p.add_argument("--cases", default=",".join(CASES), help=f"comma-separated, from {sorted(CASES)}")
    p.add_argument("--poll", type=float, default=0.5, help="sidebar poll interval (s)")
    p.add_argument("--precision", action="store_true", help="run the PROBE lines once each instead of the cases")
    p.add_argument("--model", default="qwen3:8b")
    p.add_argument("--num-ctx", type=int, default=4096)
    p.add_argument("--reserve-tokens", type=int, default=1024)
    a = p.parse_args(argv)

    ollama = OllamaClassificationProvider(a.model, timeout=120.0, num_ctx=a.num_ctx)
    provider = ContextGuard(ollama, num_ctx=a.num_ctx, reserve_tokens=a.reserve_tokens)
    runtime = Runtime(provider, LiveConfig(), {"Closer Teste"}, log=lambda _s: None)

    t0 = time.time()
    ollama.classify('Return {"ok": true} as JSON.')  # warm-up: load the model; reported, not measured
    print(json.dumps({"warmup_ms": round((time.time() - t0) * 1000),
                      "load_ms": round(ollama.last_usage.get("load_duration", 0) / 1e6)}), flush=True)

    if a.precision:
        rows = []
        for i, (expected, line) in enumerate(PROBE):
            row = {"expected": expected, **run_once(runtime, f"probe-{i}", line, a.poll,
                                                    closer_line="Me conta, o que você achou até aqui?")}
            print(json.dumps({k: row.get(k) for k in ("expected", "category", "shown", "reason",
                              "end_to_end_latency_ms", "question")}, ensure_ascii=False), flush=True)
            rows.append(row)
        objections = [r for r in rows if r["expected"]]
        print(json.dumps({"precision": {
            "shown_correct": f"{sum(r['shown'] == r['expected'] for r in objections)}/{len(objections)}",
            "false_shown": sum(bool(r["shown"]) and r["shown"] != r["expected"] for r in rows),
            **summarize([r for r in rows if r["shown"]])}}, indent=1), flush=True)
        return 0

    results: dict[str, list[dict]] = {}
    for case in a.cases.split(","):
        for i in range(a.runs):
            row = {"case": case, "run": i + 1, **run_once(runtime, f"bench-{case}-{i}", CASES[case], a.poll)}
            print(json.dumps(row, ensure_ascii=False), flush=True)
            results.setdefault(case, []).append(row)
    summary = {case: {"outcomes": sorted({f"{r['outcome']}:{r['reason']}:{r.get('category')}" for r in rows}),
                      **summarize(rows)} for case, rows in results.items()}
    print(json.dumps({"summary": summary}, ensure_ascii=False, indent=1), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
