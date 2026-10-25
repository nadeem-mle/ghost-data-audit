"""Bounded, opt-in OpenAI JSON transport with the same interface as GeminiClient.

Never assigns audit/CSV decisions. The key comes from OPENAI_API_KEY, or from a
local untracked .env (see .env.example); it is never logged or packaged. Token
usage is provider-reported; missing metadata is counted rather than estimated.
"""

import json
import math
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path


class OpenAIError(RuntimeError):
    """A sanitized transport, budget, or response error."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def load_dotenv(path=None):
    """Populate missing os.environ entries from a KEY=VALUE .env file."""
    path = Path(path) if path else Path(__file__).resolve().parents[2] / '.env'
    if not path.is_file():
        return
    for line in path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        name, value = line.split('=', 1)
        if value.strip() and name.strip() not in os.environ:
            os.environ[name.strip()] = value.strip().strip('"\'')


class OpenAIClient:
    """Single-threaded, bounded client. Retries count against max_calls."""

    def __init__(self, model=None, *, api_key=None, timeout=60, max_calls=4,
                 max_input_bytes=32768, max_output_tokens=1024,
                 max_response_bytes=262144, retries=1):
        load_dotenv()
        model = model or os.environ.get('OPENAI_MODEL')
        if not isinstance(model, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", model):
            raise OpenAIError("An explicit valid OpenAI model is required (argument or OPENAI_MODEL)")
        for value in (max_calls, max_input_bytes, max_output_tokens, max_response_bytes):
            if type(value) is not int or value <= 0:
                raise OpenAIError("Budgets must be positive integers")
        if type(retries) is not int or retries not in (0, 1):
            raise OpenAIError("At most one retry is permitted")
        if not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
            raise OpenAIError("Timeout must be positive and finite")
        key = api_key if api_key is not None else os.environ.get("OPENAI_API_KEY")
        if not isinstance(key, str) or not key or not key.isascii() or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in key):
            raise OpenAIError("OPENAI_API_KEY is unavailable or invalid")
        self.model = model
        self._key = key
        self.timeout = timeout
        self.max_calls = max_calls
        self.max_input_bytes = max_input_bytes
        self.max_output_tokens = max_output_tokens
        self.max_response_bytes = max_response_bytes
        self.retries = retries
        self.usage = dict(attempted_calls=0, successful_calls=0, input_tokens=0,
                          output_tokens=0, total_tokens=0, usage_metadata_calls=0)
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())

    def _request(self, path, payload=None):
        data = None if payload is None else json.dumps(payload, ensure_ascii=True).encode("utf-8")
        for attempt in range(self.retries + 1):
            if self.usage["attempted_calls"] >= self.max_calls:
                raise OpenAIError("OpenAI call budget exhausted")
            request = urllib.request.Request(
                "https://api.openai.com/v1/" + path, data=data,
                headers={"Authorization": "Bearer " + self._key, "Content-Type": "application/json"},
                method="GET" if data is None else "POST")
            self.usage["attempted_calls"] += 1
            try:
                with self._opener.open(request, timeout=self.timeout) as response:
                    raw = response.read(self.max_response_bytes + 1)
            except urllib.error.HTTPError as error:
                status = error.code
                error.close()
                if (status == 429 or 500 <= status <= 599) and attempt < self.retries and self.usage["attempted_calls"] < self.max_calls:
                    time.sleep(1.0)
                    continue
                raise OpenAIError(f"OpenAI HTTP {status}") from None
            except (OSError, urllib.error.URLError, ValueError):
                raise OpenAIError("OpenAI transport failed") from None
            if len(raw) > self.max_response_bytes:
                raise OpenAIError("OpenAI response size budget exceeded")
            try:
                result = json.loads(raw)
            except (ValueError, UnicodeError):
                raise OpenAIError("OpenAI response is invalid JSON") from None
            if not isinstance(result, dict) or "error" in result:
                raise OpenAIError("OpenAI response is invalid")
            self.usage["successful_calls"] += 1
            usage = result.get("usage")
            if isinstance(usage, dict):
                self.usage["usage_metadata_calls"] += 1
                for source, target in (("prompt_tokens", "input_tokens"),
                                       ("completion_tokens", "output_tokens"),
                                       ("total_tokens", "total_tokens")):
                    value = usage.get(source)
                    if type(value) is int and value >= 0:
                        self.usage[target] += value
                reasoning = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens")
                cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens")
                if type(reasoning) is int and reasoning >= 0:
                    self.usage["reasoning_tokens"] = self.usage.get("reasoning_tokens", 0) + reasoning
                if type(cached) is int and cached >= 0:
                    self.usage["cached_input_tokens"] = self.usage.get("cached_input_tokens", 0) + cached
            return result
        raise OpenAIError("OpenAI request failed")

    def list_models(self):
        """One bounded model-list call for credential/connectivity checks."""
        result = self._request("models")
        if not isinstance(result.get("data"), list):
            raise OpenAIError("OpenAI model list is invalid")
        return result["data"]

    def generate_json(self, prompt):
        """Return an advisory JSON object/array; reject refused/truncated output."""
        if not isinstance(prompt, str) or not prompt or len(prompt.encode("utf-8")) > self.max_input_bytes:
            raise OpenAIError("OpenAI prompt is empty or exceeds input budget")
        result = self._request("chat/completions", {
            "model": self.model,
            "messages": [{"role": "system", "content": "Reply with a single JSON object only."},
                         {"role": "user", "content": prompt}],
            "max_completion_tokens": self.max_output_tokens,
            "response_format": {"type": "json_object"}})
        try:
            choice = result["choices"][0]
            if choice.get("finish_reason") != "stop" or choice["message"].get("refusal"):
                raise ValueError()
            value = json.loads(choice["message"]["content"])
            if not isinstance(value, (dict, list)):
                raise ValueError()
        except (AttributeError, KeyError, IndexError, TypeError, ValueError):
            raise OpenAIError("OpenAI JSON output is missing, refused, truncated, or invalid") from None
        return value
