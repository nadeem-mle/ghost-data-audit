"""Bounded, opt-in Gemini JSON transport; never assigns audit/CSV decisions.

Pass an explicit model and an in-memory key, or set GEMINI_API_KEY. No files,
credential discovery, proxy gateways, or model fallbacks are used. Token usage
is provider-reported; missing metadata is counted rather than estimated.
"""

import json
import math
import os
import re
import time
import urllib.error
import urllib.request


class GeminiError(RuntimeError):
    """A sanitized transport, budget, or response error."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class GeminiClient:
    """Single-threaded, bounded client. Retries count against max_calls."""

    def __init__(self, model, *, api_key=None, timeout=30, max_calls=4,
                 max_input_bytes=32768, max_output_tokens=1024,
                 max_response_bytes=131072, retries=1):
        if not isinstance(model, str) or not re.fullmatch(r"(?:models/)?[A-Za-z0-9][A-Za-z0-9._-]{0,127}", model):
            raise GeminiError("An explicit valid Gemini model is required")
        for value in (max_calls, max_input_bytes, max_output_tokens, max_response_bytes):
            if type(value) is not int or value <= 0:
                raise GeminiError("Budgets must be positive integers")
        if type(retries) is not int or retries not in (0, 1):
            raise GeminiError("At most one retry is permitted")
        if not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
            raise GeminiError("Timeout must be positive and finite")
        key = api_key if api_key is not None else os.environ.get("GEMINI_API_KEY")
        if not isinstance(key, str) or not key or not key.isascii() or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in key):
            raise GeminiError("GEMINI_API_KEY is unavailable or invalid")
        self.model = model.removeprefix("models/")
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
                raise GeminiError("Gemini call budget exhausted")
            request = urllib.request.Request(
                "https://generativelanguage.googleapis.com/v1beta/" + path,
                data=data, headers={"x-goog-api-key": self._key, "Content-Type": "application/json"},
                method="GET" if data is None else "POST")
            self.usage["attempted_calls"] += 1
            try:
                with self._opener.open(request, timeout=self.timeout) as response:
                    raw = response.read(self.max_response_bytes + 1)
            except urllib.error.HTTPError as error:
                status = error.code
                error.close()
                if (status == 429 or 500 <= status <= 599) and attempt < self.retries and self.usage["attempted_calls"] < self.max_calls:
                    time.sleep(0.25)
                    continue
                raise GeminiError(f"Gemini HTTP {status}") from None
            except (OSError, urllib.error.URLError, ValueError):
                raise GeminiError("Gemini transport failed") from None
            if len(raw) > self.max_response_bytes:
                raise GeminiError("Gemini response size budget exceeded")
            try:
                result = json.loads(raw)
            except (ValueError, UnicodeError):
                raise GeminiError("Gemini response is invalid JSON") from None
            if not isinstance(result, dict) or "error" in result:
                raise GeminiError("Gemini response is invalid")
            self.usage["successful_calls"] += 1
            usage = result.get("usageMetadata")
            if isinstance(usage, dict):
                self.usage["usage_metadata_calls"] += 1
                for source, target in (("promptTokenCount", "input_tokens"),
                                       ("candidatesTokenCount", "output_tokens"),
                                       ("totalTokenCount", "total_tokens")):
                    value = usage.get(source)
                    if type(value) is int and value >= 0:
                        self.usage[target] += value
            if isinstance(usage,dict):
                for source,target in (('thoughtsTokenCount','reasoning_tokens'),('cachedContentTokenCount','cached_input_tokens')):
                    if type(usage.get(source)) is int and usage[source]>=0:self.usage[target]=self.usage.get(target,0)+usage[source]
            return result
        raise GeminiError("Gemini request failed")

    def list_models(self):
        """One bounded model-list page for credential/connectivity checks."""
        result = self._request("models?pageSize=100")
        if not isinstance(result.get("models"), list):
            raise GeminiError("Gemini model list is invalid")
        return result["models"]

    def generate_json(self, prompt):
        """Return an advisory JSON object/array; reject blocked/truncated output."""
        if not isinstance(prompt, str) or not prompt or len(prompt.encode("utf-8")) > self.max_input_bytes:
            raise GeminiError("Gemini prompt is empty or exceeds input budget")
        result = self._request(f"models/{self.model}:generateContent", {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0, "maxOutputTokens": self.max_output_tokens,
                                 "responseMimeType": "application/json"}})
        try:
            candidate = result["candidates"][0]
            if candidate.get("finishReason") != "STOP":
                raise ValueError()
            parts = candidate["content"]["parts"]
            text = "".join(part["text"] for part in parts if not part.get("thought", False))
            value = json.loads(text)
            if not isinstance(value, (dict, list)):
                raise ValueError()
        except (AttributeError, KeyError, IndexError, TypeError, ValueError):
            raise GeminiError("Gemini JSON output is missing, blocked, truncated, or invalid") from None
        return value
