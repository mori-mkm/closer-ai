// AI Closer — utterance delivery to the runtime (pure, node-testable; time is passed in).
//
// Contract: every utterance the tracker creates has a unique id (its `sequence`) and ends in exactly
// one terminal state, never silently:
//   CONFIRMED  runtime answered ACCEPTED
//   DUPLICATE  runtime answered DUPLICATE_SEQUENCE (a retry of something it already has) or
//              DUPLICATE_TEXT (the same caption repeated by the same speaker): delivered, not added twice
//   REJECTED   runtime refused it (HTTP 4xx, EMPTY): not retried
//   LOST       could not be delivered: retries exhausted, too old, queue overflow, or the extension
//              was reloaded under this tab. Counted by reason and shown to the closer.
// Retryable attempt errors (RUNTIME_UNAVAILABLE, HTTP_TIMEOUT, HTTP 5xx, INVALID_RESPONSE,
// EXTENSION_UNAVAILABLE) are retried with the SAME id, so the runtime's idempotency (sequence) makes a
// retry harmless. Retries are bounded (attempts, age, queue size): an old line never holds back a new
// one, because each utterance is sent independently and the runtime only analyzes the newest lead line.

const RETRYABLE = new Set(["RUNTIME_UNAVAILABLE", "HTTP_TIMEOUT", "INVALID_RESPONSE", "EXTENSION_UNAVAILABLE"]);

/** Classify one reply of background.js (or of sendMessage itself) into a delivery outcome. */
function classifyReply(r) {
  if (!r) return { kind: "EXTENSION_UNAVAILABLE" };
  if (r.error === "EXTENSION_CONTEXT_INVALIDATED") return { kind: "EXTENSION_CONTEXT_INVALIDATED" };
  if (r.ok) {
    const status = r.data && r.data.status;
    if (status === "ACCEPTED") return { kind: "ACCEPTED" };
    if (status === "DUPLICATE_SEQUENCE" || status === "DUPLICATE_TEXT") return { kind: "DUPLICATE", detail: status };
    if (status === "EMPTY") return { kind: "REJECTED", detail: status };
    // older runtime without "status": trust "accepted"
    if (r.data && r.data.accepted === true) return { kind: "ACCEPTED" };
    if (r.data && r.data.accepted === false) return { kind: "DUPLICATE", detail: "NOT_ACCEPTED" };
    return { kind: "INVALID_RESPONSE" };
  }
  if (r.error === "HTTP_ERROR") return r.status >= 500 ? { kind: "HTTP_5XX", detail: r.status } : { kind: "REJECTED", detail: `HTTP_${r.status}` };
  return { kind: r.error || "EXTENSION_UNAVAILABLE" };
}

const MAX_DELIVERED = 1000; // recovery buffer: the utterances the runtime holds for this tab's meeting

class UtteranceDelivery {
  constructor({ maxAttempts = 4, backoffMs = [500, 1000, 2000], maxAgeMs = 10000, maxPending = 20 } = {}) {
    Object.assign(this, { maxAttempts, backoffMs, maxAgeMs, maxPending });
    // What the runtime holds (ACCEPTED, or DUPLICATE_SEQUENCE = it already had it), kept in this tab only
    // while the meeting is open, to rebuild the runtime's session after a restart (see Rehydrator).
    this.delivered = new Map(); // sequence -> utterance
    this.pending = new Map(); // id -> {u, attempts, createdAt, nextAt, inflight}
    this.counters = { created: 0, sent: 0, confirmed: 0, retried: 0, duplicates: 0, rejected: 0, lost: 0 };
    this.attemptErrors = {}; // reason -> count, per failed attempt
    this.lostReasons = {}; // reason -> count, per utterance lost
    this.lastProblem = null; // {reason, at}: the latest attempt error or loss, for the closer
  }

  /** A complete utterance from the tracker. */
  add(u, now) {
    this.counters.created++;
    this.pending.set(u.sequence, { u, attempts: 0, createdAt: now, nextAt: now, inflight: false });
    while (this.pending.size > this.maxPending) {
      const [oldest] = this.pending.keys();
      this._lose(oldest, "QUEUE_OVERFLOW", now);
    }
  }

  /** Utterances to send now (first attempts and due retries); marks them in flight. */
  due(now) {
    const out = [];
    for (const [id, p] of this.pending) {
      if (p.inflight || p.nextAt > now) continue;
      if (now - p.createdAt > this.maxAgeMs) { this._lose(id, "TOO_OLD", now); continue; }
      p.inflight = true;
      p.attempts++;
      this.counters.sent++;
      if (p.attempts > 1) this.counters.retried++;
      out.push(p.u);
    }
    return out;
  }

  /** The reply to one attempt of utterance `id`. */
  result(id, reply, now) {
    const p = this.pending.get(id);
    if (!p) return null; // already terminal (e.g. lost by age while in flight)
    const o = classifyReply(reply);
    if (o.kind === "ACCEPTED") { this.counters.confirmed++; this._held(p.u); this.pending.delete(id); return "CONFIRMED"; }
    if (o.kind === "DUPLICATE") {
      this.counters.duplicates++;
      if (o.detail === "DUPLICATE_SEQUENCE") this._held(p.u); // the runtime has it (a retry); DUPLICATE_TEXT: dropped
      this.pending.delete(id);
      return "DUPLICATE";
    }
    const reason = o.kind === "HTTP_5XX" ? `HTTP_${o.detail}` : o.detail ? `${o.kind}:${o.detail}` : o.kind;
    this.attemptErrors[reason] = (this.attemptErrors[reason] || 0) + 1;
    this.lastProblem = { reason, at: now };
    if (o.kind === "REJECTED") { this.counters.rejected++; this.pending.delete(id); return "REJECTED"; }
    if (o.kind === "EXTENSION_CONTEXT_INVALIDATED") return this._lose(id, o.kind, now);
    if (!RETRYABLE.has(o.kind) && o.kind !== "HTTP_5XX") return this._lose(id, reason, now);
    if (p.attempts >= this.maxAttempts) return this._lose(id, `${reason}:RETRIES_EXHAUSTED`, now);
    p.inflight = false;
    p.nextAt = now + this.backoffMs[Math.min(p.attempts - 1, this.backoffMs.length - 1)];
    return "RETRY";
  }

  _held(u) {
    this.delivered.set(u.sequence, u);
    if (this.delivered.size > MAX_DELIVERED) this.delivered.delete(this.delivered.keys().next().value);
  }

  /** The utterances the runtime held, in sequence order (what a restarted runtime is given back). */
  heldUtterances() {
    return [...this.delivered.values()].sort((a, b) => a.sequence - b.sequence);
  }

  _lose(id, reason, now) {
    this.pending.delete(id);
    this.counters.lost++;
    this.lostReasons[reason] = (this.lostReasons[reason] || 0) + 1;
    this.lastProblem = { reason, at: now };
    return "LOST";
  }

  /** Utterances created but not yet terminal. */
  get inFlight() { return this.pending.size; }
}

/**
 * Detects a runtime restart (its `instance` id changes) and asks for one rehydration of this meeting.
 * A restarted runtime has no sessions; the extension sends back what it had (POST /rehydrate), which the
 * runtime adds as context only: no analysis, no recommendation, not counted as live delivery.
 */
class Rehydrator {
  constructor() {
    this.instance = null; // last runtime instance seen
    this.needed = false;
    this.inFlight = false;
    this.counters = { restarts_seen: 0, rehydrations: 0, utterances_rehydrated: 0, failures: 0 };
  }

  /** Every runtime answer that carries `instance`. */
  observe(instance) {
    if (!instance) return;
    if (this.instance && instance !== this.instance) { this.needed = true; this.counters.restarts_seen++; }
    this.instance = instance;
  }

  /** True when a rehydration should be sent now (one at a time). */
  due() {
    if (!this.needed || this.inFlight) return false;
    this.inFlight = true;
    return true;
  }

  /** Outcome of POST /rehydrate; a failure keeps it pending for the next poll. */
  result(reply) {
    this.inFlight = false;
    if (reply && reply.ok) {
      this.needed = false;
      this.counters.rehydrations++;
      this.counters.utterances_rehydrated += (reply.data && reply.data.rehydrated) || 0;
      if (reply.data && reply.data.instance) this.instance = reply.data.instance;
    } else this.counters.failures++;
  }
}

if (typeof module !== "undefined") module.exports = { UtteranceDelivery, Rehydrator, classifyReply };
