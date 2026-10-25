import io
import json
import urllib.error

import pytest

from audit.gemini import GeminiClient, GeminiError, _NoRedirect


SECRET = "synthetic-key-not-a-credential"


def reply(value):
    return io.BytesIO(json.dumps(value).encode())


def generated(text='{"findings": []}', finish="STOP"):
    return {"candidates": [{"finishReason": finish, "content": {"parts": [{"text": text}]}}],
            "usageMetadata": {"promptTokenCount": 11, "candidatesTokenCount": 4, "totalTokenCount": 15}}


def client(monkeypatch, outcomes, **kwargs):
    calls = []

    class Opener:
        def open(self, request, timeout):
            calls.append((request, timeout))
            value = outcomes.pop(0)
            if isinstance(value, Exception):
                raise value
            return reply(value)

    monkeypatch.setattr("audit.gemini.urllib.request.build_opener", lambda *args: Opener())
    monkeypatch.setattr("audit.gemini.time.sleep", lambda _: None)
    return GeminiClient("gemini-test", api_key=SECRET, **kwargs), calls


def test_json_request_fixed_origin_header_caps_usage(monkeypatch):
    c, calls = client(monkeypatch, [generated()], max_output_tokens=23)
    assert c.generate_json("Review supplied evidence") == {"findings": []}
    request, timeout = calls[0]
    assert request.full_url == "https://generativelanguage.googleapis.com/v1beta/models/gemini-test:generateContent"
    assert SECRET not in request.full_url
    assert request.get_header("X-goog-api-key") == SECRET
    body = json.loads(request.data)
    assert body["generationConfig"]["maxOutputTokens"] == 23
    assert body["generationConfig"]["responseMimeType"] == "application/json"
    assert timeout == 30
    assert c.usage == dict(attempted_calls=1, successful_calls=1, input_tokens=11,
                           output_tokens=4, total_tokens=15, usage_metadata_calls=1)
    assert SECRET not in repr(c)


@pytest.mark.parametrize("status,attempts", [(429, 2), (500, 2), (503, 2), (403, 1), (302, 1)])
def test_retry_only_transient_with_safe_errors(monkeypatch, status, attempts):
    errors = [urllib.error.HTTPError("https://example.test/?key=" + SECRET, status, SECRET, {}, io.BytesIO(SECRET.encode())) for _ in range(2)]
    c, calls = client(monkeypatch, errors)
    with pytest.raises(GeminiError) as exc:
        c.generate_json("test")
    assert len(calls) == attempts
    assert SECRET not in str(exc.value)
    assert exc.value.__suppress_context__


def test_call_budget_includes_retry(monkeypatch):
    error = urllib.error.HTTPError("url", 429, "quota", {}, io.BytesIO())
    c, calls = client(monkeypatch, [error], max_calls=1)
    with pytest.raises(GeminiError, match="HTTP 429"):
        c.generate_json("test")
    with pytest.raises(GeminiError, match="budget exhausted"):
        c.list_models()
    assert len(calls) == 1


def test_retry_then_success_and_list_probe(monkeypatch):
    error = urllib.error.HTTPError("url", 503, "unavailable", {}, io.BytesIO())
    c, calls = client(monkeypatch, [error, {"models": [{"name": "models/gemini-test"}]}])
    assert c.list_models() == [{"name": "models/gemini-test"}]
    assert len(calls) == 2 and c.usage["attempted_calls"] == 2
    assert c.usage["usage_metadata_calls"] == 0


@pytest.mark.parametrize("payload", [generated("not JSON"), generated("{}", "MAX_TOKENS"), {}, {"candidates": [None]},
                                     generated('"scalar"'), {"error": {"message": SECRET}}])
def test_bad_output_rejected_without_echo(monkeypatch, payload):
    c, _ = client(monkeypatch, [payload])
    with pytest.raises(GeminiError) as exc:
        c.generate_json("test")
    assert SECRET not in str(exc.value)


def test_input_and_response_size_caps(monkeypatch):
    c, calls = client(monkeypatch, [generated()], max_input_bytes=3, max_response_bytes=10)
    with pytest.raises(GeminiError, match="input budget"):
        c.generate_json("éé")
    assert calls == []
    with pytest.raises(GeminiError, match="response size"):
        c.generate_json("ok")


def test_no_redirect_to_credential_thief():
    assert _NoRedirect().redirect_request(None, None, 302, "", {}, "https://evil.test") is None


def test_environment_only_and_required_model(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(GeminiError, match="unavailable"):
        GeminiClient("gemini-test")
    monkeypatch.setenv("GEMINI_API_KEY", SECRET)
    assert GeminiClient("models/gemini-test").model == "gemini-test"
    with pytest.raises(TypeError):
        GeminiClient()
    for model in ("", "../../evil", "https://evil.test", "foo?key=bar"):
        with pytest.raises(GeminiError):
            GeminiClient(model)


@pytest.mark.parametrize("options", [{"retries": 2}, {"max_calls": 0}, {"max_output_tokens": -1},
                                    {"timeout": float("inf")}, {"api_key": "bad\nkey"}])
def test_invalid_settings_rejected(options):
    with pytest.raises(GeminiError):
        GeminiClient("gemini-test", **{**{"api_key": SECRET}, **options})


def test_transport_error_does_not_echo_credentials(monkeypatch):
    c, calls = client(monkeypatch, [urllib.error.URLError(SECRET)])
    with pytest.raises(GeminiError, match="transport failed") as exc:
        c.generate_json("test")
    assert SECRET not in str(exc.value) and len(calls) == 1
