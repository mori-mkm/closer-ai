"""Live latency benchmark: real Ollama, the real Runtime/LiveSalesSession path, synthetic lines only.

    python -m closer_ai.live.bench --runs 5
    python -m closer_ai.live.bench --runs 10 --cases price --poll 0.5
    python -m closer_ai.live.bench --precision      # 14 probe lines once each: shown right / false shown
    python -m closer_ai.live.bench --sequences      # live sequences: is the NEW lead line the target?
    python -m closer_ai.live.bench --commercial     # Commercial State: facts found / invented, extraction latency
    python -m closer_ai.live.bench --authority      # stakeholder discovery answers vs authority blocking objections
    python -m closer_ai.live.bench --latency --repeat 5 --label A --out runs/A.jsonl   # P1 latency matrix
    python -m closer_ai.live.bench --compliance     # Playbook Compliance growing line by line (one call)
    python -m closer_ai.live.bench --sales-intelligence   # 12 replay scenarios: opportunities, seller action

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
COMPLIANCE_CALL = [  # invented AgroTalento-style call (no client content); Playbook Compliance demo
    ("closer", "Me conta como vocês controlam os custos da fazenda hoje."),
    ("lead", "Hoje é tudo num processo manual, no caderno."),
    ("lead", "Isso faz a equipe perder muito tempo."),
    ("closer", "E quanto tempo vocês perdem com isso?"),
    ("lead", "A gente perde umas 8 horas por semana."),
    ("closer", "Além de você, quem participa da decisão?"),
    ("lead", "Meu sócio."),
    ("lead", "Gostei, mas achei muito caro."),
    ("closer", "Quando você diz caro, está comparando com o quê?"),
    ("closer", "A segunda cadeira é exatamente para o seu sócio."),
    ("closer", "Isso se paga sozinho."),
    ("closer", "Eu te ligo terça às 14h para conversarmos com ele."),
    ("lead", "Fechado, terça às 14h."),
]
# Sales Intelligence replay (invented lines, no client content). expect: final state; checkpoints: (after line n,
# expect). Keys: "ops" {OP id: status} (any other OP = a false opportunity), "rules" {rule: status},
# "seller" "OBJECTION" | "OP-xx" | None, "objection" category or None (real model only: "objection" is
# checked only when `check_objections`).
SALES_SCENARIOS = [
    ("decision_blocker",
     [("closer", "O que você achou da proposta?"), ("lead", "Preciso falar com meu sócio antes de fechar."),
      ("closer", "Vamos marcar com seu sócio terça às 14h?"), ("lead", "Pode ser.")],
     {"ops": {"OP-03": "RESOLVED"}, "rules": {"E6-R2": "SATISFIED"}},
     [(2, {"ops": {"OP-03": "ACTIVE"}, "rules": {"E6-R2": "PENDING"}, "seller": "OBJECTION",
           "objection": "AUTHORITY_INTERNAL_BUY_IN"})]),
    ("discovery_only",
     [("closer", "Além de você, quem participa da decisão?"), ("lead", "Meu sócio.")],
     {"ops": {}, "rules": {"E6-R1": "SATISFIED"}, "seller": None, "objection": None}, []),
    ("think_it_over",
     [("closer", "Esse é o formato do programa."), ("lead", "Vou pensar."),
      ("closer", "O que exatamente você precisa pensar?")],
     {"ops": {"OP-12": "RESOLVED"}, "rules": {"E11-R2": "SATISFIED"}},
     [(2, {"ops": {"OP-12": "ACTIVE"}})]),
    ("buying_signal",
     [("closer", "Esse é o formato do programa."), ("lead", "Posso pagar no cartão da empresa?"),
      ("closer", "Faz sentido a gente seguir então?")],
     {"ops": {"OP-14": "RESOLVED"}, "rules": {"E11-R4": "SATISFIED"}},
     [(2, {"ops": {"OP-14": "ACTIVE"}, "seller": "OP-14"})]),
    ("no_decision_ask",
     [("closer", "Esse é o formato do programa."), ("lead", "Quando eu começo, se eu entrar?"),
      ("closer", "Deixa eu te mostrar os encontros presenciais.")],
     {"ops": {"OP-14": "ACTIVE"}, "rules": {"E11-R4": "PENDING"}, "seller": "OP-14"}, []),
    ("owner_dependency",
     [("closer", "Como funciona a rotina da fazenda?"), ("lead", "Hoje tudo depende de mim na fazenda."),
      ("closer", "Isso é exatamente o pilar Fazenda Autônoma.")],
     {"ops": {"OP-06": "RESOLVED"}}, [(2, {"ops": {"OP-06": "ACTIVE"}, "seller": "OP-06"})]),
    ("financial_visibility",
     [("closer", "Como vocês acompanham os números?"), ("lead", "Eu nem sei minha margem."),
      ("closer", "E qual seria o seu custo por arroba hoje?")],
     {"ops": {"OP-07": "RESOLVED"}}, [(2, {"ops": {"OP-07": "ACTIVE"}})]),
    ("time_concern",
     [("closer", "O que você achou do formato?"), ("lead", "Não tenho tempo para mais um programa."),
      ("closer", "O problema é a agenda dos encontros ou a prioridade neste momento?")],
     {"ops": {"OP-10": "RESOLVED"}}, [(2, {"ops": {"OP-10": "ACTIVE"}})]),
    ("prior_bad_experience",
     [("closer", "Você já participou de algo parecido?"),
      ("lead", "Já fiz duas mentorias e não coloquei nada em prática."),
      ("closer", "O que faltou para colocar em prática?")],
     {"ops": {"OP-11": "RESOLVED"}}, [(2, {"ops": {"OP-11": "ACTIVE"}})]),
    ("multiple_signals",
     [("closer", "O investimento é de 63 mil à vista ou em 12x no cartão."),
      ("lead", "Achei caro e preciso falar com meu sócio."),
      ("lead", "Mas se eu fechar, posso pagar no cartão da empresa?")],
     {"ops": {"OP-03": "ACTIVE", "OP-14": "ACTIVE"}, "seller": "OP-14", "rules": {"E9-R1": "SATISFIED"}}, []),
    ("acceptance",
     [("closer", "Quem participa da decisão?"), ("lead", "Meu sócio."),
      ("lead", "Mas preciso falar com ele antes de fechar."), ("closer", "Vamos marcar com ele terça às 14h."),
      ("lead", "E se eu pagar no cartão da empresa?"), ("closer", "Faz sentido a gente seguir?")],
     {"ops": {"OP-03": "RESOLVED", "OP-14": "RESOLVED"}, "rules": {"E6-R2": "SATISFIED", "E11-R4": "SATISFIED"},
      "seller": None},  # the AUTHORITY card was superseded by OP-03's meeting: it never comes back
     [(2, {"ops": {}, "rules": {"E6-R1": "SATISFIED"}, "seller": None, "objection": None}),
      (3, {"ops": {"OP-03": "ACTIVE"}, "rules": {"E6-R2": "PENDING"}, "objection": "AUTHORITY_INTERNAL_BUY_IN"}),
      (4, {"ops": {"OP-03": "RESOLVED"}, "rules": {"E6-R2": "SATISFIED"}}),
      (5, {"ops": {"OP-03": "RESOLVED", "OP-14": "ACTIVE"}, "seller": "OP-14"})]),
    ("price_then_buying_signal",
     [("closer", "O investimento é de 63 mil."), ("lead", "Achei caro pra gente."),
      ("closer", "Entendo. Caro comparando com o quê?"), ("lead", "Posso pagar no cartão da empresa?"),
      ("closer", "Faz sentido a gente seguir?")],
     {"ops": {"OP-14": "RESOLVED"}, "rules": {"E11-R4": "SATISFIED"}, "seller": None},
     [(2, {"ops": {}, "seller": "OBJECTION", "objection": "PRICE_BUDGET"}),
      (4, {"ops": {"OP-14": "ACTIVE"}, "seller": "OP-14"})]),
    ("price_then_neutral_fact",
     [("closer", "O investimento é de 63 mil."), ("lead", "Achei caro pra gente."),
      ("lead", "Hoje temos cinco pessoas no time.")],
     {"ops": {}, "seller": "OBJECTION", "objection": "PRICE_BUDGET"}, []),
    ("false_positive_guards",
     [("closer", "Quem mais está envolvido?"), ("lead", "Eu e minha esposa."),
      ("lead", "O financeiro também participa."), ("lead", "Isso faz a equipe perder muito tempo."),
      ("lead", "Gostei bastante da apresentação.")],
     {"ops": {}, "seller": None}, []),
]


def sales_snapshot(runtime: Runtime, meeting_id: str) -> dict:
    """What the copilot knows and shows right now (one consistent read)."""
    s = runtime.sessions[meeting_id]
    view = runtime.recommendation(meeting_id)
    ops = view["opportunities"]["opportunities"]
    rec = s.current()
    return {"ops": {o["playbook_op_id"]: o["status"] for o in ops},
            "op_instances": [o["id"] for o in ops],
            "rules": {r["rule_id"]: r["status"] for r in view["playbook_compliance"]["rule_results"]},
            "seller": (None if not view["seller_action"] else "OBJECTION" if view["seller_action"]["source"] == "OBJECTION"
                       else view["seller_action"]["source_id"].split(":")[0]),
            "seller_action": view["seller_action"], "objection": rec.category if rec else None,
            "objections": [f["value"] for f in s.commercial.view()["objections"]],
            "ms": {"compliance": s.compliance_ms, "opportunity": s.opportunity_ms, "arbitration": s.arbitration_ms}}


def sales_check(snap: dict, expect: dict, check_objections: bool) -> list[str]:
    errors = []
    if "ops" in expect:
        for op, status in expect["ops"].items():
            if snap["ops"].get(op) != status:
                errors.append(f"{op}: {snap['ops'].get(op)} != {status}")
        errors += [f"unexpected {op}" for op in snap["ops"] if op not in expect["ops"]]
    errors += [f"{r}: {snap['rules'].get(r)} != {v}" for r, v in expect.get("rules", {}).items()
               if snap["rules"].get(r) != v]
    if "seller" in expect and snap["seller"] != expect["seller"]:
        errors.append(f"seller {snap['seller']} != {expect['seller']}")
    if check_objections and "objection" in expect and snap["objection"] != expect["objection"]:
        errors.append(f"objection {snap['objection']} != {expect['objection']}")
    return errors


def run_sales(runtime: Runtime, name: str, lines: list, expect: dict, checkpoints: list,
              check_objections: bool = True) -> dict:
    """Stream one scenario like the extension (analysis + facts inline), check the checkpoints and the end."""
    mid, base = f"si-{name}-{time.time():.0f}", time.time() - 120
    points = dict(checkpoints)
    trace, errors, conflicts, stale = [], [], 0, 0
    displaced: set[str] = set()  # objection cards an opportunity took over
    last = None
    for seq, (role, text) in enumerate(lines, 1):
        runtime.receive(parse_utterance({"meeting_id": mid, "speaker": "Closer Teste" if role == "closer" else
                                         "Lead Teste", "text": text, "timestamp": base + seq * 8, "sequence": seq},
                                        runtime.closer_names, base + seq * 8), background=False)
        snap = sales_snapshot(runtime, mid)
        sa = snap["seller_action"]
        # a conflict = an opportunity shown over an active objection card without the buying-signal rule
        conflicts += bool(snap["objection"] and sa and sa["source"] == "OPPORTUNITY" and sa["priority"] != 1)
        # stale = an objection card coming back after an opportunity took its place (no dismissals here)
        if last and last["source"] == "OBJECTION" and sa and sa["source"] == "OPPORTUNITY":
            displaced.add(last["source_id"])
        stale += bool(sa and sa["source_id"] in displaced and (not last or last["source_id"] != sa["source_id"]))
        last = sa
        trace.append({"seg": f"seg_{seq}", "role": role, "text": text, "objection": snap["objection"],
                      "ops": snap["ops"], "seller": snap["seller"], "ms": snap["ms"]})
        if seq in points:
            errors += [f"@{seq} {e}" for e in sales_check(snap, points[seq], check_objections)]
    snap = sales_snapshot(runtime, mid)
    errors += sales_check(snap, expect, check_objections)
    brief = runtime.sessions[mid].finalize().to_json()["opportunities"]
    expected_ops = set(expect.get("ops", {})) | {op for _, e in checkpoints for op in e.get("ops", {})}
    per_op: dict[str, int] = {}
    for i in snap["op_instances"]:
        per_op[i.split(":")[0]] = per_op.get(i.split(":")[0], 0) + 1
    return {"scenario": name, "ok": not errors, "errors": errors, "trace": trace,
            "commercial_state": {k: [f["value"] for f in v] for k, v in
                                 runtime.sessions[mid].commercial.view().items() if v},
            "compliance": {r: v for r, v in snap["rules"].items() if v != "PENDING"},
            "opportunities": snap["ops"], "seller_action": snap["seller"], "objections": snap["objections"],
            "missed_at_finalize": [o["playbook_op_id"] for o in brief["missed"]],
            "false_opportunities": sorted(set(snap["ops"]) - expected_ops),
            "missed_opportunities": sorted(op for op in expect.get("ops", {}) if op not in snap["ops"]),
            "duplicates": sum(n - 1 for n in per_op.values()), "seller_conflicts": conflicts,
            "stale_resurfacing": stale, "recommendations_superseded":
                runtime.sessions[mid].counters["recommendations_superseded"]}


def sales_summary(rows: list[dict]) -> dict:
    created = sum(len(r["opportunities"]) for r in rows)
    false = sum(len(r["false_opportunities"]) for r in rows)
    return {"scenarios_ok": f"{sum(r['ok'] for r in rows)}/{len(rows)}",
            "false_opportunities": false, "false_opportunity_rate": round(false / created, 3) if created else 0.0,
            "missed_opportunities": sum(len(r["missed_opportunities"]) for r in rows),
            "duplicate_opportunities": sum(r["duplicates"] for r in rows),
            "seller_action_conflicts": sum(r["seller_conflicts"] for r in rows),
            "stale_recommendation_resurfacing": sum(r["stale_resurfacing"] for r in rows),
            "recommendations_superseded": sum(r["recommendations_superseded"] for r in rows),
            "max_ms": {k: max(t["ms"][k] for r in rows for t in r["trace"])
                       for k in ("compliance", "opportunity", "arbitration")}}


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
    p.add_argument("--compliance", action="store_true", help="stream COMPLIANCE_CALL, print compliance per line")
    p.add_argument("--sales-intelligence", action="store_true",
                   help="replay SALES_SCENARIOS (--scenarios to pick): opportunities, compliance, seller action")
    p.add_argument("--no-commercial", action="store_true", help="disable commercial facts extraction (A/B)")
    p.add_argument("--authority", action="store_true", help="run the AUTHORITY_MATRIX (discovery vs blocking)")
    p.add_argument("--latency", action="store_true", help="run the LATENCY matrix (per-stage timings + accuracy)")
    p.add_argument("--cold", action="store_true", help="--latency: unload models first; the first run is cold")
    p.add_argument("--label", default="", help="--latency: config label in the output")
    p.add_argument("--out", type=Path, help="--latency: also append every row to this JSONL file")
    p.add_argument("--scenarios", default="", help="--latency: comma-separated scenario names (default: all)")
    p.add_argument("--repeat", type=int, default=1, help="--authority: runs per case")
    p.add_argument("--no-fast-path", action="store_true", help="always use the LLM classifier")
    p.add_argument("--history", type=int, default=0,
                   help="--latency: prefix each scenario with this many earlier (neutral) call lines")
    p.add_argument("--model", default="qwen3:8b")
    p.add_argument("--num-ctx", type=int, default=4096)
    p.add_argument("--reserve-tokens", type=int, default=1024)
    a = p.parse_args(argv)

    ollama = OllamaClassificationProvider(a.model, timeout=120.0, num_ctx=a.num_ctx)
    provider = ContextGuard(ollama, num_ctx=a.num_ctx, reserve_tokens=a.reserve_tokens)
    runtime = Runtime(provider, LiveConfig(commercial_facts=not a.no_commercial, fast_path=not a.no_fast_path),
                      {"Closer Teste"}, log=lambda _s: None)

    if a.latency and a.cold:
        unload_models()
    t0 = time.time()
    if not (a.latency and a.cold):
        ollama.classify('Return {"ok": true} as JSON.')  # warm-up: load the model; reported, not measured
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

    if a.sales_intelligence:
        rows = []
        for name, lines, expect, checkpoints in SALES_SCENARIOS:
            if a.scenarios and name not in a.scenarios.split(","):
                continue
            rows.append(run_sales(runtime, name, lines, expect, checkpoints))
            print(json.dumps({k: v for k, v in rows[-1].items() if k != "trace"}, ensure_ascii=False), flush=True)
        print(json.dumps({"sales_intelligence": sales_summary(rows)}, indent=1), flush=True)
        if a.out:
            with a.out.open("a", encoding="utf-8") as f:
                for r in rows:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
        return 0

    if a.compliance:
        mid, base = f"compliance-{time.time():.0f}", time.time() - 120
        for seq, (role, text) in enumerate(COMPLIANCE_CALL, 1):
            runtime.receive(parse_utterance({"meeting_id": mid, "speaker": "Closer Teste" if role == "closer"
                                             else "Lead Teste", "text": text, "timestamp": base + seq * 8,
                                             "sequence": seq}, runtime.closer_names, base + seq * 8),
                            background=False)
            s = runtime.sessions[mid]
            c = s.compliance()
            print(json.dumps({"seg": f"seg_{seq}", "role": role, "text": text,
                              "recommendation": s.current().category if s.current() else None,
                              "rules": {r.rule_id: f"{r.status} {list(r.segment_ids)}" for r in c.rule_results
                                        if not (r.status == "PENDING" and c.rules[r.rule_id].rule_class == "PROHIBITED")},
                              "compliance_ms": s.compliance_ms}, ensure_ascii=False), flush=True)
        print(json.dumps({"commercial_state": runtime.sessions[mid].commercial.view(),
                          "playbook_compliance": runtime.sessions[mid].compliance().view()},
                         ensure_ascii=False, indent=1), flush=True)
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
