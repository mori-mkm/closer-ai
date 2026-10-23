// AI Closer — content script on meet.google.com: captions -> local runtime; a small dock at the bottom
// left with three retractable panels (Sugestão, Histórico, ⋯). Nothing is stored in the browser. Talks
// to the runtime only through background.js. What is shown is decided by dockView()/dockReducer()
// (sidebar_view.js); this file only draws it.

(() => {
  const meetingId = location.pathname.slice(1);
  if (!/^[a-z]{3}-[a-z]{4}-[a-z]{3}$/.test(meetingId)) return; // not a meeting page

  const tracker = new CaptionTracker(meetingId);
  // Never throws, never resolves with nothing: every outcome is classified (see delivery.js).
  const send = (msg) => new Promise((resolve) => {
    try {
      chrome.runtime.sendMessage(msg, (r) => {
        const err = chrome.runtime.lastError; // e.g. the background worker was restarting
        resolve(err || !r ? { ok: false, error: "EXTENSION_UNAVAILABLE", detail: err && err.message } : r);
      });
    } catch (e) { // the extension was reloaded/updated under this tab: reload the Meet tab
      resolve({ ok: false, error: "EXTENSION_CONTEXT_INVALIDATED", detail: String(e) });
    }
  });
  const delivery = new UtteranceDelivery();
  const rehydrator = new Rehydrator();

  // --- dock (shadow DOM so Meet's CSS cannot touch it). Bottom left, above Meet's control bar. ---
  const BASE_BOTTOM = 88; // Meet's control bar is ~80 px tall
  const host = document.createElement("div");
  host.style.cssText = `position:fixed;left:16px;bottom:${BASE_BOTTOM}px;z-index:2147483647`;
  const root = host.attachShadow({ mode: "closed" });
  root.innerHTML = `<style>
    :host{all:initial}
    *{box-sizing:border-box}
    .wrap{font:13px/1.45 "Google Sans",Roboto,system-ui,sans-serif;color:#e8eaed;display:flex;flex-direction:column;
      align-items:flex-start;gap:8px}
    .panel{width:min(360px,calc(100vw - 32px));background:#181818;border:1px solid #2a2a2a;border-radius:14px;
      box-shadow:0 8px 24px rgba(0,0,0,.45);display:flex;flex-direction:column;overflow:hidden}
    .ph{display:flex;align-items:center;gap:8px;padding:10px 12px 6px 14px}
    .pt{font-size:11px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;color:#9aa0a6;flex:1}
    .pb{padding:4px 14px 14px;overflow-y:auto;scrollbar-width:thin;scrollbar-color:#3c4043 transparent}
    .x{border:0;background:transparent;color:#9aa0a6;font-size:16px;line-height:1;width:24px;height:24px;
      border-radius:6px;cursor:pointer}
    .x:hover{background:#2a2a2a;color:#e8eaed}
    .lbl{font-size:10px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;color:#9aa0a6;margin-top:12px}
    .lbl:first-child{margin-top:0}
    .said{font-size:13px;font-style:italic;color:#bdbdbd;margin-top:2px}
    .say{font-size:18px;font-weight:600;line-height:1.35;color:#fff;margin-top:4px}
    .lbl.ready{color:#8ab4f8}
    .obj{font-size:12px;color:#9aa0a6;margin-top:10px}
    .foot{display:flex;align-items:center;justify-content:space-between;margin-top:12px}
    .chip{font-size:11px;color:#bdbdbd;background:#242424;border-radius:10px;padding:2px 8px}
    .live{display:flex;gap:6px;align-items:baseline;font-size:12px;color:#bdbdbd;margin-bottom:10px}
    .live .d{width:7px;height:7px;border-radius:50%;flex:none;transform:translateY(-1px)}
    .empty{color:#9aa0a6;font-style:italic}
    .btn{border:0;background:#242424;color:#e8eaed;font:inherit;font-size:13px;border-radius:18px;
      padding:7px 14px;cursor:pointer;position:relative;display:inline-flex;align-items:center;gap:6px}
    .btn:hover{background:#2f2f2f}
    .btn.on{background:#3c4043}
    .btn.icon{padding:7px 11px;font-weight:700}
    .btn.hot{box-shadow:inset 0 0 0 1px #8ab4f8;color:#8ab4f8}
    .badge{width:8px;height:8px;border-radius:50%;background:#8ab4f8}
    .dock{display:flex;align-items:center;gap:6px;background:#111;border:1px solid #2a2a2a;border-radius:24px;
      padding:5px;box-shadow:0 4px 14px rgba(0,0,0,.4)}
    .st{display:inline-flex;align-items:center;gap:6px;padding:0 8px 0 6px;font-size:12px;color:#bdbdbd;
      max-width:170px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
    .dot{width:8px;height:8px;border-radius:50%;flex:none}
    .warn{font-size:11px;color:#bdbdbd;background:#2a2a2a;border-radius:10px;padding:2px 8px;cursor:help}
    .toast{font-size:12px;color:#8ab4f8;background:#111;border:1px solid #2a2a2a;border-radius:12px;padding:4px 10px;
      pointer-events:none}
    .hl{margin-bottom:10px}
    .hw{font-size:11px;font-weight:600;color:#9aa0a6}
    .hw.lead{color:#e8eaed}
    .ht{color:#bdbdbd}
    .hl.lead .ht{color:#fff}
    .mono{font:11px/1.45 ui-monospace,Consolas,monospace;color:#bdbdbd;white-space:pre-wrap;margin:0}
    [hidden]{display:none!important}
  </style>
  <div class="wrap">
    <div class="panel" id="p-suggestion" hidden>
      <div class="ph"><span class="pt">Sugestão</span><button class="x" data-close title="Minimizar">–</button></div>
      <div class="pb" id="sug"></div>
    </div>
    <div class="panel" id="p-history" hidden>
      <div class="ph"><span class="pt">Histórico</span><button class="x" data-close title="Minimizar">–</button></div>
      <div class="pb" id="hist" style="max-height:260px"></div>
    </div>
    <div class="panel" id="p-advanced" hidden>
      <div class="ph"><span class="pt">Avançado</span><button class="x" data-close title="Minimizar">–</button></div>
      <div class="pb" style="max-height:320px"><button class="btn" id="b-finalize"
        title="Gera o Post-call Brief a partir do estado comercial da call">Finalizar call · brief</button>
        <pre class="mono" id="adv"></pre></div>
    </div>
    <div class="toast" id="toast" hidden>Nova sugestão</div>
    <div class="dock">
      <span class="st"><span class="dot" id="dot"></span><span id="status"></span></span>
      <span class="warn" id="warn" hidden></span>
      <button class="btn" id="b-suggestion">Sugestão<span class="badge" id="badge" hidden></span></button>
      <button class="btn" id="b-history">Histórico</button>
      <button class="btn icon" id="b-advanced" title="Avançado" aria-label="Avançado">•••</button>
    </div>
  </div>`;
  document.documentElement.appendChild(host);
  const $ = (id) => root.getElementById(id);
  const el = (tag, cls, text) => {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  };

  const counters = { captions_seen: 0 };
  let health = null;
  let polling = false;
  const seenKeys = new Set();
  let runtimeOk = false;
  let lastData = null;
  let ui = DOCK_INITIAL;
  let view = null;
  let shownHistory = "";
  let shownSuggestion = "";

  const dispatch = (action) => { ui = dockReducer(ui, action); render(); };
  for (const p of ["suggestion", "history", "advanced"]) {
    $(`b-${p}`).onclick = () => dispatch({ type: "toggle", panel: p, recId: view && view.rec ? view.rec.id : null });
  }
  for (const b of root.querySelectorAll("[data-close]")) b.onclick = () => dispatch({ type: "close" });
  // Post-call Brief: explicit end of call (POST /finalize, idempotent); the brief then shows in this panel.
  $("b-finalize").onclick = () => {
    $("b-finalize").textContent = "Gerando brief…";
    send({ type: "finalize", body: { meeting_id: meetingId } }).then((r) => {
      $("b-finalize").textContent = r.ok ? "Brief gerado" : `Brief: erro (${r.error}${r.status ? ` ${r.status}` : ""})`;
      poll();
    });
  };

  function liveLine(color, text) {
    const row = el("div", "live");
    const d = el("span", "d");
    d.style.background = color;
    row.append(d, el("span", null, text));
    return row;
  }

  function renderSuggestion(v) {
    const key = JSON.stringify([v.rec, v.analyzing, v.detected]);
    if (key === shownSuggestion) return; // redraw only on change (keeps the Dispensar button under the cursor)
    shownSuggestion = key;
    const box = $("sug");
    box.replaceChildren();
    // Below, in this order: what to say now (largest), what the client said, the objective.
    if (v.detected) box.append(liveLine(TONES.objection, `Objeção detectada · ${v.detected.label}`));
    else if (v.analyzing) box.append(liveLine(TONES.analyzing, `Analisando: “${v.analyzing.text}”`));
    if (!v.rec) {
      if (!v.analyzing) box.append(el("div", "empty", "Nenhuma sugestão ativa."));
      else if (v.detected) box.append(el("div", "empty", "Preparando a sugestão…"));
      return;
    }
    box.append(el("div", "lbl", "Cliente disse"), el("div", "said", `“${v.rec.said}”`),
      el("div", "lbl ready", "Sugestão"), el("div", "say", `“${v.rec.question}”`));
    if (v.rec.objective) box.append(el("div", "obj", `Objetivo: ${v.rec.objective}`));
    const foot = el("div", "foot");
    const dismiss = el("button", "btn", "Dispensar");
    dismiss.onclick = () => {
      dispatch({ type: "dismiss", recId: v.rec.id });
      send({ type: "dismiss", body: { meeting_id: meetingId } }).then(poll);
    };
    foot.append(el("span", "chip", v.rec.label || ""), dismiss);
    box.append(foot);
  }

  function renderHistory(lines) {
    const key = JSON.stringify(lines);
    if (key === shownHistory) return;
    shownHistory = key;
    const box = $("hist");
    const atBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 24;
    box.replaceChildren();
    if (!lines.length) box.append(el("div", "empty", "Nenhuma fala recebida pelo runtime ainda."));
    for (const l of lines) {
      const row = el("div", `hl ${l.role}`);
      row.append(el("div", `hw ${l.role}`, l.who), el("div", "ht", l.text));
      box.append(row);
    }
    if (atBottom) box.scrollTop = box.scrollHeight;
  }

  function render() {
    view = dockView(lastData, {
      runtimeOk, captionsOn: MeetCaptionAdapter.region(document) !== null, counters, meetingId, health, delivery,
      rehydrator,
    });
    const chrome_ = dockChrome(ui, view, Date.now());
    $("dot").style.background = view.color;
    $("status").textContent = view.status;
    $("warn").hidden = !view.warning;
    if (view.warning) { $("warn").textContent = `⚠ ${view.warning.count}`; $("warn").title = view.warning.text; }
    $("badge").hidden = !chrome_.badge;
    $("b-suggestion").classList.toggle("hot", chrome_.active);
    $("toast").hidden = !chrome_.toast;
    for (const p of ["suggestion", "history", "advanced"]) {
      $(`p-${p}`).hidden = ui.open !== p;
      $(`b-${p}`).classList.toggle("on", ui.open === p);
    }
    if (ui.open === "suggestion") renderSuggestion(view); else shownSuggestion = "";
    if (ui.open === "history") renderHistory(view.history); else shownHistory = "";
    if (ui.open === "advanced") {
      const a = view.advanced;
      $("adv").textContent = [...(a.brief ? [...a.brief, ""] : []), ...a.basic, ...(a.commercial ? ["", ...a.commercial] : []), ...(a.technical ? ["", ...a.technical]
        : ["", "Detalhes técnicos: inicie o runtime com --debug."])].join("\n");
    }
  }

  // Keep the dock above Meet's captions when they reach the left side (small windows, long captions).
  function place() {
    const region = MeetCaptionAdapter.region(document);
    let bottom = BASE_BOTTOM;
    if (region) {
      const r = region.getBoundingClientRect();
      const dockRight = 16 + Math.min(360, innerWidth - 32);
      if (r.height > 0 && r.left < dockRight && r.top < innerHeight - BASE_BOTTOM) {
        bottom = Math.max(BASE_BOTTOM, Math.round(innerHeight - r.top + 8));
      }
    }
    host.style.bottom = `${bottom}px`;
    for (const p of root.querySelectorAll(".panel")) p.style.maxHeight = `${Math.max(160, innerHeight - bottom - 80)}px`;
  }

  async function poll() {
    if (polling) return; // one GET at a time: an answer is never overtaken by an older one
    polling = true;
    const r = await send({ type: "poll", meeting_id: meetingId });
    polling = false;
    runtimeOk = r.ok;
    lastData = r.ok ? r.data : null;
    if (lastData) rehydrator.observe(lastData.instance);
    if (rehydrator.due()) { // the runtime restarted: give this meeting's transcript back, once
      send({ type: "rehydrate", body: { meeting_id: meetingId, utterances: delivery.heldUtterances() } })
        .then((rr) => rehydrator.result(rr));
    }
    const recId = lastData && lastData.state === "ACTIVE" ? lastData.id : null;
    ui = dockReducer(ui, { type: "data", recId, now: Date.now() });
    render();
  }

  setInterval(() => {
    const captions = MeetCaptionAdapter.read(document);
    for (const c of captions) if (!seenKeys.has(c.key)) { seenKeys.add(c.key); counters.captions_seen++; }
    const now = Date.now();
    for (const u of tracker.tick(now, captions)) delivery.add(u, now);
    for (const u of delivery.due(now)) { // first attempts and bounded retries, same id each time
      send({ type: "utterance", body: u }).then((r) => delivery.result(u.sequence, r, Date.now()));
    }
    place();
  }, 500);
  setInterval(poll, 500); // loopback GET: cheap; a new suggestion reaches the dock within 0.5 s
  const checkHealth = () => send({ type: "health" }).then((r) => {
    health = r.ok ? r.data : null;
    if (health) rehydrator.observe(health.instance);
  });
  setInterval(checkHealth, 5000);
  checkHealth();
  addEventListener("resize", place);
  poll();
})();
