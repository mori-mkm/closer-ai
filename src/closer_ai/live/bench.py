"""Live latency benchmark: real Ollama, the real Runtime/LiveSalesSession path, synthetic lines only.

    python -m closer_ai.live.bench --runs 5
    python -m closer_ai.live.bench --runs 10 --cases price --poll 0.5
    python -m closer_ai.live.bench --precision      # 14 probe lines once each: shown right / false shown
    python -m closer_ai.live.bench --sequences      # live sequences: is the NEW lead line the target?
    python -m closer_ai.live.bench --commercial     # Commercial State: facts found / invented, extraction latency

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
from typing import Any

from closer_ai.ai.ollama_provider import OllamaClassificationProvider
from closer_ai.demo.analyze_call import ContextGuard
from closer_ai.live.commercial_state import fact_key
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
# Live sequences (invented): each is analyzed line by line as in a call; only the LAST lead line's
# analysis is scored. Expected = the category of the last lead line, None = no objection in it,
# or a set when more than one answer is acceptable.
SEQUENCES: list[tuple[str, list[tuple[str, str]], Any]] = [
    ("price -> authority", [("lead", "Gostei da proposta, mas achei muito caro."),
                            ("lead", "Preciso falar com meu sócio antes de fechar.")], "AUTHORITY_INTERNAL_BUY_IN"),
    ("price -> closer -> authority", [("lead", "Gostei da proposta, mas achei muito caro."),
                                      ("closer", "Entendi, caro em relação a quê?"),
                                      ("lead", "Preciso falar com meu sócio antes de fechar.")],
     "AUTHORITY_INTERNAL_BUY_IN"),
    ("authority -> price", [("lead", "Preciso validar com minha sócia."), ("closer", "Claro, faz sentido."),
                            ("lead", "Mas o principal problema para mim ainda é o preço.")], "PRICE_BUDGET"),
    ("price -> neutral", [("lead", "Está muito caro."), ("closer", "Entendi."),
                          ("lead", "Hoje temos cinco pessoas no time.")], None),
    ("authority -> neutral", [("lead", "Preciso falar com meu sócio antes de fechar."), ("closer", "Combinado."),
                              ("lead", "A operação roda de segunda a sábado.")], None),
    ("neutral -> timing", [("lead", "Hoje temos cinco pessoas no time."), ("closer", "E qual o momento de vocês?"),
                           ("lead", "Agora não é o momento, talvez no próximo trimestre.")], "TIMING_PRIORITY"),
    ("price -> need/value", [("lead", "Achei muito caro."), ("closer", "Entendi."),
                             ("lead", "Sinceramente não sei se a gente precisa disso, nosso volume é muito pequeno.")],
     "NEED_VALUE_FIT"),
    ("price -> competition", [("lead", "Achei muito caro."), ("closer", "Entendi."),
                              ("lead", "Já temos um fornecedor que atende a gente e estamos satisfeitos com ele.")],
     "COMPETITION_EXISTING_SOLUTION"),
    ("same category, stronger", [("lead", "Achei um pouco caro."), ("closer", "Entendi."),
                                 ("lead", "Na verdade não cabe no nosso orçamento de jeito nenhum.")], "PRICE_BUDGET"),
    ("continuation, same turn", [("lead", "Eu gostei."),
                                 ("lead", "Mas está acima do que eu consigo investir agora.")], "PRICE_BUDGET"),
    ("context question -> short answer", [("closer", "Além de você, alguém participa da decisão?"),
                                          ("lead", "Sim, meu sócio.")], {None, "AUTHORITY_INTERNAL_BUY_IN"}),
    ("neutral only", [("lead", "Hoje temos cinco pessoas no time."), ("closer", "Legal."),
                      ("lead", "A gente usa uma planilha compartilhada.")], None),
]

METRICS = ("queue_wait_ms", "classifier_latency_ms", "classifier_ollama_ms", "classifier_output_tokens",
           "policy_ms", "guidance_latency_ms", "guidance_ollama_ms", "guidance_output_tokens",
           "end_to_end_latency_ms", "displayed_latency_ms")


Q_DECISION = ("closer", "Além de você, alguém participa da decisão?")
# (name, lines, expected): expected = field -> needles (folded words a fact's key must contain); fields not
# named must stay empty, except "objections" (the objection engine's, checked only when named).
COMMERCIAL = [
    ("stakeholder", [Q_DECISION, ("lead", "Sim, meu sócio.")], {"stakeholders": ["socio"]}),
    ("pain", [("closer", CLOSER_LINE), ("lead", "Hoje fazemos tudo manualmente.")], {"pain_points": ["manual"]}),
    ("impact", [("closer", "E como isso afeta vocês?"), ("lead", "A equipe perde três horas por dia nisso.")],
     {"impacts": ["tres horas"]}),
    ("buying_signal", [("closer", "Faz sentido para vocês?"), ("lead", "Se funcionar, quero começar ainda este mês.")],
     {"buying_signals": ["comecar"]}),
    ("objection", [("closer", "O que achou?"), ("lead", "Gostei, mas achei muito caro.")],
     {"objections": ["PRICE_BUDGET"]}),
    ("neutral", [("closer", CLOSER_LINE), ("lead", "Hoje temos cinco pessoas no time.")], {}),
    ("next_step", [("closer", "Te mando a proposta e marcamos quinta às 10?"), ("lead", "Fechado, quinta às 10 então.")],
     {"next_steps": ["quinta"]}),
    ("commercial_term", [("closer", "Quanto vocês investem hoje?"),
                         ("lead", "Hoje pagamos uns dois mil por mês na ferramenta atual.")],
     {"commercial_terms": ["dois mil"]}),
    ("dedup", [Q_DECISION, ("lead", "Sim, meu sócio."), ("closer", "Certo."), ("lead", "Preciso validar com meu sócio.")],
     {"stakeholders": ["socio"], "decision_process": ["validar"]}),
    ("role_update", [Q_DECISION, ("lead", "Sim, meu sócio."), ("closer", "E qual o papel dele?"),
                     ("lead", "Ele é quem dá a palavra final.")], {"stakeholders": ["socio"], "roles": ["final_decision_maker"]}),
    ("manual_sequence", [("closer", CLOSER_LINE), ("lead", "É tudo manual."), ("lead", "Isso faz a equipe perder muito tempo."),
                         ("closer", "Quem participa da decisão?"), ("lead", "Meu sócio também."),
                         ("lead", "Gostei, mas achei caro."), ("lead", "Se a gente resolver isso, quero começar este mês.")],
     {"pain_points": ["manual"], "impacts": ["tempo"], "stakeholders": ["socio"], "buying_signals": ["comecar"],
      "objections": ["PRICE_BUDGET"]}),
]


def score_commercial(state: dict, expected: dict) -> dict:
    """Missing expected facts (FN) and facts nobody expected (FP), per field."""
    fn, fp = [], []
    for name, facts in state.items():
        if name == "objections" and name not in expected:
            continue
        needles = expected.get(name, [])
        keys = [fact_key(f["value"]) if name != "objections" else f["value"] for f in facts]
        fn += [f"{name}:{n}" for n in needles if not any(n in k for k in keys)]
        fp += [f"{name}:{k}" for k in keys if not any(n in k for n in needles)]
    roles = [f.get("role") for f in state["stakeholders"]]
    fn += [f"role:{r}" for r in expected.get("roles", []) if r not in roles]
    return {"missing": fn, "invented_or_unexpected": fp}


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
    p.add_argument("--sequences", action="store_true", help="run the live SEQUENCES (latest-utterance anchoring)")
    p.add_argument("--commercial", action="store_true", help="run the COMMERCIAL cases (Commercial State v0)")
    p.add_argument("--no-commercial", action="store_true", help="disable commercial facts extraction (A/B)")
    p.add_argument("--model", default="qwen3:8b")
    p.add_argument("--num-ctx", type=int, default=4096)
    p.add_argument("--reserve-tokens", type=int, default=1024)
    a = p.parse_args(argv)

    ollama = OllamaClassificationProvider(a.model, timeout=120.0, num_ctx=a.num_ctx)
    provider = ContextGuard(ollama, num_ctx=a.num_ctx, reserve_tokens=a.reserve_tokens)
    runtime = Runtime(provider, LiveConfig(commercial_facts=not a.no_commercial), {"Closer Teste"}, log=lambda _s: None)

    t0 = time.time()
    ollama.classify('Return {"ok": true} as JSON.')  # warm-up: load the model; reported, not measured
    print(json.dumps({"warmup_ms": round((time.time() - t0) * 1000),
                      "load_ms": round(ollama.last_usage.get("load_duration", 0) / 1e6)}), flush=True)

    if a.commercial:
        facts_runs: list[dict] = []
        runtime._facts = lambda t: facts_runs.append(t)  # keep each extraction's technical record
        rows = []
        for i, (name, lines, expected) in enumerate(COMMERCIAL):
            mid, base, start = f"commercial-{i}", time.time() - 60, len(facts_runs)
            for seq, (role, text) in enumerate(lines, 1):
                runtime.receive(parse_utterance({"meeting_id": mid, "speaker": "Closer Teste" if role == "closer"
                                                 else "Lead Teste", "text": text, "timestamp": base + seq * 8,
                                                 "sequence": seq}, runtime.closer_names, base + seq * 8),
                                background=False)
            s = runtime.sessions[mid]
            state = s.commercial.view()
            rows.append({"case": name, **score_commercial(state, expected),
                         "state": {k: [f"{f['value']}{'/' + f['role'] if f.get('role') else ''} {f['segment_ids']}"
                                       for f in v] for k, v in state.items() if v},
                         "recommendation": s.current().category if s.current() else None,
                         "rejected": [r for t in facts_runs[start:] for r in t.get("rejected", [])]})
            print(json.dumps(rows[-1], ensure_ascii=False), flush=True)
        lat = [t["latency_ms"] for t in facts_runs if t.get("outcome") in ("EXTRACTED", "ERROR")]
        print(json.dumps({"commercial": {
            "cases_exact": f"{sum(not r['missing'] and not r['invented_or_unexpected'] for r in rows)}/{len(rows)}",
            "missing_facts": sum(len(r["missing"]) for r in rows),
            "unexpected_facts": sum(len(r["invented_or_unexpected"]) for r in rows),
            "extraction_calls": len(lat), "skipped_short": sum(t.get("outcome") == "SKIPPED_SHORT" for t in facts_runs),
            "errors": sum(t.get("outcome") == "ERROR" for t in facts_runs),
            "extraction_ms_median": statistics.median(lat) if lat else None, "extraction_ms_max": max(lat, default=None),
            "lead_lines": sum(r == "lead" for _, ls, _ in COMMERCIAL for r, _ in ls),
        }}, indent=1), flush=True)
        return 0

    if a.sequences:
        rows = []
        for i, (name, lines, expected) in enumerate(SEQUENCES):
            s = runtime.session(f"seq-{i}")
            base = time.time() - 60
            t = None
            for seq, (role, text) in enumerate(lines, 1):
                speaker = "Closer Teste" if role == "closer" else "Lead Teste"
                runtime.receive(parse_utterance({"meeting_id": f"seq-{i}", "speaker": speaker, "text": text,
                                                 "timestamp": base + seq * 8, "sequence": seq},
                                                runtime.closer_names, base + seq * 8), background=False)
                if role == "lead" and s.timings:
                    t = s.timings[-1]
            got = t.get("category") if t and t["outcome"] in ("RECOMMENDED", "KEPT") else None
            ok = got in expected if isinstance(expected, set) else got == expected
            rows.append({"sequence": name, "expected": sorted(map(str, expected)) if isinstance(expected, set)
                         else expected, "got": got, "outcome": f"{t['outcome']}:{t['reason']}" if t else None,
                         "classifier_category": t.get("category") if t else None, "ok": ok})
            print(json.dumps(rows[-1], ensure_ascii=False), flush=True)
        objs = [r for r, (_, _, e) in zip(rows, SEQUENCES, strict=True) if e and not isinstance(e, set)]
        print(json.dumps({"sequences": {
            "correct": f"{sum(r['ok'] for r in rows)}/{len(rows)}",
            "false_positives": sum(r["got"] is not None and not r["ok"] and r["expected"] is None for r in rows),
            "wrong_category": sum(r["got"] is not None and not r["ok"] and r["expected"] is not None for r in rows),
            "false_negatives": sum(r["got"] is None and not r["ok"] for r in objs),
            "no_qualifying_episode": sum(str(r["outcome"]).endswith("NO_QUALIFYING_EPISODE") for r in rows),
        }}, indent=1), flush=True)
        return 0

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
