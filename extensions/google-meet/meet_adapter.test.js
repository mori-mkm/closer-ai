// node --test extensions/google-meet/
const test = require("node:test");
const assert = require("node:assert");
const { CaptionTracker } = require("./meet_adapter.js");

const tracker = () => new CaptionTracker("abc-defg-hij", { stableMs: 1000, sequenceBase: 0 });
const cap = (key, speaker, text) => ({ key, speaker, text });

test("partial captions are consolidated into one utterance once stable", () => {
  const t = tracker();
  assert.deepStrictEqual(t.tick(0, [cap(1, "Ana", "Gostei")]), []);
  assert.deepStrictEqual(t.tick(300, [cap(1, "Ana", "Gostei da proposta, mas")]), []);
  assert.deepStrictEqual(t.tick(600, [cap(1, "Ana", "Gostei da proposta, mas achei caro.")]), []);
  const out = t.tick(1700, [cap(1, "Ana", "Gostei da proposta, mas achei caro.")]);
  assert.strictEqual(out.length, 1);
  assert.deepStrictEqual(out[0], { meeting_id: "abc-defg-hij", speaker: "Ana", text: "Gostei da proposta, mas achei caro.",
    timestamp: 1700, sequence: 1, changed_at: 600 }); // stable for 1.1 s after the last change
});

test("the same caption is never emitted twice", () => {
  const t = tracker();
  t.tick(0, [cap(1, "Ana", "Preciso falar com meu sócio.")]);
  assert.strictEqual(t.tick(1000, [cap(1, "Ana", "Preciso falar com meu sócio.")]).length, 1);
  assert.strictEqual(t.tick(5000, [cap(1, "Ana", "Preciso falar com meu sócio.")]).length, 0);
  // Meet re-renders the same line in a new block: still not repeated
  assert.strictEqual(t.tick(6000, [cap(2, "Ana", "Preciso falar com meu sócio")]).length, 0);
  assert.strictEqual(t.tick(7000, []).length, 0);
});

test("a block that keeps growing emits only the new words", () => {
  const t = tracker();
  t.tick(0, [cap(1, "Ana", "Gostei da proposta.")]);
  t.tick(1000, [cap(1, "Ana", "Gostei da proposta.")]);
  t.tick(1200, [cap(1, "Ana", "Gostei da proposta. Mas achei caro.")]);
  const out = t.tick(2300, [cap(1, "Ana", "Gostei da proposta. Mas achei caro.")]);
  assert.deepStrictEqual(out.map((u) => u.text), ["Mas achei caro."]);
});

test("a block that disappears is flushed; order and sequence are kept", () => {
  const t = tracker();
  t.tick(0, [cap(1, "Matheus", "Como vocês fazem hoje?"), cap(2, "Ana", "Na planilha")]);
  const out = t.tick(200, [cap(2, "Ana", "Na planilha")]);
  assert.deepStrictEqual(out.map((u) => [u.speaker, u.sequence]), [["Matheus", 1]]);
  const later = t.tick(1300, [cap(2, "Ana", "Na planilha")]);
  assert.deepStrictEqual(later.map((u) => [u.speaker, u.text, u.sequence]), [["Ana", "Na planilha", 2]]);
});

test("unknown speaker is passed through, not guessed", () => {
  const t = tracker();
  t.tick(0, [cap(1, "unknown", "Tá caro")]);
  assert.strictEqual(t.tick(1000, [cap(1, "unknown", "Tá caro")])[0].speaker, "unknown");
});

// --- delivery contract (delivery.js): captured -> sent -> confirmed | duplicate | rejected | lost ---------
const { UtteranceDelivery, Rehydrator, classifyReply } = require("./delivery.js");
const OK = (status) => ({ ok: true, status: 200, data: { accepted: status === "ACCEPTED", status } });
const DOWN = { ok: false, error: "RUNTIME_UNAVAILABLE" };
const terminal = (d) => d.counters.confirmed + d.counters.duplicates + d.counters.rejected + d.counters.lost;

test("failures are classified, not lumped together", () => {
  assert.strictEqual(classifyReply(OK("ACCEPTED")).kind, "ACCEPTED");
  assert.strictEqual(classifyReply(OK("DUPLICATE_SEQUENCE")).kind, "DUPLICATE");
  assert.strictEqual(classifyReply(OK("DUPLICATE_TEXT")).kind, "DUPLICATE");
  assert.strictEqual(classifyReply(DOWN).kind, "RUNTIME_UNAVAILABLE");
  assert.strictEqual(classifyReply({ ok: false, error: "HTTP_TIMEOUT" }).kind, "HTTP_TIMEOUT");
  assert.strictEqual(classifyReply({ ok: false, error: "INVALID_RESPONSE", status: 200 }).kind, "INVALID_RESPONSE");
  assert.deepStrictEqual(classifyReply({ ok: false, error: "HTTP_ERROR", status: 400 }), { kind: "REJECTED", detail: "HTTP_400" });
  assert.deepStrictEqual(classifyReply({ ok: false, error: "HTTP_ERROR", status: 503 }), { kind: "HTTP_5XX", detail: 503 });
  assert.strictEqual(classifyReply(undefined).kind, "EXTENSION_UNAVAILABLE");
  assert.strictEqual(classifyReply({ ok: false, error: "EXTENSION_CONTEXT_INVALIDATED" }).kind, "EXTENSION_CONTEXT_INVALIDATED");
});

test("runtime briefly down: retried with the same id and backoff, then confirmed once", () => {
  const d = new UtteranceDelivery();
  d.add({ sequence: 7, text: "Gostei da proposta, mas achei muito caro." }, 0);
  const sent = [];
  const step = (now, reply) => { for (const u of d.due(now)) { sent.push(u.sequence); d.result(u.sequence, reply, now); } };
  step(0, DOWN); // attempt 1
  step(100, DOWN); // not due yet (backoff 500 ms)
  step(500, DOWN); // attempt 2
  step(1500, OK("DUPLICATE_SEQUENCE")); // attempt 3: the runtime had it after all (lost reply) -> no duplicate
  assert.deepStrictEqual(sent, [7, 7, 7]);
  assert.deepStrictEqual(d.counters, { created: 1, sent: 3, confirmed: 0, retried: 2, duplicates: 1, rejected: 0, lost: 0 });
  assert.deepStrictEqual(d.attemptErrors, { RUNTIME_UNAVAILABLE: 2 });
  assert.strictEqual(d.inFlight, 0);
});

test("bounded: retries exhausted, too old or queue overflow end as LOST with a reason", () => {
  const d = new UtteranceDelivery({ maxAttempts: 2, backoffMs: [500], maxAgeMs: 3000, maxPending: 2 });
  d.add({ sequence: 1 }, 0);
  for (const u of d.due(0)) d.result(u.sequence, DOWN, 0);
  for (const u of d.due(500)) d.result(u.sequence, DOWN, 500);
  assert.deepStrictEqual(d.lostReasons, { "RUNTIME_UNAVAILABLE:RETRIES_EXHAUSTED": 1 });
  d.add({ sequence: 2 }, 1000);
  for (const u of d.due(1000)) d.result(u.sequence, { ok: false, error: "HTTP_TIMEOUT" }, 1000);
  assert.deepStrictEqual(d.due(5000), []); // older than maxAgeMs: dropped instead of retried
  assert.strictEqual(d.lostReasons.TOO_OLD, 1);
  for (const s of [3, 4, 5]) d.add({ sequence: s }, 6000); // maxPending 2: the oldest goes
  assert.strictEqual(d.lostReasons.QUEUE_OVERFLOW, 1);
  assert.deepStrictEqual([...d.pending.keys()], [4, 5]);
  assert.strictEqual(d.counters.lost, 3);
});

test("a newer utterance is never held back by an older one being retried", () => {
  const d = new UtteranceDelivery();
  d.add({ sequence: 1 }, 0);
  for (const u of d.due(0)) d.result(u.sequence, DOWN, 0); // 1 waits for its retry
  d.add({ sequence: 2 }, 100);
  assert.deepStrictEqual(d.due(100).map((u) => u.sequence), [2]); // sent right away
});

test("rejected and invalidated are terminal and counted; nothing ends silently", () => {
  const d = new UtteranceDelivery();
  for (const s of [1, 2, 3, 4]) d.add({ sequence: s }, 0);
  const replies = { 1: OK("ACCEPTED"), 2: { ok: false, error: "HTTP_ERROR", status: 400 },
    3: { ok: false, error: "EXTENSION_CONTEXT_INVALIDATED" }, 4: OK("DUPLICATE_TEXT") };
  for (const u of d.due(0)) d.result(u.sequence, replies[u.sequence], 0);
  assert.deepStrictEqual(d.counters, { created: 4, sent: 4, confirmed: 1, retried: 0, duplicates: 1, rejected: 1, lost: 1 });
  assert.deepStrictEqual(d.lostReasons, { EXTENSION_CONTEXT_INVALIDATED: 1 });
  assert.strictEqual(terminal(d) + d.inFlight, d.counters.created); // conservation: every utterance accounted for
});

// --- session recovery: what the runtime held, given back once after a restart ------------------------
test("the recovery buffer holds exactly what the runtime has, in sequence order", () => {
  const d = new UtteranceDelivery();
  for (const s of [3, 1, 2, 4]) d.add({ sequence: s, text: `fala ${s}` }, 0);
  const replies = { 1: OK("ACCEPTED"), 2: OK("DUPLICATE_SEQUENCE"), 3: OK("ACCEPTED"), 4: OK("DUPLICATE_TEXT") };
  for (const u of d.due(0)) d.result(u.sequence, replies[u.sequence], 0);
  // 2 was a retry the runtime already had; 4 was dropped by the runtime (same caption repeated)
  assert.deepStrictEqual(d.heldUtterances().map((u) => u.sequence), [1, 2, 3]);
  const lost = new UtteranceDelivery({ maxAttempts: 1 });
  lost.add({ sequence: 9 }, 0);
  for (const u of lost.due(0)) lost.result(u.sequence, DOWN, 0);
  assert.deepStrictEqual(lost.heldUtterances(), []); // never confirmed: not "held"
});

test("a runtime restart (new instance) triggers exactly one rehydration; same instance never does", () => {
  const r = new Rehydrator();
  r.observe("a1");
  r.observe("a1");
  assert.strictEqual(r.due(), false); // first contact or same runtime: nothing to restore
  r.observe("b2"); // restarted
  assert.strictEqual(r.due(), true);
  assert.strictEqual(r.due(), false); // one at a time
  r.result({ ok: false, error: "RUNTIME_UNAVAILABLE" }); // failed: retried at the next poll
  assert.strictEqual(r.due(), true);
  r.result({ ok: true, data: { rehydrated: 3, utterances: 3, instance: "b2" } });
  r.observe("b2");
  assert.strictEqual(r.due(), false);
  assert.deepStrictEqual(r.counters, { restarts_seen: 1, rehydrations: 1, utterances_rehydrated: 3, failures: 1 });
});
