// AI Closer — relay to the local runtime. Runs in the extension context, so the request is allowed by
// host_permissions instead of the Meet page's CORS. The X-AI-Closer header is required by the runtime.
//
// Every reply is classified (never a bare failure):
//   {ok: true, status, data}                          HTTP 2xx with a JSON body
//   {ok: false, error: "HTTP_ERROR", status, data?}   runtime answered 4xx/5xx
//   {ok: false, error: "HTTP_TIMEOUT"}                no answer within TIMEOUT_MS
//   {ok: false, error: "RUNTIME_UNAVAILABLE"}         nothing listening / connection refused
//   {ok: false, error: "INVALID_RESPONSE", status}    2xx but not JSON (another program on the port?)
const BASE = "http://127.0.0.1:8765";
const TIMEOUT_MS = 3000;

async function relay(msg) {
  const headers = { "X-AI-Closer": "1" };
  let url, init;
  if (msg.type === "poll") {
    url = `${BASE}/recommendation?meeting_id=${encodeURIComponent(msg.meeting_id)}`;
    init = { method: "GET", headers };
  } else if (msg.type === "rehydrate") {
    url = `${BASE}/rehydrate`;
    init = { method: "POST", headers: { ...headers, "Content-Type": "application/json" }, body: JSON.stringify(msg.body) };
  } else if (msg.type === "health") {
    url = `${BASE}/health`;
    init = { method: "GET" };
  } else {
    url = `${BASE}/${msg.type === "dismiss" ? "dismiss" : "live-utterance"}`;
    init = { method: "POST", headers: { ...headers, "Content-Type": "application/json" }, body: JSON.stringify(msg.body) };
  }
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
  let r;
  try {
    r = await fetch(url, { ...init, signal: ctrl.signal });
  } catch (e) {
    return { ok: false, error: e.name === "AbortError" ? "HTTP_TIMEOUT" : "RUNTIME_UNAVAILABLE", detail: String(e) };
  } finally {
    clearTimeout(timer);
  }
  let data;
  try {
    data = await r.json();
  } catch (e) {
    return { ok: false, error: r.ok ? "INVALID_RESPONSE" : "HTTP_ERROR", status: r.status };
  }
  return r.ok ? { ok: true, status: r.status, data } : { ok: false, error: "HTTP_ERROR", status: r.status, data };
}

chrome.runtime.onMessage.addListener((msg, _sender, reply) => {
  relay(msg).then(reply);
  return true; // async reply
});
