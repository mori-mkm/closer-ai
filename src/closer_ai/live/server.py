"""Local runtime for the Live Meet Copilot v0 (stdlib HTTP, loopback only) + synthetic stream replay.

    python -m closer_ai.live.server --closer "Matheus"           # serve 127.0.0.1:8765 for the extension
    python -m closer_ai.live.server --replay examples/live/smoke_price.txt --delay 2   # no Meet needed

Endpoints (the Chrome extension's background worker is the only intended client):
- POST /live-utterance  {"meeting_id", "speaker", "text", "timestamp", "sequence"}
                        -> {"accepted", "status", "id", "role"}; idempotent per (meeting_id, sequence): a retry
                           of an utterance already received answers status DUPLICATE_SEQUENCE
- GET  /recommendation?meeting_id=...                                  -> the current one or {"state": "NONE"}
- POST /dismiss         {"meeting_id"}
- POST /rehydrate       {"meeting_id", "utterances": [...]} -> {"rehydrated", "utterances"}: after a runtime
                        restart the extension sends back what this meeting already had (context only)
- POST /finalize        {"meeting_id"} -> {"brief": {...}, "markdown": "..."}: end of call, the Post-call
                        Brief built from the meeting's CommercialState; idempotent (the same brief again)
- GET  /health          -> {"status", "runtime", "model", "model_state", "instance"} (no call data)

Every request needs the header `X-AI-Closer: 1` and POST bodies `Content-Type: application/json`;
both force a CORS preflight that this server never answers, so an ordinary web page cannot write to
or read from it. Analysis runs in one background thread per meeting (single flight: utterances that
arrive meanwhile are picked up by one follow-up analysis). Nothing is persisted; latency timings
(no text) are printed as JSON lines.
"""
from __future__ import annotations

import argparse
import json
import socket
import sys
import threading
import time
import urllib.request
import uuid
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from closer_ai.ai.objection_guidance import load_objection_knowledge
from closer_ai.ai.ollama_provider import OllamaClassificationProvider, OllamaError
from closer_ai.demo.analyze_call import CLASSIFICATION_KB, GUIDANCE_KB, ContextGuard
from closer_ai.live.post_call_brief import render_markdown
from closer_ai.live.session import LiveConfig, LiveSalesSession, LiveUtterance

DEFAULT_PORT = 8765
SELF_LABELS = ("você", "voce", "you")  # how Meet captions the local user
_MAX_BODY = 64 * 1024
_MAX_REHYDRATE_BODY = 1024 * 1024  # up to ~1000 utterances of one meeting


def role_for(speaker: str, closer_names: set[str]) -> str:
    """Closer = the configured names (and Meet's "You"); unknown stays unknown; anyone else = lead."""
    s = speaker.strip().lower()
    if not s or s == "unknown":
        return "unknown"
    return "closer" if s in closer_names else "lead"


def _timestamp(value: Any) -> float:
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value / 1000 if value > 1e11 else value)  # epoch ms or s
    if isinstance(value, str):
        return datetime.fromisoformat(value).timestamp()
    raise ValueError("timestamp must be epoch seconds/ms or ISO-8601")


def parse_utterance(payload: Any, closer_names: set[str], received_at: float) -> LiveUtterance:
    if not isinstance(payload, dict):
        raise TypeError("expected a JSON object")
    meeting_id, text, seq = payload.get("meeting_id"), payload.get("text"), payload.get("sequence")
    speaker = payload.get("speaker") or "unknown"
    if not isinstance(meeting_id, str) or not meeting_id or not isinstance(text, str) or not isinstance(speaker, str):
        raise TypeError("meeting_id, speaker and text must be strings")
    if not isinstance(seq, int) or isinstance(seq, bool):
        raise TypeError("sequence must be an integer")
    return LiveUtterance(meeting_id=meeting_id, speaker=speaker.strip() or "unknown",
                         role=role_for(speaker, closer_names), text=text.strip(),
                         timestamp=_timestamp(payload.get("timestamp", received_at)), sequence=seq,
                         received_at=received_at,
                         caption_changed_at=_timestamp(payload["changed_at"]) if "changed_at" in payload else None)


class Runtime:
    """Sessions by meeting_id + the single-flight analysis worker."""

    def __init__(self, provider: Any, config: LiveConfig, closer_names: set[str], log=print,
                 debug: bool = False) -> None:
        self.provider, self.config, self.log, self.debug = provider, config, log, debug
        self._last_poll: dict[str, str] = {}
        self.closer_names = {n.lower() for n in closer_names} | set(SELF_LABELS)
        self.knowledge = load_objection_knowledge(GUIDANCE_KB)
        self.sessions: dict[str, LiveSalesSession] = {}
        self._busy: set[str] = set()
        self._lock = threading.Lock()
        self.model = getattr(provider, "model", None)
        self.model_state = "unknown"  # unknown | ready | unavailable (warm-up and every analysis update it)
        # A new id per process: the extension sees it change after a restart and rehydrates the meeting.
        self.instance = uuid.uuid4().hex[:12]

    def session(self, meeting_id: str) -> LiveSalesSession:
        with self._lock:
            if meeting_id not in self.sessions:
                self.sessions[meeting_id] = LiveSalesSession(meeting_id, self.provider, self.knowledge,
                                                             CLASSIFICATION_KB, self.config,
                                                             debug=self.dbg if self.debug else None)
            return self.sessions[meeting_id]

    def dbg(self, tag: str, **fields: Any) -> None:
        """Temporary `--debug` stage log (stderr). Includes caption text: test meetings only."""
        if self.debug:
            self.log(f"[{tag}] " + json.dumps(fields, ensure_ascii=False, default=str))

    def receive(self, utt: LiveUtterance, background: bool = True) -> str:
        """Add one utterance; returns the delivery status (ACCEPTED | DUPLICATE_SEQUENCE | DUPLICATE_TEXT | EMPTY)."""
        s = self.session(utt.meeting_id)
        with s.lock:  # add + its status, atomically (concurrent POSTs for the same meeting)
            accepted = s.add(utt)
            status = s.last_add_status
        why_not = s.last_trigger_reason if accepted else status
        s.debug_state.update(last_speaker=utt.speaker, last_role=utt.role)
        self.dbg("RUNTIME", sequence=utt.sequence, speaker=utt.speaker, role=utt.role, accepted=accepted,
                 status=status, text=utt.text)
        busy = utt.meeting_id in self._busy
        self.dbg("TRIGGER", analyze=why_not is None, reason=why_not, busy=busy,
                 queued=why_not is None and busy, pending_lead=s.pending_lead_seq)
        if accepted and (why_not is None or s.should_extract()):
            if background:
                self._kick(s)
            else:
                if why_not is None:
                    self._done(s.analyze())
                while s.should_extract():
                    self._facts(s.extract())
        return status

    def _facts(self, t: dict[str, Any]) -> None:
        """One commercial-facts extraction finished: technical line only (no call text)."""
        if t.get("outcome") != "NOTHING":
            self.log(json.dumps(t))

    def _done(self, t: dict[str, Any]) -> None:
        """One finished analysis: timing line on stderr + model health from what actually happened."""
        self.log(json.dumps(t))
        if str(t.get("reason", "")).startswith("ERROR:OllamaError"):
            self.model_state = "unavailable"
        elif t.get("classifier_finished_at"):
            self.model_state = "ready"

    def health(self) -> dict[str, Any]:
        """Runtime and model state only; never call data."""
        return {"status": "ok" if self.model_state != "unavailable" else "degraded", "runtime": "ready",
                "model": self.model, "model_state": self.model_state, "instance": self.instance}

    def rehydrate(self, meeting_id: str, items: Any) -> dict[str, Any]:
        """Rebuild a meeting's transcript after a restart; never analyzed (see LiveSalesSession.rehydrate)."""
        if not isinstance(items, list):
            raise TypeError("utterances must be a list")
        now = time.time()
        utts = [parse_utterance({**i, "meeting_id": meeting_id}, self.closer_names, now) for i in items]
        s = self.session(meeting_id)
        added = s.rehydrate(utts)
        self.dbg("REHYDRATE", meeting_id=meeting_id, received=len(utts), added=added, utterances=len(s.utterances))
        if added and s.should_extract():
            self._kick(s)  # rebuild the commercial state in the background: extraction only, no analysis
        return {"rehydrated": added, "utterances": len(s.utterances), "instance": self.instance}

    def finalize(self, meeting_id: str, wait_seconds: float = 60.0) -> dict[str, Any] | None:
        """End of call -> Post-call Brief (None: unknown meeting). Waits for the analysis/extraction in
        progress so the last lead lines are in the state; raises TimeoutError if it does not finish."""
        s = self.sessions.get(meeting_id)
        if s is None:
            return None
        deadline = time.time() + wait_seconds
        while s.brief is None and s.busy():
            if time.time() > deadline:
                raise TimeoutError("analysis still running; finalize again in a few seconds")
            time.sleep(0.1)
        brief = s.finalize()
        self.dbg("BRIEF", meeting_id=meeting_id, risks=[r.code for r in brief.risks], facts=sum(map(len, brief.facts.values())))
        return {"brief": brief.to_json(), "markdown": render_markdown(brief)}

    def _kick(self, s: LiveSalesSession) -> None:
        with self._lock:
            if s.meeting_id in self._busy:
                return  # busy: the pending slot holds the latest lead; the worker takes it when done
            self._busy.add(s.meeting_id)

        def work() -> None:
            # Objection analysis first (it drives the recommendation); commercial facts only when no lead
            # line is waiting for analysis and the call has paused (facts_idle), so they rarely hold Ollama
            # when the next lead line arrives.
            try:
                while True:
                    if s.should_analyze():
                        self._done(s.analyze())
                    elif s.should_extract():
                        if s.facts_idle():
                            self._facts(s.extract())
                        else:
                            time.sleep(0.25)  # wait for a pause in the conversation (or a new lead line)
                    with self._lock:
                        if not s.should_analyze() and not s.should_extract():
                            self._busy.discard(s.meeting_id)
                            return
            except BaseException:
                with self._lock:
                    self._busy.discard(s.meeting_id)
                raise

        threading.Thread(target=work, daemon=True).start()

    def status(self, s: LiveSalesSession | None, rec: Any) -> str:
        """Dock state: CAPTURING | ANALYZING | RECOMMENDATION_READY | NO_RECOMMENDATION | ERROR.

        Called under `s.lock` and derived only from session state, so it can never disagree with the
        `active_analysis` / recommendation of the same snapshot (a lead line waiting for the worker counts
        as ANALYZING)."""
        if s is not None and (s.active_analysis is not None or s.pending_lead_seq is not None):
            return "ANALYZING"
        if rec is not None:
            return "RECOMMENDATION_READY"
        last = s.last_outcome if s else None
        if last and last.startswith("NO_RECOMMENDATION:ERROR"):
            return "ERROR"
        if last and last.startswith("NO_RECOMMENDATION"):
            return "NO_RECOMMENDATION"
        return "CAPTURING"

    def recommendation(self, meeting_id: str) -> dict[str, Any]:
        """What the sidebar shows: the one active recommendation (top-level fields, or state NONE),
        the sidebar status and the last utterances exactly as the session received them."""
        s = self.sessions.get(meeting_id)
        if s is None:
            view = {"state": "NONE", "status": "CAPTURING", "transcript": [], "instance": self.instance}
            if self.debug:
                view["debug"] = {"session": False}
            return view
        with s.lock:  # one consistent snapshot: never a finished result next to a stale "analyzing"
            rec = s.current()
            view = {"state": "NONE"} if rec is None else rec.view()
            if rec is not None:
                s.mark_displayed(rec.id)
            view["status"] = self.status(s, rec)
            view["instance"] = self.instance
            view["active_analysis"] = s.active_analysis and dict(s.active_analysis)
            view["last_completed_analysis"] = s.last_completed_analysis and dict(s.last_completed_analysis)
            view["transcript"] = [{"role": u.role, "text": u.text, **({"speaker": u.speaker} if self.debug else {})}
                                  for u in s.transcript()]
            view["commercial_state"] = s.commercial.view()  # shown only in the dock's advanced panel
            view["playbook_compliance"] = s.compliance().view()  # idem (deterministic, ~ms)
            if s.brief is not None:  # after POST /finalize (advanced panel only)
                view["post_call_brief"] = {"markdown": render_markdown(s.brief), "finalized_at": s.brief.finalized_at}
        if self.debug:
            if self._last_poll.get(meeting_id) != view["state"]:  # log changes only (polled every 0.5 s)
                self._last_poll[meeting_id] = view["state"]
                self.dbg("POLL", meeting_id=meeting_id, session=True, state=view["state"])
            last = s.timings[-1] if s.timings else {}
            view["debug"] = {**s.debug_state, "session": True, "utterances": len(s.utterances),
                             "latency": {k: last[k] for k in ("queue_wait_ms", "classifier_latency_ms",
                                                              "guidance_latency_ms", "end_to_end_latency_ms",
                                                              "displayed_latency_ms") if k in last},
                             "counters": dict(s.counters), "analysis_error_reasons": dict(s.error_reasons),
                             "commercial_counters": dict(s.fact_counters), "compliance_ms": s.compliance_ms,
                             "fast_path": {**s.fast_path_counters, "by_category": dict(s.fast_path_by_category)},
                             "model_state": self.model_state,
                             "recommendation_state": (s.current_recommendation.state
                                                      if s.current_recommendation else "NONE")}
        return view


def make_handler(runtime: Runtime) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args: Any) -> None:  # no request logging (URLs carry the meeting id)
            pass

        def _send(self, code: int, body: dict[str, Any]) -> None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _allowed(self) -> bool:
            if self.headers.get("X-AI-Closer") != "1":
                self._send(403, {"error": "missing X-AI-Closer header"})
                return False
            return True

        def _json(self) -> Any:
            if not (self.headers.get("Content-Type") or "").startswith("application/json"):
                raise ValueError("Content-Type must be application/json")
            n = int(self.headers.get("Content-Length") or 0)
            if n > (_MAX_REHYDRATE_BODY if self.path == "/rehydrate" else _MAX_BODY):
                raise ValueError("body too large")
            return json.loads(self.rfile.read(n) or b"null")

        def do_GET(self) -> None:
            url = urlsplit(self.path)
            if url.path == "/health":  # no call data: no header needed (curl, duplicate-runtime check)
                return self._send(200, runtime.health())
            if not self._allowed():
                return
            if url.path != "/recommendation":
                return self._send(404, {"error": "not found"})
            meeting_id = parse_qs(url.query).get("meeting_id", [""])[0]
            self._send(200, runtime.recommendation(meeting_id))

        def do_POST(self) -> None:
            if not self._allowed():
                return
            try:
                payload = self._json()
                if self.path == "/live-utterance":
                    utt = parse_utterance(payload, runtime.closer_names, time.time())
                    runtime.dbg("CAPTION", speaker=utt.speaker, text=utt.text, sequence=utt.sequence)
                    status = runtime.receive(utt)
                    runtime.dbg("HTTP", request="POST /live-utterance", status=200, delivery=status)
                    return self._send(200, {"accepted": status == "ACCEPTED", "status": status,
                                            "id": utt.sequence, "role": utt.role})
                if self.path == "/rehydrate":
                    meeting_id = payload.get("meeting_id")
                    if not isinstance(meeting_id, str) or not meeting_id:
                        raise ValueError("meeting_id must be a non-empty string")
                    return self._send(200, runtime.rehydrate(meeting_id, payload.get("utterances")))
                if self.path == "/finalize":
                    try:
                        out = runtime.finalize(str(payload.get("meeting_id", "")))
                    except TimeoutError as exc:
                        return self._send(503, {"error": str(exc)})
                    return self._send(200, out) if out else self._send(404, {"error": "unknown meeting"})
                if self.path == "/dismiss":
                    runtime.session(str(payload.get("meeting_id", ""))).dismiss()
                    return self._send(200, {"ok": True})
                self._send(404, {"error": "not found"})
            except (ValueError, TypeError, AttributeError) as exc:
                runtime.dbg("HTTP", request=f"POST {self.path}", status=400, error=str(exc))
                self._send(400, {"error": str(exc)})

    return Handler


def replay(runtime: Runtime, path: Path, delay: float) -> None:
    """Feed a `speaker: text` transcript as a live stream, analysing inline; print what the closer sees."""
    lines = [ln.strip() for ln in path.read_text(encoding="utf-8-sig").splitlines()]
    runtime.closer_names.add("closer")  # replay files label speakers by role ("closer:", "lead:")
    seq = 0
    for line in lines:
        if not line or line.startswith("#"):
            continue
        speaker, _, text = line.partition(":")
        seq += 1
        now = time.time()
        print(f"> {speaker.strip()}: {text.strip()}")
        runtime.receive(parse_utterance({"meeting_id": "replay", "speaker": speaker, "text": text,
                                         "timestamp": now, "sequence": seq}, runtime.closer_names, now),
                        background=False)
        print(json.dumps(runtime.recommendation("replay"), ensure_ascii=False, indent=2))
        time.sleep(delay)


class LiveHTTPServer(ThreadingHTTPServer):
    """One runtime per port. Windows lets a second process bind a port that has SO_REUSEADDR (the
    stdlib default here), and the extension then talks to whichever answers; an exclusive bind makes the
    second runtime fail at start instead."""

    allow_reuse_address = not sys.platform.startswith("win")
    daemon_threads = True

    def server_bind(self) -> None:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):  # Windows
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def bind_or_explain(port: int, handler: type[BaseHTTPRequestHandler]) -> LiveHTTPServer:
    """The server, or SystemExit with a clear message when the port is taken."""
    try:
        return LiveHTTPServer(("127.0.0.1", port), handler)
    except OSError as exc:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1) as r:
                ours = bool(json.loads(r.read()).get("runtime"))
        except (OSError, ValueError):
            ours = False
        who = "AI Closer runtime already running" if ours else "port already in use by another process"
        raise SystemExit(f"ERROR: {who} on 127.0.0.1:{port} ({exc.strerror or exc}). "
                         "Stop it first; only one runtime may serve the extension.") from exc


def warm_up(ollama: OllamaClassificationProvider, log, runtime: Runtime | None = None) -> None:
    """Load the model (same options as the analyses) before the first objection: a cold load measured
    6.7-23 s on the RTX 4050 test machine, all of it otherwise added to the first recommendation."""
    t0 = time.time()
    try:
        ollama.classify('Return {"ok": true} as JSON.')
        if runtime is not None:
            runtime.model_state = "ready"
        log(json.dumps({"warm_up_ms": round((time.time() - t0) * 1000),
                        "load_ms": round(ollama.last_usage.get("load_duration", 0) / 1e6)}))
    except (OllamaError, ValueError) as exc:  # never blocks serving; the first analysis reports the real error
        if runtime is not None:
            runtime.model_state = "unavailable"
        log(json.dumps({"warm_up_error": f"{type(exc).__name__}: {exc}"}))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--closer", default="", help="comma-separated caption names of the closer (besides 'You')")
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    p.add_argument("--model", default="qwen3:8b")
    p.add_argument("--num-ctx", type=int, default=4096)
    p.add_argument("--no-fast-path", action="store_true",
                   help="always use the LLM classifier (no deterministic fast path for obvious PRICE/AUTHORITY)")
    p.add_argument("--reserve-tokens", type=int, default=1024, help="output budget kept free in num_ctx")
    p.add_argument("--arm", default="E1", choices=("E0", "E1", "E2"))
    p.add_argument("--window-seconds", type=float, default=LiveConfig.window_seconds)
    p.add_argument("--window-utterances", type=int, default=LiveConfig.max_window_utterances)
    p.add_argument("--cooldown", type=float, default=LiveConfig.cooldown_seconds)
    p.add_argument("--ttl", type=float, default=LiveConfig.ttl_seconds)
    p.add_argument("--timeout", type=float, default=120.0, help="Ollama request timeout (s)")
    p.add_argument("--keep-alive", default="30m",
                   help="how long Ollama keeps the model loaded between analyses ('' = Ollama's default, 5 min)")
    p.add_argument("--replay", type=Path, help="stream this transcript instead of serving")
    p.add_argument("--delay", type=float, default=1.0, help="seconds between replayed utterances")
    p.add_argument("--no-commercial-state", action="store_true",
                   help="do not extract commercial facts (no extra LLM call per lead line)")
    p.add_argument("--debug", action="store_true",
                   help="temporary: log every pipeline stage (with caption text) and show a debug panel; test meetings only")
    a = p.parse_args(argv)

    ollama = OllamaClassificationProvider(a.model, timeout=a.timeout, num_ctx=a.num_ctx, keep_alive=a.keep_alive or None)
    provider = ContextGuard(ollama, num_ctx=a.num_ctx, reserve_tokens=a.reserve_tokens)
    config = LiveConfig(window_seconds=a.window_seconds, max_window_utterances=a.window_utterances,
                        cooldown_seconds=a.cooldown, ttl_seconds=a.ttl, arm=a.arm,
                        commercial_facts=not a.no_commercial_state, fast_path=not a.no_fast_path)
    names = {n.strip() for n in a.closer.split(",") if n.strip()}
    runtime = Runtime(provider, config, names, log=lambda s: print(s, file=sys.stderr, flush=True), debug=a.debug)
    if a.replay:
        replay(runtime, a.replay, a.delay)
        return 0
    server = bind_or_explain(a.port, make_handler(runtime))
    threading.Thread(target=warm_up, args=(ollama, runtime.log, runtime), daemon=True).start()
    print(f"AI Closer live runtime on http://127.0.0.1:{a.port} ({a.model}, {a.arm}, num_ctx {a.num_ctx}"
          f"{'; no fast path' if a.no_fast_path else ''})"
          f" closer names: {sorted(runtime.closer_names)}{' [DEBUG]' if a.debug else ''}", file=sys.stderr, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
