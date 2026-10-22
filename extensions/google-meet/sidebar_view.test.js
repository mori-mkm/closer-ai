// node --test extensions/google-meet/sidebar_view.test.js
const test = require("node:test");
const assert = require("node:assert");
const { sidebarView } = require("./sidebar_view.js");

const ctx = { runtimeOk: true, captionsOn: true, meetingId: "abc-defg-hij",
  counters: { captions_seen: 2, utterances_sent: 2, utterances_failed: 0 } };
const ready = {
  state: "ACTIVE", id: 1, category: "PRICE_BUDGET", label: "Preço / orçamento", move: "Esclareça antes de responder",
  question: "Caro em relação a quê?", rationale: "O lead disse que achou caro.", grade: "WEAK",
  knowledge_unit: "guidance.PRICE_BUDGET", move_id: "PRICE_BUDGET.M2", move_code: "CLARIFY", grounding: "VALID",
  status: "RECOMMENDATION_READY",
  transcript: [{ role: "closer", text: "Entendi." }, { role: "lead", text: "Gostei da proposta, mas achei muito caro." }],
};

test("transcript and recommendation are exactly what the runtime sent", () => {
  const v = sidebarView(ready, ctx);
  assert.deepStrictEqual(v.transcript.map((l) => `${l.who}: ${l.text}`),
    ["Closer: Entendi.", "Lead: Gostei da proposta, mas achei muito caro."]);
  assert.strictEqual(v.rec.category, "PRICE_BUDGET");
  assert.strictEqual(v.rec.question, "Caro em relação a quê?");
  assert.strictEqual(v.status.text, "Recomendação pronta");
  assert.strictEqual(v.debugLines, null); // not in debug mode
});

test("no active recommendation and no transcript -> nothing invented", () => {
  const v = sidebarView({ state: "NONE", status: "CAPTURING", transcript: [] }, ctx);
  assert.strictEqual(v.rec, null);
  assert.deepStrictEqual(v.transcript, []);
  assert.strictEqual(v.status.text, "Capturando");
});

test("states: analyzing, no recommendation, error, offline, captions off", () => {
  const text = (data, c = ctx) => sidebarView(data, c).status.text;
  assert.strictEqual(text({ state: "NONE", status: "ANALYZING" }), "Analisando fala do lead…");
  assert.strictEqual(text({ state: "NONE", status: "NO_RECOMMENDATION" }), "Sem objeção para recomendar");
  assert.strictEqual(text({ state: "NONE", status: "ERROR" }), "Erro na análise");
  assert.strictEqual(text(null, { ...ctx, runtimeOk: false }), "Runtime offline");
  assert.strictEqual(text({ state: "NONE", status: "CAPTURING" }, { ...ctx, captionsOn: false }), "Ative as legendas (CC)");
});

test("debug shows raw speaker -> role and the retrieval provenance", () => {
  const data = { ...ready, transcript: [{ role: "lead", speaker: "Matheus Mori", text: "Achei caro." }],
    debug: { utterances: 1, last_speaker: "Matheus Mori", last_role: "lead", recommendation_state: "ACTIVE" } };
  const v = sidebarView(data, ctx);
  assert.strictEqual(v.transcript[0].who, "Matheus Mori → lead");
  for (const line of ["knowledge_unit: guidance.PRICE_BUDGET", "move: CLARIFY (PRICE_BUDGET.M2)", "grade: WEAK",
    "grounding: VALID"]) assert.ok(v.debugLines.includes(line), line);
});

test("the analysis running now and the last finished one are shown separately", () => {
  const data = {
    state: "NONE", status: "ANALYZING", transcript: [],
    active_analysis: { sequence: 4, segment_id: "seg_4", speaker: "Lead Teste", role: "lead",
      text_preview: "Gostei da proposta, mas achei muito caro.", started_at: 1 },
    last_completed_analysis: { sequence: 2, segment_id: "seg_2", category: "IMPLEMENTATION_INTEGRATION",
      outcome: "NO_RECOMMENDATION", reason: "UNCORROBORATED_CATEGORY", finished_at: 1 },
    debug: { utterances: 4, last_speaker: "Lead Teste", last_role: "lead", recommendation_state: "NONE" },
  };
  const v = sidebarView(data, ctx);
  assert.deepStrictEqual(v.analyzing, { who: "Lead", text: "Gostei da proposta, mas achei muito caro.", segment: "seg_4" });
  assert.ok(v.debugLines.includes("active_segment: seg_4"));
  const i = v.debugLines.indexOf("ÚLTIMA ANÁLISE CONCLUÍDA");
  assert.deepStrictEqual(v.debugLines.slice(i + 1, i + 5), ["category: IMPLEMENTATION_INTEGRATION",
    "outcome: NO_RECOMMENDATION", "reason: UNCORROBORATED_CATEGORY", "segment: seg_2"]);
  assert.strictEqual(sidebarView({ ...data, active_analysis: null }, ctx).analyzing, null);
});
