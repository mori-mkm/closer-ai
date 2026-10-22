"""Local Ollama adapter for the objection classifier (provider v0.1). Transport only.

See docs/ai/OLLAMA_CLASSIFICATION_PROVIDER_V0_1.md. Implements `ClassificationProvider`: sends the
classifier's prompt unchanged to Ollama's native `/api/generate` and returns the model's JSON object.
Prompt semantics, parsing of the output contract and validation stay in `objection_classifier`.

- Local only: `base_url` must be plain http on a loopback host; redirects are refused and
  environment/system proxies are ignored, so a transcript cannot leave the machine by configuration.
- One request, no retry, no fallback model, no response repair: model content that is not a JSON
  object raises `MalformedResponseError` (model compliance is measured, not hidden).
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit

from closer_ai.ai.objection_classifier import MalformedResponseError

DEFAULT_BASE_URL = "http://127.0.0.1:11434"
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
_USAGE_KEYS = ("prompt_eval_count", "eval_count", "total_duration", "load_duration", "prompt_eval_duration",
               "eval_duration")


class OllamaError(RuntimeError):
    """Transport failure: unreachable server, timeout, HTTP error or malformed Ollama API response."""


class _RefuseRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None  # urllib then raises HTTPError for the 3xx instead of following it


# No ProxyHandler entries: HTTP(S)_PROXY and system proxy settings are not used.
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), _RefuseRedirect)


def check_local_url(base_url: str) -> str:
    """Return `base_url` without a trailing slash if it is http on a loopback host; else ValueError."""
    parts = urlsplit(base_url)
    try:
        _ = parts.port  # raises ValueError on a non-numeric or out-of-range port
    except ValueError as exc:
        raise ValueError(f"invalid port in base_url {base_url!r}") from exc
    if parts.scheme != "http" or parts.hostname not in LOOPBACK_HOSTS or parts.username or parts.password:
        raise ValueError(f"Ollama provider v0.1 is local-only (http on {sorted(LOOPBACK_HOSTS)}); got {base_url!r}")
    if parts.path.strip("/") or parts.query or parts.fragment:
        raise ValueError(f"base_url must have no path, query or fragment; got {base_url!r}")
    return base_url.rstrip("/")


class OllamaClassificationProvider:
    name = "ollama"

    def __init__(self, model: str, base_url: str = DEFAULT_BASE_URL, timeout: float = 300.0,
                 num_ctx: int = 16384, keep_alive: str | None = None) -> None:
        if not model:
            raise ValueError("model is required")
        self.model = model
        self.base_url = check_local_url(base_url)
        self.timeout = timeout
        # ponytail: Ollama silently truncates prompts longer than num_ctx (default 2-4k) — size it
        # to the largest arm; compare `last_usage["prompt_eval_count"]` when in doubt.
        self.num_ctx = num_ctx
        # How long Ollama keeps the model loaded after a request (e.g. "30m"); None = Ollama's default (5 min).
        # The live runtime sets it so a quiet stretch of a call does not pay a model reload.
        self.keep_alive = keep_alive
        # Observational usage of the latest classify() call (reset at each call; single-threaded).
        self.last_usage: dict[str, Any] = {}

    @property
    def config(self) -> dict[str, Any]:
        """Generation configuration for run provenance (no secrets; not part of the prompt digest)."""
        c = {"base_url": self.base_url, "timeout": self.timeout, "format": "json", "think": False,
             "temperature": 0, "num_ctx": self.num_ctx}
        return c if self.keep_alive is None else {**c, "keep_alive": self.keep_alive}

    def classify(self, prompt: str, schema: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
        """`schema`: a JSON schema Ollama enforces on the output (structured outputs) instead of plain JSON."""
        self.last_usage = {}
        c = self.config
        request_body = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "format": dict(schema) if schema is not None else c["format"],
            "think": c["think"],
            "options": {"temperature": c["temperature"], "num_ctx": c["num_ctx"]},
        }
        if self.keep_alive is not None:
            request_body["keep_alive"] = self.keep_alive
        body = json.dumps(request_body).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/api/generate", data=body, headers={"Content-Type": "application/json"}
        )
        try:
            with _OPENER.open(request, timeout=self.timeout) as http:
                payload = http.read()
        except urllib.error.HTTPError as exc:
            raise OllamaError(f"Ollama HTTP {exc.code}: {exc.reason}") from exc
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            raise OllamaError(f"Ollama unreachable at {self.base_url}: {exc}") from exc

        try:
            api = json.loads(payload)
        except ValueError as exc:
            raise OllamaError("Ollama API response is not JSON") from exc
        if not isinstance(api, dict) or not isinstance(api.get("response"), str):
            raise OllamaError("Ollama API response has no string 'response' field")
        if api.get("done") is not True:
            raise OllamaError(f"Ollama generation not done (done_reason={api.get('done_reason')!r})")
        self.last_usage = {k: api[k] for k in _USAGE_KEYS if k in api}

        try:
            content = json.loads(api["response"])
        except ValueError as exc:
            raise MalformedResponseError(f"model output is not JSON: {exc}") from exc
        if not isinstance(content, dict):
            raise MalformedResponseError(f"model output is JSON {type(content).__name__}, not an object")
        return content
