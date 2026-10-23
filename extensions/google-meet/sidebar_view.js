// AI Closer — what the dock shows, as pure functions of the runtime's GET /recommendation answer.
// No DOM, no Meet knowledge, node-testable. Every text comes from the runtime: the history is what
// LiveSalesSession accepted, the suggestion is the runtime's grounded CommercialGuidance view.
//
// dockView(data, ctx)       -> tone + status, suggestion, analyzing/detected line, history, advanced lines
// dockReducer(state, action) -> which panel is open (one at a time), badge and "Nova sugestão" toast

// The four states the closer sees (Meet's dark palette). Nothing else is colored.
const TONES = {
  idle: "#9aa0a6", // gray: offline, captions off, error
  listening: "#fdd663", // yellow: listening
  analyzing: "#fdd663", // yellow: analyzing a lead line
  objection: "#f28b82", // red: objection detected, suggestion not ready yet
  ready: "#8ab4f8", // blue: suggestion ready
};
const ROLE_LABEL = { lead: "Lead", closer: "Closer", unknown: "?" };
const PANELS = ["suggestion", "history", "advanced"];
const TOAST_MS = 4000;
const HISTORY_LINES = 8;
// Commercial State sections, in display order (runtime field -> label). Advanced panel only.
const COMMERCIAL_SECTIONS = [
  ["pain_points", "Pain"], ["impacts", "Impact"], ["stakeholders", "Stakeholders"],
  ["decision_process", "Decision process"], ["buying_signals", "Buying signals"], ["objections", "Objections"],
  ["commercial_terms", "Commercial terms"], ["next_steps", "Next steps"],
];

/** Compact, evidence-cited lines of the runtime's commercial_state (null when the runtime has none). */
function commercialLines(state) {
  if (!state) return null;
  const lines = ["COMMERCIAL STATE"];
  for (const [key, label] of COMMERCIAL_SECTIONS) {
    const facts = state[key] || [];
    lines.push(label);
    if (!facts.length) lines.push("- -");
    for (const f of facts) {
      const role = f.role && f.role !== "mentioned" ? ` (${f.role})` : "";
      lines.push(`- ${f.value}${role} [${(f.segment_ids || []).join(", ")}]`);
    }
  }
  return lines;
}

/**
 * data: the runtime answer (or null when it is unreachable).
 * ctx: { runtimeOk, captionsOn, meetingId, health: {model_state}|null,
 *        counters: {captions_seen}, delivery: UtteranceDelivery (counters, attemptErrors, lostReasons, inFlight) }
 */
function dockView(data, ctx) {
  const d = data || {};
  const debug = Boolean(d.debug);
  const a = d.active_analysis || null;
  const rec = d.state === "ACTIVE"
    ? { id: d.id, said: d.lead_said, question: d.question, objective: d.objective || null, label: d.label }
    : null;
  const analyzing = a ? { text: a.text_preview } : null;
  const detected = a && a.detected_category ? { label: a.label || a.detected_category } : null;

  let tone, status;
  if (!ctx.runtimeOk) [tone, status] = ["idle", "Runtime offline"];
  else if (ctx.health && ctx.health.model_state === "unavailable") [tone, status] = ["idle", "Modelo indisponível"];
  else if (!ctx.captionsOn) [tone, status] = ["idle", "Ative as legendas (CC)"];
  else if (detected) [tone, status] = ["objection", "Objeção detectada"];
  else if (a || d.status === "ANALYZING") [tone, status] = ["analyzing", "Analisando…"];
  else if (rec) [tone, status] = ["ready", "Sugestão pronta"];
  else if (d.status === "ERROR") [tone, status] = ["idle", "Erro na análise"];
  else [tone, status] = ["listening", "Ouvindo"];

  const history = (d.transcript || []).slice(-HISTORY_LINES).map((u) => ({
    who: debug && u.speaker ? `${u.speaker} → ${u.role}` : ROLE_LABEL[u.role] || "?",
    role: u.role,
    text: u.text,
  }));

  // Delivery problems are never silent: a lost utterance shows a small warning in the dock.
  const dl = ctx.delivery || null;
  const lost = dl ? dl.counters.lost : 0;
  const warning = lost
    ? { count: lost, text: `${lost} ${lost === 1 ? "fala não entregue" : "falas não entregues"} ao runtime` }
    : null;

  // Advanced panel: basic status always; technical data only when the runtime runs with --debug.
  const basic = [
    `Runtime: ${ctx.runtimeOk ? "online" : "offline"}${ctx.health ? ` · modelo: ${ctx.health.model_state}` : ""}`,
    `Legendas: ${ctx.captionsOn ? "ligadas" : "desligadas"}`,
    `Status: ${status}`,
  ];
  if (warning) basic.push(`Atenção: ${warning.text}`);
  const commercial = commercialLines(d.commercial_state);
  const brief = d.post_call_brief ? d.post_call_brief.markdown.trimEnd().split("\n") : null; // after finalize
  let technical = null;
  if (debug) {
    const c = ctx.counters;
    const l = d.last_completed_analysis;
    const lat = d.debug.latency || {};
    const k = (dl && dl.counters) || {};
    const rc = d.debug.counters || {};
    const kv = (o) => Object.entries(o).map(([a, b]) => `${a}=${b}`).join(", ") || "-";
    technical = [
      `status: ${d.status || "-"} · recommendation_state: ${d.debug.recommendation_state || "-"}`,
      `runtime_utterances: ${d.debug.utterances ?? "-"} · last: ${d.debug.last_speaker || "-"} → ${d.debug.last_role || "-"}`,
      "", "ENTREGA (extensão)",
      `captions_seen: ${c.captions_seen ?? "-"} · utterances_created: ${k.created ?? "-"}`,
      `utterances_sent: ${k.sent ?? "-"} · utterances_accepted: ${k.confirmed ?? "-"} · utterances_retried: ${k.retried ?? "-"}`,
      `duplicates_suppressed: ${k.duplicates ?? "-"} · utterances_rejected: ${k.rejected ?? "-"} · utterances_failed: ${k.lost ?? "-"}`,
      `in_flight: ${dl ? dl.inFlight : "-"}`,
      `attempt_errors: ${dl ? kv(dl.attemptErrors) : "-"}`,
      `failed_reasons: ${dl ? kv(dl.lostReasons) : "-"}`,
      `recovery: ${ctx.rehydrator ? kv(ctx.rehydrator.counters) : "-"}`,
      "", "RUNTIME",
      `received: ${rc.received ?? "-"} · accepted: ${rc.accepted ?? "-"} · duplicates_suppressed: ${rc.duplicates_suppressed ?? "-"} · rejected: ${rc.rejected ?? "-"} · rehydrated: ${rc.rehydrated ?? "-"}`,
      `analyses_started: ${rc.analyses_started ?? "-"} · analyses_completed: ${rc.analyses_completed ?? "-"} · analysis_errors: ${rc.analysis_errors ?? "-"}`,
      `recommendations_created: ${rc.recommendations_created ?? "-"} · model_state: ${d.debug.model_state || "-"}`,
      `analysis_error_reasons: ${kv(d.debug.analysis_error_reasons || {})}`,
      `commercial: ${kv(d.debug.commercial_counters || {})}`,
    ];
    if (a) technical.push(`active_segment: ${a.segment_id}${a.detected_category ? ` · ${a.detected_category}` : ""}`);
    if (rec) {
      technical.push("", "RECOMENDAÇÃO ATIVA", `category: ${d.category}`, `knowledge_unit: ${d.knowledge_unit}`,
        `move: ${d.move_code || "-"} (${d.move_id})`, `grade: ${d.grade}`, `grounding: ${d.grounding}`,
        `action: ${d.move}`, `rationale: ${d.rationale}`);
    }
    technical.push("", "ÚLTIMA ANÁLISE CONCLUÍDA");
    if (l) {
      technical.push(`category: ${l.category || "-"}`, `outcome: ${l.outcome}`, `reason: ${l.reason}`,
        `segment: ${l.segment_id || "-"}`);
    } else technical.push("(nenhuma ainda)");
    const ms = ["queue_wait_ms", "classifier_latency_ms", "guidance_latency_ms", "end_to_end_latency_ms",
      "displayed_latency_ms"].filter((k) => k in lat).map((k) => `${k}: ${lat[k]}`);
    if (ms.length) technical.push("", "LATÊNCIA (última análise)", ...ms);
    technical.push("", `meeting_id: ${ctx.meetingId}`);
  }

  return { tone, color: TONES[tone], status, rec, analyzing, detected, history, warning, advanced: { basic, commercial, brief, technical } };
}

const DOCK_INITIAL = Object.freeze({ open: null, seenRecId: null, notifiedRecId: null, toastUntil: 0 });

/**
 * UI state of the dock. Actions:
 *  {type: "toggle", panel, recId?}  open that panel (closing any other) or close it if already open
 *  {type: "close"}                  close the open panel (the dock stays)
 *  {type: "data", recId, now}       new runtime answer: a new recommendation gets a badge + a short toast,
 *                                   unless the Suggestion panel is already open (then it just updates)
 *  {type: "dismiss", recId}         the closer dismissed it: close the panel, no badge for it
 */
function dockReducer(state, action) {
  const s = state || DOCK_INITIAL;
  switch (action.type) {
    case "toggle": {
      if (!PANELS.includes(action.panel)) return s;
      const open = s.open === action.panel ? null : action.panel;
      const seen = open === "suggestion" && action.recId != null ? action.recId : s.seenRecId;
      return { ...s, open, seenRecId: seen, toastUntil: open === "suggestion" ? 0 : s.toastUntil };
    }
    case "close":
      return { ...s, open: null };
    case "data": {
      if (action.recId == null || action.recId === s.seenRecId) return s;
      if (s.open === "suggestion") return { ...s, seenRecId: action.recId, notifiedRecId: action.recId };
      if (action.recId === s.notifiedRecId) return s;
      return { ...s, notifiedRecId: action.recId, toastUntil: action.now + TOAST_MS };
    }
    case "dismiss":
      return { ...s, open: s.open === "suggestion" ? null : s.open, seenRecId: action.recId ?? s.seenRecId,
        toastUntil: 0 };
    default:
      return s;
  }
}

/** Dock highlight for this moment: `active` (blue Sugestão button) while a recommendation is ACTIVE;
 * `badge` and `toast` only while the closer has not opened it yet. */
function dockChrome(state, view, now) {
  const active = Boolean(view.rec);
  const unseen = active && view.rec.id !== state.seenRecId;
  return { active, badge: unseen, toast: unseen && now < state.toastUntil };
}

if (typeof module !== "undefined") {
  module.exports = { dockView, dockReducer, dockChrome, commercialLines, DOCK_INITIAL, TONES, TOAST_MS };
}
