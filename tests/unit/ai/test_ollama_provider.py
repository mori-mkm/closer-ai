"""Ollama provider adapter tests. A stdlib fake server on 127.0.0.1 stands in for Ollama — no
Ollama install, model or external network is needed."""
from __future__ import annotations

import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from classifier_support import episode, response, synthetic_call

from closer_ai.ai.objection_classifier import (
    ClassificationProvider,
    MalformedResponseError,
    build_prompt,
    classify_call,
)
from closer_ai.ai.ollama_provider import (
    DEFAULT_BASE_URL,
    OllamaClassificationProvider,
    OllamaError,
    check_local_url,
)


class FakeOllama:
    """Replies to every POST with `status`, `body` (bytes) and extra `headers`; records requests."""

    def __init__(self) -> None:
        self.status, self.body, self.headers, self.delay = 200, b"{}", {}, 0.0
        self.requests: list[tuple[str, dict]] = []
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                length = int(self.headers["Content-Length"])
                fake.requests.append((self.path, json.loads(self.rfile.read(length))))
                time.sleep(fake.delay)
                self.send_response(fake.status)
                for k, v in fake.headers.items():
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(fake.body)))
                self.end_headers()
                self.wfile.write(fake.body)

            def log_message(self, *args: object) -> None:
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, args=(0.01,), daemon=True).start()

    def reply(self, content: str, **api: object) -> None:
        self.body = json.dumps({"model": "m", "response": content, "done": True, **api}).encode()


@pytest.fixture
def fake():
    server = FakeOllama()
    yield server
    server.server.shutdown()
    server.server.server_close()


def provider(fake: FakeOllama, **kw: object) -> OllamaClassificationProvider:
    return OllamaClassificationProvider(model="qwen3:8b", base_url=fake.url, **kw)


KB = Path(__file__).resolve().parents[3] / "docs" / "knowledge" / "sales" / "objections"


# --- request ----------------------------------------------------------------------------------


def test_request_endpoint_and_body(fake):
    fake.reply(json.dumps(response()))
    prompt = "TASK RULES\n\nçãõ — [s1 | lead]\n  exact  text\n"
    provider(fake, num_ctx=8192).classify(prompt)
    [(path, body)] = fake.requests
    assert path == "/api/generate"
    assert body == {
        "model": "qwen3:8b",
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "think": False,
        "options": {"temperature": 0, "num_ctx": 8192},
    }


@pytest.mark.parametrize("arm", ["E0", "E1", "E2"])
def test_classifier_prompt_sent_unchanged(fake, arm):
    call = synthetic_call()
    fake.reply(json.dumps(response()))
    classify_call(call, arm, provider(fake), knowledge_root=KB)
    assert fake.requests[0][1]["prompt"] == build_prompt(call, arm, KB)


# --- response ---------------------------------------------------------------------------------


def test_end_to_end_run_with_valid_model_json(fake):
    call = synthetic_call()
    s = [seg.segment_id for seg in call.segments]
    content = response(episode(objection_segment_ids=[s[1]], context_segment_ids=[s[2], s[3]]))
    fake.reply(json.dumps(content), prompt_eval_count=900, eval_count=120, total_duration=5, context=[1, 2])
    p = provider(fake)
    assert isinstance(p, ClassificationProvider)
    run = classify_call(call, "E0", p)
    assert run.provider == "ollama" and run.model == "qwen3:8b"
    assert run.raw_response == content  # the classifier receives exactly the model's JSON
    assert run.valid, run.validation_errors
    assert p.last_usage == {"prompt_eval_count": 900, "eval_count": 120, "total_duration": 5}


def test_invalid_prediction_is_reported_by_classifier_not_provider(fake):
    fake.reply(json.dumps(response(episode(objection_segment_ids=["nope"]))))
    run = classify_call(synthetic_call(), "E0", provider(fake))
    assert not run.valid


def test_wrong_shape_reaches_classifier_parser(fake):
    fake.reply(json.dumps({"call_detection": "NO_OBJECTION"}))
    with pytest.raises(MalformedResponseError, match="expected keys"):
        classify_call(synthetic_call(), "E0", provider(fake))


# --- errors -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "content",
    ['```json\n{"call_detection": "NO_OBJECTION"}\n```', 'Sure! {"a": 1}', "{'a': 1}", "", '["a"]', "3"],
)
def test_model_output_not_a_json_object_is_not_repaired(fake, content):
    fake.reply(content)
    with pytest.raises(MalformedResponseError, match="model output"):
        provider(fake).classify("x")


@pytest.mark.parametrize(
    "body",
    [b"not json", b"[]", b'{"done": true}', b'{"response": 5, "done": true}',
     b'{"response": "{}", "done": false, "done_reason": "load"}'],
)
def test_malformed_ollama_api_response(fake, body):
    fake.body = body
    with pytest.raises(OllamaError):
        provider(fake).classify("x")


@pytest.mark.parametrize("status", [400, 404, 500])
def test_http_error(fake, status):
    fake.status, fake.body = status, b'{"error": "model not found"}'
    with pytest.raises(OllamaError, match=f"HTTP {status}"):
        provider(fake).classify("x")


def test_timeout(fake):
    fake.reply("{}")
    fake.delay = 1.0
    with pytest.raises(OllamaError, match="unreachable"):
        provider(fake, timeout=0.1).classify("x")


def test_connection_refused():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    with pytest.raises(OllamaError, match="unreachable"):
        OllamaClassificationProvider(model="m", base_url=f"http://127.0.0.1:{port}").classify("x")


@pytest.mark.parametrize("status", [301, 302, 307, 308])
def test_redirect_is_not_followed(fake, status):
    fake.status, fake.headers = status, {"Location": "http://example.com/api/generate"}
    with pytest.raises(OllamaError, match=f"HTTP {status}"):
        provider(fake).classify("x")
    assert len(fake.requests) == 1


def test_proxy_environment_is_ignored(fake, monkeypatch):
    for var in ("HTTP_PROXY", "http_proxy", "ALL_PROXY"):
        monkeypatch.setenv(var, "http://203.0.113.1:9")  # TEST-NET, unroutable
    monkeypatch.delenv("NO_PROXY", raising=False)
    monkeypatch.delenv("no_proxy", raising=False)
    fake.reply("{}")
    assert provider(fake, timeout=2).classify("x") == {}
    assert len(fake.requests) == 1


# --- local-only boundary ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "url", [DEFAULT_BASE_URL, "http://localhost:11434", "http://127.0.0.1:11434/", "http://[::1]:11434"]
)
def test_loopback_urls_accepted(url):
    assert check_local_url(url) == url.rstrip("/")
    OllamaClassificationProvider(model="m", base_url=url)


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com:11434",
        "https://remote-server:11434",
        "https://127.0.0.1:11434",
        "http://192.168.0.10:11434",
        "http://10.0.0.5:11434",
        "http://8.8.8.8:11434",
        "http://0.0.0.0:11434",
        "http://localhost.example.com:11434",
        "http://127.0.0.1@example.com:11434",
        "http://user:pw@localhost:11434",
        "http://localhost:11434/proxy",
        "ftp://localhost",
        "localhost:11434",
        r"http://127.0.0.1:11434\.evil.com",
        "http://localhost:abc",
        "http://localhost:99999",
    ],
)
def test_non_local_urls_rejected(url):
    with pytest.raises(ValueError):
        OllamaClassificationProvider(model="m", base_url=url)


def test_model_is_required():
    with pytest.raises(TypeError):
        OllamaClassificationProvider()  # type: ignore[call-arg]
    with pytest.raises(ValueError):
        OllamaClassificationProvider(model="")


def test_config_matches_request_and_has_no_secret(fake):
    fake.reply("{}")
    p = provider(fake, timeout=7, num_ctx=4096)
    p.classify("x")
    body = fake.requests[0][1]
    c = p.config
    assert c == {"base_url": fake.url, "timeout": 7, "format": "json", "think": False, "temperature": 0,
                 "num_ctx": 4096}
    assert (body["format"], body["think"], body["options"]) == (
        c["format"], c["think"], {"temperature": c["temperature"], "num_ctx": c["num_ctx"]})


def test_usage_reset_when_a_later_call_fails(fake):
    p = provider(fake)
    fake.reply("{}", eval_count=3)
    p.classify("x")
    assert p.last_usage == {"eval_count": 3}
    fake.status = 500
    with pytest.raises(OllamaError):
        p.classify("x")
    assert p.last_usage == {}
