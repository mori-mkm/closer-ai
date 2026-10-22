// AI Closer — relay to the local runtime. Runs in the extension context, so the request is allowed by
// host_permissions instead of the Meet page's CORS. The X-AI-Closer header is required by the runtime.
const BASE = "http://127.0.0.1:8765";

chrome.runtime.onMessage.addListener((msg, _sender, reply) => {
  const headers = { "X-AI-Closer": "1" };
  let url, init;
  if (msg.type === "poll") {
    url = `${BASE}/recommendation?meeting_id=${encodeURIComponent(msg.meeting_id)}`;
    init = { method: "GET", headers };
  } else {
    url = `${BASE}/${msg.type === "dismiss" ? "dismiss" : "live-utterance"}`;
    init = { method: "POST", headers: { ...headers, "Content-Type": "application/json" }, body: JSON.stringify(msg.body) };
  }
  fetch(url, init)
    .then((r) => r.json())
    .then((data) => reply({ ok: true, data }))
    .catch((e) => reply({ ok: false, error: String(e) }));
  return true; // async reply
});
