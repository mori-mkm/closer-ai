// node --test extensions/google-meet/sidebar_view.test.js
const test = require("node:test");
const assert = require("node:assert");
const { dockView, dockReducer, dockChrome, DOCK_INITIAL, TONES, TOAST_MS } = require("./sidebar_view.js");
const { UtteranceDelivery } = require("./delivery.js");

const delivery = new UtteranceDelivery();
for (let i = 1; i <= 5; i++) delivery.add({ sequence: i }, 0);
for (const u of delivery.due(0)) delivery.result(u.sequence, { ok: true, data: { status: "ACCEPTED" } }, 0);
const ctx = { runtimeOk: true, captionsOn: true, meetingId: "abc-defg-hij", counters: { captions_seen: 2 },
  delivery, health: { model_state: "ready" } };
const transcript = [
  { role: "closer", text: "Como vocês fazem esse processo hoje?" },
  { role: "lead", text: "Hoje a gente perde bastante tempo." },
  { role: "closer", text: "Entendi. E como isso impacta vocês?" },
  { role: "lead", text: "Gostei da proposta, mas achei muito caro." },
];
const ready = {
  state: "ACTIVE", id: 1, category: "PRICE_BUDGET", label: "Preço / orçamento", move: "Esclareça antes de responder",
  question: "Caro em relação a quê?", rationale: "O lead disse que achou caro.", grade: "WEAK",
  lead_said: "Gostei da proposta, mas achei muito caro.", objective: "esclarecer antes de responder",
  knowledge_unit: "guidance.PRICE_BUDGET", move_id: "PRICE_BUDGET.M2", move_code: "CLARIFY", grounding: "VALID",
  status: "RECOMMENDATION_READY", active_analysis: null,
  last_completed_analysis: { sequence: 4, segment_id: "seg_4", category: "PRICE_BUDGET", outcome: "RECOMMENDED",
    reason: "GUIDED", finished_at: 1 },
  transcript,
};
const analyzing = { state: "NONE", status: "ANALYZING", transcript,
  active_analysis: { sequence: 4, segment_id: "seg_4", speaker: "Lead Teste", role: "lead",
    text_preview: "Gostei da proposta, mas achei muito caro.", started_at: 1 } };
const detected = { ...analyzing, active_analysis: { ...analyzing.active_analysis,
  detected_category: "PRICE_BUDGET", label: "Preço / orçamento" } };
const withDebug = (data) => ({ ...data, transcript: data.transcript.map((u) => ({ ...u, speaker: u.role === "lead" ? "Lead Teste" : "Você" })),
  debug: { utterances: 4, last_speaker: "Lead Teste", last_role: "lead", recommendation_state: data.state,
    latency: { queue_wait_ms: 1, classifier_latency_ms: 8100, guidance_latency_ms: 5100, end_to_end_latency_ms: 13200 } } });
const TECH = ["PRICE_BUDGET", "guidance.", "PRICE_BUDGET.M2", "WEAK", "VALID", "seg_", "queue_wait_ms",
  "classifier_latency_ms"];

test("dock starts closed: no panel open, no badge, no toast", () => {
  const v = dockView(ready, ctx);
  assert.strictEqual(DOCK_INITIAL.open, null);
  assert.deepStrictEqual(dockChrome(DOCK_INITIAL, dockView({ state: "NONE", status: "CAPTURING" }, ctx), 0),
    { active: false, badge: false, toast: false });
  assert.ok(v.rec); // there is something to open, but nothing is opened for the closer
});

test("opening Sugestão shows the suggestion first in size, the client's words and the objective", () => {
  const v = dockView(ready, ctx);
  const ui = dockReducer(DOCK_INITIAL, { type: "toggle", panel: "suggestion", recId: v.rec.id });
  assert.strictEqual(ui.open, "suggestion");
  assert.deepStrictEqual(v.rec, { id: 1, said: "Gostei da proposta, mas achei muito caro.",
    question: "Caro em relação a quê?", objective: "esclarecer antes de responder", label: "Preço / orçamento" });
  assert.strictEqual(dockReducer(ui, { type: "toggle", panel: "suggestion" }).open, null); // same button closes
});

test("only one panel at a time: opening Histórico closes Sugestão; the dock stays", () => {
  let ui = dockReducer(DOCK_INITIAL, { type: "toggle", panel: "suggestion", recId: 1 });
  ui = dockReducer(ui, { type: "toggle", panel: "history" });
  assert.strictEqual(ui.open, "history");
  ui = dockReducer(ui, { type: "toggle", panel: "advanced" });
  assert.strictEqual(ui.open, "advanced");
  assert.strictEqual(dockReducer(ui, { type: "close" }).open, null); // "–" minimizes back to the dock
});

test("a new ACTIVE recommendation gives a blue badge and a short toast, without opening anything", () => {
  const v = dockView(ready, ctx);
  assert.strictEqual(v.tone, "ready");
  assert.strictEqual(v.color, TONES.ready);
  const ui = dockReducer(DOCK_INITIAL, { type: "data", recId: 1, now: 1000 });
  assert.strictEqual(ui.open, null);
  assert.deepStrictEqual(dockChrome(ui, v, 1000), { active: true, badge: true, toast: true });
  assert.deepStrictEqual(dockChrome(ui, v, 1000 + TOAST_MS), { active: true, badge: true, toast: false });
  // reopening after closing: still ACTIVE (blue), badge gone once seen
  let seen = dockReducer(ui, { type: "toggle", panel: "suggestion", recId: 1 });
  seen = dockReducer(seen, { type: "close" });
  assert.deepStrictEqual(dockChrome(seen, v, 2000), { active: true, badge: false, toast: false });
  assert.strictEqual(dockReducer(seen, { type: "toggle", panel: "suggestion", recId: 1 }).open, "suggestion");
});

test("with Sugestão already open a new recommendation just updates it (no badge, no toast)", () => {
  const ui = dockReducer(dockReducer(DOCK_INITIAL, { type: "toggle", panel: "suggestion" }),
    { type: "data", recId: 2, now: 0 });
  assert.strictEqual(ui.open, "suggestion");
  assert.deepStrictEqual(dockChrome(ui, dockView({ ...ready, id: 2 }, ctx), 0), { active: true, badge: false, toast: false });
});

test("ANALYZING is yellow and shows the lead line, nothing technical", () => {
  const v = dockView(analyzing, ctx);
  assert.deepStrictEqual([v.tone, v.color, v.status], ["analyzing", TONES.analyzing, "Analisando…"]);
  assert.deepStrictEqual(v.analyzing, { text: "Gostei da proposta, mas achei muito caro." });
  assert.strictEqual(v.detected, null);
  assert.strictEqual(dockView({ state: "NONE", status: "CAPTURING", transcript: [] }, ctx).tone, "listening");
  assert.strictEqual(TONES.listening, TONES.analyzing); // listening and analyzing share the yellow
});

test("objection detected before the guidance is red, with the pt-BR label only", () => {
  const v = dockView(detected, ctx);
  assert.deepStrictEqual([v.tone, v.color, v.status], ["objection", TONES.objection, "Objeção detectada"]);
  assert.deepStrictEqual(v.detected, { label: "Preço / orçamento" });
  assert.strictEqual(v.rec, null);
});

test("recommendation ready is blue; neutral states are gray", () => {
  assert.strictEqual(dockView(ready, ctx).tone, "ready");
  assert.strictEqual(dockView(null, { ...ctx, runtimeOk: false }).tone, "idle");
  assert.strictEqual(dockView(null, { ...ctx, runtimeOk: false }).status, "Runtime offline");
  assert.strictEqual(dockView({ state: "NONE", status: "CAPTURING" }, { ...ctx, captionsOn: false }).status,
    "Ative as legendas (CC)");
  assert.strictEqual(dockView({ state: "NONE", status: "ERROR" }, ctx).tone, "idle");
});

test("technical data is hidden by default: nothing technical outside the advanced panel", () => {
  const v = dockView(ready, ctx); // runtime without --debug
  assert.strictEqual(v.advanced.technical, null);
  const visible = JSON.stringify([v.status, v.rec, v.analyzing, v.detected, v.history, v.advanced.basic]);
  for (const t of TECH) assert.ok(!visible.includes(t), t);
  assert.deepStrictEqual(v.advanced.basic, ["Runtime: online · modelo: ready", "Legendas: ligadas",
    "Status: Sugestão pronta"]);
  assert.strictEqual(v.warning, null);
});

test("advanced panel (with --debug) has the technical data; default UI still does not", () => {
  const v = dockView(withDebug(ready), ctx);
  for (const line of ["category: PRICE_BUDGET", "knowledge_unit: guidance.PRICE_BUDGET", "move: CLARIFY (PRICE_BUDGET.M2)",
    "grade: WEAK", "grounding: VALID", "segment: seg_4", "queue_wait_ms: 1", "classifier_latency_ms: 8100",
    "meeting_id: abc-defg-hij", "rationale: O lead disse que achou caro."]) {
    assert.ok(v.advanced.technical.includes(line), line);
  }
  assert.ok(v.advanced.technical.includes("captions_seen: 2 · utterances_created: 5"));
  assert.ok(v.advanced.technical.includes("utterances_sent: 5 · utterances_accepted: 5 · utterances_retried: 0"));
  assert.ok(v.advanced.technical.includes("duplicates_suppressed: 0 · utterances_rejected: 0 · utterances_failed: 0"));
  assert.ok(dockView(withDebug(analyzing), ctx).advanced.technical.includes("active_segment: seg_4"));
  assert.ok(!JSON.stringify(v.rec).includes("PRICE_BUDGET"));
});

test("history: last lines as the runtime received them, closer and lead labeled", () => {
  const v = dockView(ready, ctx);
  assert.deepStrictEqual(v.history.map((l) => `${l.who}: ${l.text}`), [
    "Closer: Como vocês fazem esse processo hoje?", "Lead: Hoje a gente perde bastante tempo.",
    "Closer: Entendi. E como isso impacta vocês?", "Lead: Gostei da proposta, mas achei muito caro."]);
  const many = Array.from({ length: 12 }, (_, i) => ({ role: "lead", text: `fala ${i}` }));
  assert.strictEqual(dockView({ state: "NONE", transcript: many }, ctx).history.length, 8);
  assert.strictEqual(dockView(withDebug(ready), ctx).history[0].who, "Você → closer");
});

test("dismiss closes the panel and removes the highlight once the runtime drops it", () => {
  let ui = dockReducer(DOCK_INITIAL, { type: "toggle", panel: "suggestion", recId: 1 });
  ui = dockReducer(ui, { type: "dismiss", recId: 1 });
  assert.strictEqual(ui.open, null);
  const after = dockView({ state: "NONE", status: "CAPTURING", transcript }, ctx); // runtime: DISMISSED
  assert.deepStrictEqual(dockChrome(ui, after, 0), { active: false, badge: false, toast: false });
  assert.strictEqual(after.history.length, 4); // transcript kept
});

test("expired recommendation: highlight gone, history kept, no stale badge", () => {
  const ui = dockReducer(DOCK_INITIAL, { type: "data", recId: 1, now: 0 }); // badge, never opened
  const expired = dockView({ state: "NONE", status: "CAPTURING", transcript }, ctx); // runtime: EXPIRED
  assert.deepStrictEqual(dockChrome(ui, expired, 100), { active: false, badge: false, toast: false });
  assert.strictEqual(expired.tone, "listening");
  assert.strictEqual(expired.rec, null);
  assert.strictEqual(expired.history.length, 4);
});

test("a lost utterance is reported in the dock (warning) and in the advanced panel, never silently", () => {
  const d = new UtteranceDelivery({ maxAttempts: 1 });
  d.add({ sequence: 9 }, 0);
  for (const u of d.due(0)) d.result(u.sequence, { ok: false, error: "RUNTIME_UNAVAILABLE" }, 0);
  const v = dockView(ready, { ...ctx, delivery: d });
  assert.deepStrictEqual(v.warning, { count: 1, text: "1 fala não entregue ao runtime" });
  assert.ok(v.advanced.basic.includes("Atenção: 1 fala não entregue ao runtime"));
  const tech = dockView(withDebug(ready), { ...ctx, delivery: d }).advanced.technical;
  assert.ok(tech.includes("failed_reasons: RUNTIME_UNAVAILABLE:RETRIES_EXHAUSTED=1"));
});

test("runtime online but model unavailable is its own gray state", () => {
  const v = dockView({ state: "NONE", status: "CAPTURING" }, { ...ctx, health: { model_state: "unavailable" } });
  assert.deepStrictEqual([v.tone, v.status], ["idle", "Modelo indisponível"]);
});
