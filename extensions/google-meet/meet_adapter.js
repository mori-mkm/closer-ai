// AI Closer — Google Meet caption boundary. The ONLY file that knows Meet's DOM.
//
// MeetCaptionAdapter: DOM -> caption blocks {key, speaker, text}. Meet's class names are obfuscated
// and change without notice: every selector lives in SELECTORS, tried in order, with structural
// fallbacks. A speaker that cannot be read is "unknown" — never guessed.
// CaptionTracker: caption blocks over time -> complete LiveUtterances (pure, no DOM; node-testable).

const SELECTORS = {
  // The captions panel. aria-label is localized ("Captions", "Legendas", "Subtítulos").
  region: [
    'div[role="region"][aria-label*="aption" i]',
    'div[role="region"][aria-label*="egenda" i]',
    'div[role="region"][aria-label*="ubtít" i]',
  ],
  block: [".nMcdL", ".TBMuR"], // one caption block per speaker turn
  speaker: [".NWpY1d", ".KcIKyf", ".zs7s8d"],
  text: [".ygicle", ".VbkSUe", ".iTTPOb"],
};

const MeetCaptionAdapter = {
  _ids: new WeakMap(),
  _next: 1,

  region(doc) {
    for (const sel of SELECTORS.region) {
      const el = doc.querySelector(sel);
      if (el) return el;
    }
    return null;
  },

  _first(root, sels) {
    for (const sel of sels) {
      const el = root.querySelector(sel);
      if (el) return el;
    }
    return null;
  },

  _key(el) {
    if (!this._ids.has(el)) this._ids.set(el, this._next++);
    return this._ids.get(el);
  },

  /** Visible caption blocks, oldest first. [] when captions are off or not found. */
  read(doc) {
    const region = this.region(doc);
    if (!region) return [];
    let blocks = [];
    for (const sel of SELECTORS.block) {
      blocks = [...region.querySelectorAll(sel)];
      if (blocks.length) break;
    }
    if (!blocks.length) blocks = [...region.children].filter((c) => c.innerText && c.innerText.trim());
    return blocks.map((b) => {
      const speakerEl = this._first(b, SELECTORS.speaker);
      const textEl = this._first(b, SELECTORS.text);
      const speaker = speakerEl ? speakerEl.innerText.trim() : "";
      let text = textEl ? textEl.innerText : b.innerText;
      if (!textEl && speaker && text.startsWith(speaker)) text = text.slice(speaker.length);
      return { key: this._key(b), speaker: speaker || "unknown", text: text.replace(/\s+/g, " ").trim() };
    }).filter((c) => c.text);
  },
};

const _words = (t) => t.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "")
  .replace(/[^\p{L}\p{N}\s]/gu, "").split(/\s+/).filter(Boolean);

/**
 * Turns the live, self-revising caption blocks into complete utterances.
 * A block's text is emitted once it has been stable for `stableMs`, or when the block disappears.
 * If the block keeps growing afterwards, only the new words are emitted. Identical repeats are dropped.
 */
class CaptionTracker {
  constructor(meetingId, { stableMs = 1500, sequenceBase = Date.now() } = {}) {
    this.meetingId = meetingId;
    this.stableMs = stableMs;
    this.sequence = sequenceBase; // epoch-ms base: stays increasing across page reloads
    this.blocks = new Map(); // key -> {speaker, text, emitted, changedAt}
    this.lastBySpeaker = new Map();
  }

  _emit(b, now, out) {
    const all = _words(b.text);
    const done = _words(b.emitted);
    const grows = done.length && done.every((w, i) => all[i] === w);
    const raw = b.text.split(/\s+/).filter(Boolean);
    const text = (grows ? raw.slice(done.length) : raw).join(" ").trim();
    b.emitted = b.text;
    const norm = _words(text).join(" ");
    if (!norm || (!grows && this.lastBySpeaker.get(b.speaker) === norm)) return;
    this.lastBySpeaker.set(b.speaker, norm);
    out.push({ meeting_id: this.meetingId, speaker: b.speaker, text, timestamp: now, sequence: ++this.sequence,
      changed_at: b.changedAt }); // changed_at: last caption change, for the runtime's latency breakdown
  }

  /** Feed the current blocks; returns the utterances completed by this tick, in order. */
  tick(now, captions) {
    const out = [];
    const seen = new Set();
    for (const c of captions) {
      seen.add(c.key);
      const b = this.blocks.get(c.key);
      if (!b) this.blocks.set(c.key, { speaker: c.speaker, text: c.text, emitted: "", changedAt: now });
      else if (b.text !== c.text || b.speaker !== c.speaker) Object.assign(b, { speaker: c.speaker, text: c.text, changedAt: now });
    }
    for (const [key, b] of this.blocks) {
      const gone = !seen.has(key);
      if (b.text !== b.emitted && (gone || now - b.changedAt >= this.stableMs)) this._emit(b, now, out);
      if (gone) this.blocks.delete(key);
    }
    return out;
  }
}

if (typeof module !== "undefined") module.exports = { MeetCaptionAdapter, CaptionTracker, SELECTORS };
