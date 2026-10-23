"""Live latency benchmark: real Ollama, the real Runtime/LiveSalesSession path, synthetic lines only.

    python -m closer_ai.live.bench --runs 5
    python -m closer_ai.live.bench --runs 10 --cases price --poll 0.5
    python -m closer_ai.live.bench --precision      # 14 probe lines once each: shown right / false shown
    python -m closer_ai.live.bench --sequences      # live sequences: is the NEW lead line the target?
    python -m closer_ai.live.bench --commercial     # Commercial State: facts found / invented, extraction latency
    python -m closer_ai.live.bench --authority      # stakeholder discovery answers vs authority blocking objections
    python -m closer_ai.live.bench --latency --repeat 5 --label A --out runs/A.jsonl   # P1 latency matrix

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
from pathlib import Path
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
                                          ("lead", "Sim, meu sócio.")], None),  # stakeholder fact, not an objection
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


# (name, closer question or None, lead line, expected category or None): invented lines
AUTHORITY_MATRIX = [
    ("discovery: quem participa / meu sócio", "Quem participa da decisão?", "Meu sócio.", None),
    ("discovery: além de você / sim, meu sócio", "Além de você, alguém participa da decisão?", "Sim, meu sócio.", None),
    ("discovery: quem precisa olhar / eu e meu diretor", "Quem precisa olhar essa proposta?", "Eu e meu diretor.", None),
    ("discovery: precisa aprovar? / sim, meu sócio", "Além de você, alguém precisa aprovar?", "Sim, meu sócio.", None),
    ("discovery: quem decide / eu e minha sócia", "E quem decide a compra aí?", "Sou eu e a minha sócia.", None),
    ("discovery: alguém mais / o financeiro também", "Mais alguém participa?", "O financeiro também participa.", None),
    ("blocking: falar com meu sócio antes de fechar", None, "Preciso falar com meu sócio antes de fechar.",
     "AUTHORITY_INTERNAL_BUY_IN"),
    ("blocking: falar com um sócio antes de fechar (Meet)", None, "Preciso falar com um sócio antes de fechar.",
     "AUTHORITY_INTERNAL_BUY_IN"),
    ("blocking: não posso decidir sozinho", None, "Eu gostei, mas não posso decidir isso sozinho.",
     "AUTHORITY_INTERNAL_BUY_IN"),
    ("blocking: diretor precisa aprovar antes", None, "Meu diretor precisa aprovar antes da gente seguir.",
     "AUTHORITY_INTERNAL_BUY_IN"),
    ("blocking: só avanço depois da aprovação", None, "Só consigo avançar depois da aprovação do meu sócio.",
     "AUTHORITY_INTERNAL_BUY_IN"),
    ("blocking: falar com o meu sócio antes (cut)", None, "Preciso falar com o meu sócio antes",
     "AUTHORITY_INTERNAL_BUY_IN"),
]


# Latency matrix (P1): (scenario, kind, lines, expected category or None). Invented lines. Each run is a
# fresh meeting through Runtime.receive (background worker) + the sidebar poller, so `displayed` is real.
LATENCY = [
    ("obvious price", "price", [("closer", CLOSER_LINE), ("lead", "Gostei da proposta, mas achei muito caro.")],
     "PRICE_BUDGET"),
    ("ambiguous price", "price", [("closer", "E o investimento, como ficou para vocês?"),
                                  ("lead", "Esse valor ficou um pouco pesado pra gente.")], "PRICE_BUDGET"),
    ("price reference", "context", [("closer", "E isso cabe no orçamento de vocês?"), ("lead", "Não, ficou acima.")],
     "PRICE_BUDGET"),
    ("negated price", "price", [("closer", "O que achou do valor?"), ("lead", "Não achei caro, o preço está ok.")],
     None),
    ("authority blocker 1", "authority", [("closer", "Faz sentido para vocês?"),
                                          ("lead", "Preciso falar com meu sócio antes de fechar.")],
     "AUTHORITY_INTERNAL_BUY_IN"),
    ("authority blocker 2", "authority", [("closer", "Faz sentido para vocês?"),
                                          ("lead", "Eu gostei, mas não posso decidir isso sozinho.")],
     "AUTHORITY_INTERNAL_BUY_IN"),
    ("authority blocker 3", "authority", [("closer", "Faz sentido para vocês?"),
                                          ("lead", "Meu diretor precisa aprovar antes da gente seguir.")],
     "AUTHORITY_INTERNAL_BUY_IN"),
    ("authority discovery 1", "discovery", [("closer", "Além de você, alguém participa da decisão?"),
                                            ("lead", "Sim, meu sócio.")], None),
    ("authority discovery 2", "discovery", [("closer", "Quem precisa olhar essa proposta?"),
                                            ("lead", "Eu e meu diretor.")], None),
    ("timing", "other", [("closer", "Quando faria sentido começar?"),
                         ("lead", "Agora não é o momento, talvez no próximo trimestre.")], "TIMING_PRIORITY"),
    ("need/value", "other", [("closer", "Faz sentido para vocês?"),
                             ("lead", "Sinceramente não sei se a gente precisa disso.")], "NEED_VALUE_FIT"),
    ("competition", "other", [("closer", "Como vocês fazem isso hoje?"),
                              ("lead", "A gente já usa outra ferramenta que resolve isso.")],
     "COMPETITION_EXISTING_SOLUTION"),
    ("neutral", "neutral", [("closer", CLOSER_LINE), ("lead", "Hoje temos cinco pessoas no time.")], None),
    ("same-turn continuation", "context", [("closer", "O que achou da proposta?"), ("lead", "Eu gostei."),
                                           ("lead", "Mas está acima do que eu consigo investir agora.")],
     "PRICE_BUDGET"),
]
HISTORY = [  # earlier, objection-free call lines (a full rolling window in a real call); invented
    ("closer", "Bom dia! Obrigado por separar esse tempo hoje."), ("lead", "Bom dia, imagina, vamos lá."),
    ("closer", "Me conta um pouco da empresa de vocês."),
    ("lead", "A gente é uma distribuidora de insumos agrícolas, com uns quarenta clientes ativos."),
    ("closer", "E como vocês acompanham os pedidos hoje?"),
    ("lead", "Cada vendedor anota do seu jeito, depois alguém junta tudo numa planilha."),
    ("closer", "Entendi. E isso funciona bem?"), ("lead", "Funciona, mas dá bastante retrabalho no fim do mês."),
    ("closer", "Deixa eu te mostrar como a plataforma organiza isso."), ("lead", "Pode mostrar, por favor."),
]
LATENCY_FIELDS = ("queue_wait_ms", "classifier_latency_ms", "classifier_prompt_tokens", "classifier_output_tokens",
                  "classifier_ollama_load_ms", "classifier_ollama_prompt_eval_ms", "classifier_ollama_eval_ms",
                  "policy_ms", "guidance_latency_ms", "guidance_prompt_tokens", "guidance_output_tokens",
                  "guidance_ollama_load_ms", "guidance_ollama_prompt_eval_ms", "guidance_ollama_eval_ms",
                  "end_to_end_latency_ms", "displayed_latency_ms")


def run_scenario(runtime: Runtime, meeting_id: str, lines: list, poll: float = 0.25, timeout: float = 180.0,
                 history: list | None = None) -> dict:
    """All lines as a live stream (background worker); wait for the last lead line's outcome as the sidebar
    sees it (displayed when a recommendation shows up). `history`: earlier call lines, already seen (context
    only, via rehydrate), as in a real call where each of them was analyzed when it was said."""
    s = runtime.session(meeting_id)
    history = history or []
    if history:
        base = time.time() - 60
        runtime.rehydrate(meeting_id, [{"speaker": "Closer Teste" if role == "closer" else "Lead Teste", "text": text,
                                        "timestamp": base + i, "sequence": i} for i, (role, text) in enumerate(history, 1)])
    last_lead = len(history) + max(i for i, (role, _) in enumerate(lines, 1) if role == "lead")
    for seq, (role, text) in enumerate(lines, len(history) + 1):
        now = time.time()
        runtime.receive(parse_utterance({"meeting_id": meeting_id, "speaker": "Closer Teste" if role == "closer"
                                         else "Lead Teste", "text": text, "timestamp": now, "sequence": seq},
                                        runtime.closer_names, now))
    deadline = time.time() + timeout
    while time.time() < deadline:
        view = runtime.recommendation(meeting_id)  # marks displayed, like the sidebar poll
        done = [t for t in s.timings if t.get("sequence") == last_lead]
        if done and (view["state"] == "ACTIVE" or done[-1]["outcome"] != "RECOMMENDED"):
            break
        if not s.timings and not s.should_analyze() and s.active_analysis is None and s.last_trigger_reason:
            return {"outcome": "NOT_ANALYZED", "reason": s.last_trigger_reason, "shown": None}
        time.sleep(poll)
    else:
        raise TimeoutError(f"{meeting_id}: no result in {timeout}s")
    t = flat(done[-1])
    rec = s.current()
    t["shown"] = rec.category if rec else None
    return t


def pct(values: list[float], q: float) -> float:
    v = sorted(values)
    return v[min(len(v) - 1, round(q * (len(v) - 1)))]


def stats(values: list[float]) -> dict:
    if not values:
        return {}
    out = {"median": round(statistics.median(values)), "min": min(values), "max": max(values), "n": len(values)}
    if len(values) >= 5:
        out["p90"] = pct(values, 0.9)
    return out


def unload_models(base_url: str = "http://127.0.0.1:11434") -> None:
    """Cold start: ask Ollama to unload every loaded model (keep_alive 0)."""
    import urllib.request
    with urllib.request.urlopen(f"{base_url}/api/ps", timeout=10) as r:
        loaded = [m["name"] for m in json.loads(r.read()).get("models", [])]
    for name in loaded:
        body = json.dumps({"model": name, "keep_alive": 0}).encode()
        urllib.request.urlopen(urllib.request.Request(f"{base_url}/api/generate", data=body,
                                                      headers={"Content-Type": "application/json"}), timeout=60).read()


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
    p.add_argument("--authority", action="store_true", help="run the AUTHORITY_MATRIX (discovery vs blocking)")
    p.add_argument("--latency", action="store_true", help="run the LATENCY matrix (per-stage timings + accuracy)")
    p.add_argument("--cold", action="store_true", help="--latency: unload models first; the first run is cold")
    p.add_argument("--label", default="", help="--latency: config label in the output")
    p.add_argument("--out", type=Path, help="--latency: also append every row to this JSONL file")
    p.add_argument("--scenarios", default="", help="--latency: comma-separated scenario names (default: all)")
    p.add_argument("--repeat", type=int, default=1, help="--authority: runs per case")
    p.add_argument("--no-fast-path", action="store_true", help="always use the LLM classifier")
    p.add_argument("--context-turns", type=int, default=0, help="classifier_context_turns (0 = whole window)")
    p.add_argument("--history", type=int, default=0,
                   help="--latency: prefix each scenario with this many earlier (neutral) call lines")
    p.add_argument("--classifier-model", default=None, help="separate classifier model (default: --model)")
    p.add_argument("--classifier-num-ctx", type=int, default=None)
    p.add_argument("--model", default="qwen3:8b")
    p.add_argument("--num-ctx", type=int, default=4096)
    p.add_argument("--reserve-tokens", type=int, default=1024)
    a = p.parse_args(argv)

    ollama = OllamaClassificationProvider(a.model, timeout=120.0, num_ctx=a.num_ctx)
    provider = ContextGuard(ollama, num_ctx=a.num_ctx, reserve_tokens=a.reserve_tokens)
    classifier, c_ollama = None, None
    if a.classifier_model or a.classifier_num_ctx:
        ctx = a.classifier_num_ctx or a.num_ctx
        c_ollama = OllamaClassificationProvider(a.classifier_model or a.model, timeout=120.0, num_ctx=ctx)
        classifier = ContextGuard(c_ollama, num_ctx=ctx, reserve_tokens=min(a.reserve_tokens, ctx // 2))
    runtime = Runtime(provider, LiveConfig(commercial_facts=not a.no_commercial, fast_path=not a.no_fast_path,
                                           classifier_context_turns=a.context_turns),
                      {"Closer Teste"}, log=lambda _s: None, classifier_provider=classifier)

    if a.latency and a.cold:
        unload_models()
    t0 = time.time()
    if not (a.latency and a.cold):
        ollama.classify('Return {"ok": true} as JSON.')  # warm-up: load the model; reported, not measured
        if c_ollama is not None:
            c_ollama.classify('Return {"ok": true} as JSON.')
    print(json.dumps({"warmup_ms": round((time.time() - t0) * 1000),
                      "load_ms": round(ollama.last_usage.get("load_duration", 0) / 1e6)}), flush=True)

    if a.latency:
        rows = []
        chosen = [x for x in LATENCY if not a.scenarios or x[0] in a.scenarios.split(",")]
        for r in range(a.repeat):
            for i, (name, kind, lines, expected) in enumerate(chosen):
                # a different number per run: a real call's window never repeats, so Ollama's prompt cache
                # must not make a repeated run look faster than live
                history = [(role, text.replace("quarenta", str(31 + r * len(chosen) + i)))
                           for role, text in HISTORY[:a.history]]
                t = run_scenario(runtime, f"lat-{a.label}-{i}-{r}-{time.time():.0f}", lines, history=history)
                row = {"label": a.label, "scenario": name, "kind": kind, "run": r + 1,
                       "cold": a.cold and r == 0 and i == 0, "expected": expected, "shown": t.get("shown"),
                       "classifier_category": t.get("category"), "outcome": t.get("outcome"), "reason": t.get("reason"),
                       "classification_source": t.get("classification_source", "llm"),
                       "ok": t.get("shown") == expected, **{k: t.get(k) for k in LATENCY_FIELDS}}
                print(json.dumps(row, ensure_ascii=False), flush=True)
                rows.append(row)
                if a.out:
                    with a.out.open("a", encoding="utf-8") as f:
                        f.write(json.dumps(row, ensure_ascii=False) + "\n")
        warm = [r for r in rows if not r["cold"]]
        pick = lambda key, rs: [r[key] for r in rs if isinstance(r.get(key), int | float)]
        summary = {"label": a.label, "runs": len(rows), "warm_runs": len(warm),
                   "accuracy": f"{sum(r['ok'] for r in rows)}/{len(rows)}",
                   "false_positives": sum(r["shown"] is not None and r["shown"] != r["expected"] for r in rows),
                   "false_negatives": sum(r["shown"] is None and r["expected"] is not None for r in rows),
                   "discovery_fp": sum(r["shown"] is not None for r in rows if r["kind"] == "discovery"),
                   "authority_blockers": f"{sum(r['ok'] for r in rows if r['kind'] == 'authority')}/"
                                         f"{sum(r['kind'] == 'authority' for r in rows)}",
                   "fast_path_hits": sum(r["classification_source"] == "deterministic_fast_path" for r in rows),
                   **{k: stats(pick(k, warm)) for k in LATENCY_FIELDS},
                   "cold": [{k: r.get(k) for k in ("scenario", "classifier_ollama_load_ms", "classifier_latency_ms",
                                                   "displayed_latency_ms")} for r in rows if r["cold"]]}
        print(json.dumps({"latency_summary": summary}, ensure_ascii=False, indent=1), flush=True)
        if a.out:
            with a.out.with_suffix(".summary.json").open("w", encoding="utf-8") as f:
                json.dump(summary, f, ensure_ascii=False, indent=1)
        return 0

    if a.authority:
        rows = []
        for i, (name, question, line, expected) in enumerate(AUTHORITY_MATRIX):
            for r in range(a.repeat):
                mid, base = f"auth-{i}-{r}", time.time() - 60
                lines = ([("closer", question)] if question else [("closer", "Me conta, o que você achou?")]) + [
                    ("lead", line)]
                for seq, (role, text) in enumerate(lines, 1):
                    runtime.receive(parse_utterance({"meeting_id": mid, "speaker": "Closer Teste" if role == "closer"
                                                     else "Lead Teste", "text": text, "timestamp": base + seq * 8,
                                                     "sequence": seq}, runtime.closer_names, base + seq * 8),
                                    background=False)
                s = runtime.sessions[mid]
                t = s.timings[-1] if s.timings else {"outcome": "NOT_ANALYZED", "reason": s.last_trigger_reason}
                shown = t.get("category") if t["outcome"] in ("RECOMMENDED", "KEPT") else None
                rows.append({"case": name, "expected": expected, "shown": shown, "classifier": t.get("category"),
                             "reason": t["reason"],
                             "objections_in_state": [f["value"] for f in s.commercial.view()["objections"]],
                             "ok": shown == expected and bool(expected or not s.commercial.view()["objections"])})
                print(json.dumps(rows[-1], ensure_ascii=False), flush=True)
        disc = [r for r in rows if r["expected"] is None]
        block = [r for r in rows if r["expected"]]
        print(json.dumps({"authority": {
            "discovery_false_positives": f"{sum(not r['ok'] for r in disc)}/{len(disc)}",
            "blocking_shown": f"{sum(r['ok'] for r in block)}/{len(block)}",
        }}, indent=1), flush=True)
        return 0

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
