import asyncio
from intentparity import ai

def test_nebius_provider_uses_official_endpoint_and_key(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "nebius")
    monkeypatch.setenv("LLM_MODEL", "example/test-model")
    monkeypatch.setenv("NEBIUS_API_KEY", "TEST_KEY_ONLY")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    captured = {}
    class Response:
        def raise_for_status(self): pass
        def json(self):
            return {"choices":[{"message":{"content":'{"amount":"75.00","currency":"USD"}'}}]}
    class FakeClient:
        def __init__(self, *args, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self,*args): pass
        async def post(self, url, **kwargs):
            captured["url"] = url
            captured["headers"] = kwargs["headers"]
            captured["body"] = kwargs["json"]
            return Response()
    monkeypatch.setattr(ai.httpx, "AsyncClient", FakeClient)
    result = asyncio.run(ai.interpret("Invoice Priya for $75, not $750."))
    assert result["amount"] == "75.00"
    assert result["currency"] == "USD"
    assert result["provider"] == "llm:example/test-model"
    assert captured["url"] == "https://api.tokenfactory.nebius.com/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer TEST_KEY_ONLY"
    assert captured["body"]["model"] == "example/test-model"

def test_missing_cloud_key_fails_closed(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "nebius")
    monkeypatch.setenv("LLM_MODEL", "example/test-model")
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    result = asyncio.run(ai.interpret("Charge $75."))
    assert result["amount"] is None
    assert result["error"] == "MissingLLMConfiguration"

def test_unconfigured_mode_remains_explicit_heuristic(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "compatible")
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    result = asyncio.run(ai.interpret("Charge $7, not $7000."))
    assert result["provider"] == "heuristic_only"

def test_nebius_model_config_uses_only_nebius_key(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "nebius")
    monkeypatch.setenv("LLM_MODEL", "a/model")
    monkeypatch.setenv("NEBIUS_API_KEY", "EXAMPLE_TOKEN")
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    assert ai.is_configured()
