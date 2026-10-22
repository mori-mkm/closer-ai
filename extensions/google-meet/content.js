// AI Closer — content script on meet.google.com: captions -> local runtime; sidebar with the captured
// transcript and the one active recommendation. Nothing is stored in the browser. Talks to the runtime
// only through background.js. What the sidebar shows is decided by sidebarView() (sidebar_view.js).

(() => {
  const meetingId = location.pathname.slice(1);
  if (!/^[a-z]{3}-[a-z]{4}-[a-z]{3}$/.test(meetingId)) return; // not a meeting page

  const tracker = new CaptionTracker(meetingId);
  const send = (msg) => new Promise((resolve) => chrome.runtime.sendMessage(msg, (r) => resolve(r || { ok: false })));

  // --- sidebar (shadow DOM so Meet's CSS cannot touch it). Right side, above Meet's control bar. ---
  const host = document.createElement("div");
  host.style.cssText = "position:fixed;right:16px;bottom:96px;z-index:2147483647;width:320px";
  const root = host.attachShadow({ mode: "closed" });
  root.innerHTML = `<style>
    .panel{font:13px/1.4 system-ui,sans-serif;background:rgba(255,255,255,.97);color:#1f1f1f;border-radius:12px;
      box-shadow:0 4px 16px rgba(0,0,0,.3);display:flex;flex-direction:column;max-height:calc(100vh - 200px)}
    .head{display:flex;align-items:center;gap:8px;padding:8px 12px;border-bottom:1px solid #eee}
    .brand{font-size:11px;font-weight:700;letter-spacing:.08em;color:#5f6368}
    .dot{width:8px;height:8px;border-radius:50%;flex:none}
    #status{font-size:12px;flex:1}
    button{border:0;background:#eee;border-radius:6px;padding:2px 8px;cursor:pointer;font-size:11px}
    .sec{font-size:10px;text-transform:uppercase;letter-spacing:.06em;color:#5f6368;margin:8px 12px 4px}
    #transcript{overflow-y:auto;min-height:40px;max-height:200px;padding:0 12px;flex:1 1 auto}
    .line{margin:0 0 4px}
    .who{font-weight:600;margin-right:4px}
    .who.lead{color:#b3261e}.who.closer{color:#1a73e8}
    .empty{color:#80868b;font-style:italic}
    #now{margin:8px 8px 0;padding:8px 12px;border-radius:10px;background:#fef7e0;border-left:4px solid #f9ab00;flex:none}
    .nowtxt{font-style:italic}
    #rec{margin:8px;padding:10px 12px;border-radius:10px;background:#fdecea;border-left:4px solid #b3261e;flex:none}
    .lbl{font-size:10px;text-transform:uppercase;letter-spacing:.06em;color:#5f6368;margin-top:6px}
    .lbl:first-child{margin-top:0}
    .cat{font-weight:700;font-size:14px;color:#b3261e}
    .code{font-size:11px;color:#5f6368}
    .say{font-weight:600;font-size:14px}
    .why{font-size:11px;color:#444;margin-top:6px}
    .dbg{font:10.5px/1.35 ui-monospace,monospace;color:#444;white-space:pre-wrap;border-top:1px solid #eee;
      padding:6px 12px;flex:none}
    [hidden]{display:none!important}
  </style>
  <div class="panel">
    <div class="head"><span class="brand">AI CLOSER</span><span class="dot" id="dot"></span><span id="status"></span>
      <button id="min" title="Minimizar">–</button></div>
    <div id="body">
      <div class="sec">Transcrição</div>
      <div id="transcript"></div>
      <div id="now" hidden>
        <div class="lbl">Analisando agora</div>
        <div><span class="who" id="nowwho"></span> <span class="nowtxt" id="nowtext"></span></div>
      </div>
      <div id="rec" hidden>
        <div class="lbl">Objeção detectada</div>
        <div class="cat" id="label"></div><div class="code" id="code"></div>
        <div class="lbl">O que fazer</div><div id="move"></div>
        <div class="lbl">O que falar</div><div class="say" id="question"></div>
        <div class="why" id="why"></div>
        <div style="text-align:right;margin-top:6px"><button id="dismiss">Dispensar</button></div>
      </div>
      <div class="dbg" id="dbg" hidden></div>
    </div>
  </div>`;
  document.documentElement.appendChild(host);
  const $ = (id) => root.getElementById(id);
  $("dismiss").onclick = () => send({ type: "dismiss", body: { meeting_id: meetingId } }).then(poll);
  $("min").onclick = () => { $("body").hidden = !$("body").hidden; $("min").textContent = $("body").hidden ? "+" : "–"; };

  const counters = { captions_seen: 0, utterances_sent: 0, utterances_failed: 0 };
  const seenKeys = new Set();
  let runtimeOk = false;
  let lastData = null;
  let shownTranscript = "";

  function renderTranscript(lines) {
    const key = JSON.stringify(lines);
    if (key === shownTranscript) return;
    shownTranscript = key;
    const box = $("transcript");
    const atBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 24;
    box.replaceChildren();
    if (!lines.length) {
      const e = document.createElement("div");
      e.className = "empty";
      e.textContent = "Nenhuma fala recebida pelo runtime ainda.";
      box.append(e);
    }
    for (const l of lines) {
      const row = document.createElement("div");
      row.className = "line";
      const who = document.createElement("span");
      who.className = `who ${l.role}`;
      who.textContent = `${l.who}:`;
      row.append(who, document.createTextNode(l.text));
      box.append(row);
    }
    if (atBottom) box.scrollTop = box.scrollHeight;
  }

  function render() {
    const v = sidebarView(lastData, {
      runtimeOk, captionsOn: MeetCaptionAdapter.region(document) !== null, counters, meetingId,
    });
    $("status").textContent = v.status.text;
    $("dot").style.background = v.status.color;
    renderTranscript(v.transcript);
    $("now").hidden = !v.analyzing;
    if (v.analyzing) {
      $("nowwho").textContent = `${v.analyzing.who}:`;
      $("nowtext").textContent = `"${v.analyzing.text}"`;
    }
    $("rec").hidden = !v.rec;
    if (v.rec) {
      $("label").textContent = `⚠ ${v.rec.label}`;
      $("code").textContent = v.rec.category;
      $("move").textContent = v.rec.move;
      $("question").textContent = `"${v.rec.question}"`;
      $("why").textContent = v.rec.rationale;
    }
    $("dbg").hidden = !v.debugLines;
    if (v.debugLines) $("dbg").textContent = v.debugLines.join("\n");
  }

  async function poll() {
    const r = await send({ type: "poll", meeting_id: meetingId });
    runtimeOk = r.ok;
    lastData = r.ok ? r.data : null;
    render();
  }

  setInterval(() => {
    const captions = MeetCaptionAdapter.read(document);
    for (const c of captions) if (!seenKeys.has(c.key)) { seenKeys.add(c.key); counters.captions_seen++; }
    for (const u of tracker.tick(Date.now(), captions)) {
      send({ type: "utterance", body: u }).then((r) => {
        runtimeOk = r.ok;
        if (r.ok) counters.utterances_sent++; else counters.utterances_failed++;
      });
    }
  }, 500);
  setInterval(poll, 1000);
  poll();
})();
