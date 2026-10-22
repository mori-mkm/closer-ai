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
