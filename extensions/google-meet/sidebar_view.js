// AI Closer — what the sidebar shows, as a pure function of the runtime's GET /recommendation answer.
// No DOM, no Meet knowledge, node-testable. Every text comes from the runtime: the transcript is
// what LiveSalesSession accepted, the recommendation is the runtime's CommercialGuidance view.

const SIDEBAR_STATUS = {
  CAPTURING: { text: "Capturando", color: "#1e8e3e" },
  ANALYZING: { text: "Analisando fala do lead…", color: "#f9ab00" },
  RECOMMENDATION_READY: { text: "Recomendação pronta", color: "#1a73e8" },
  NO_RECOMMENDATION: { text: "Sem objeção para recomendar", color: "#5f6368" },
  ERROR: { text: "Erro na análise", color: "#d93025" },
};
const ROLE_LABEL = { lead: "Lead", closer: "Closer", unknown: "?" };

/**
 * data: the runtime answer (or null when it is unreachable).
 * ctx: { runtimeOk, captionsOn, counters: {captions_seen, utterances_sent, utterances_failed}, meetingId }
 */
function sidebarView(data, ctx) {
  const d = data || {};
  const debug = Boolean(d.debug);
  let status;
  if (!ctx.runtimeOk) status = { ...SIDEBAR_STATUS.ERROR, text: "Runtime offline" };
  else if (!ctx.captionsOn) status = { ...SIDEBAR_STATUS.CAPTURING, text: "Ative as legendas (CC)", color: "#5f6368" };
  else status = SIDEBAR_STATUS[d.status] || SIDEBAR_STATUS.CAPTURING;

  const transcript = (d.transcript || []).map((u) => ({
    who: debug && u.speaker ? `${u.speaker} → ${u.role}` : ROLE_LABEL[u.role] || "?",
    role: u.role,
    text: u.text,
  }));

  // The analysis running NOW (its own utterance), never mixed with the last finished one.
  const a = d.active_analysis;
  const analyzing = a ? { who: ROLE_LABEL[a.role] || "?", text: a.text_preview, segment: a.segment_id } : null;

  const rec = d.state === "ACTIVE"
    ? { id: d.id, category: d.category, label: d.label, move: d.move, question: d.question, rationale: d.rationale }
    : null;

  let debugLines = null;
  if (debug) {
    const c = ctx.counters;
    debugLines = [
      `runtime: ${ctx.runtimeOk ? "online" : "offline"} · status: ${d.status || "-"}`,
      `captions_seen: ${c.captions_seen} · utterances_sent: ${c.utterances_sent} (failed ${c.utterances_failed})`,
      `runtime_utterances: ${d.debug.utterances ?? "-"}`,
      `last: ${d.debug.last_speaker || "-"} → ${d.debug.last_role || "-"}`,
      `recommendation_state: ${d.debug.recommendation_state || "-"}`,
    ];
    if (analyzing) debugLines.push(`active_segment: ${analyzing.segment}`);
    const l = d.last_completed_analysis;
    debugLines.push("", "ÚLTIMA ANÁLISE CONCLUÍDA");
    if (l) {
      debugLines.push(`category: ${l.category || "-"}`, `outcome: ${l.outcome}`, `reason: ${l.reason}`,
        `segment: ${l.segment_id || "-"}`);
    } else debugLines.push("(nenhuma ainda)");
    debugLines.push("");
    if (rec) {
      debugLines.push(
        `knowledge_unit: ${d.knowledge_unit}`,
        `move: ${d.move_code || "-"} (${d.move_id})`,
        `grade: ${d.grade}`,
        `grounding: ${d.grounding}`,
      );
    }
    debugLines.push(`meeting_id: ${ctx.meetingId}`);
  }
  return { status, transcript, analyzing, rec, debugLines };
}

if (typeof module !== "undefined") module.exports = { sidebarView, SIDEBAR_STATUS };
