"""PayPal client tests never contact the PayPal network."""
import asyncio
import pytest
from intentparity import paypal


def test_sandbox_is_disabled_without_explicit_opt_in(monkeypatch):
    monkeypatch.setenv("PAYPAL_CLIENT_ID", "unit-test")
    monkeypatch.setenv("PAYPAL_CLIENT_SECRET", "unit-test")
    monkeypatch.setenv("ENABLE_SANDBOX_CHECKOUT", "false")
    assert not paypal.sandbox_enabled()
    monkeypatch.setenv("ENABLE_SANDBOX_CHECKOUT", "true")
    assert paypal.sandbox_enabled()


def test_create_order_sends_pay_now_and_sandbox_context(monkeypatch):
    monkeypatch.delenv("PAYPAL_RETURN_URL", raising=False)
    monkeypatch.delenv("PAYPAL_CANCEL_URL", raising=False)
    observed = {}
    async def fake_request(path, payload=None, request_id=None, method="POST"):
        observed.update(path=path, payload=payload, request_id=request_id, method=method)
        return {"id":"SBOX123456"}
    monkeypatch.setattr(paypal,"_request",fake_request)
    result = asyncio.run(paypal.create_order("7.00","USD","case-unit-test"))
    assert result["id"] == "SBOX123456"
    assert observed["path"] == "/v2/checkout/orders"
    assert observed["request_id"] == "create-case-unit-test"
    assert observed["payload"]["intent"] == "CAPTURE"
    assert observed["payload"]["purchase_units"][0]["amount"] == {"currency_code":"USD","value":"7.00"}
    experience = observed["payload"]["payment_source"]["paypal"]["experience_context"]
    assert experience["user_action"] == "PAY_NOW"
    assert experience["shipping_preference"] == "NO_SHIPPING"


@pytest.mark.parametrize("bad",["file:///etc/passwd",
        "http://evil.example/return", "https://user:pass@evil.example/return"])
def test_unsafe_return_url_is_rejected(monkeypatch,bad):
    monkeypatch.setenv("PAYPAL_RETURN_URL",bad)
    monkeypatch.delenv("PAYPAL_CANCEL_URL",raising=False)
    with pytest.raises(paypal.SandboxError):
        asyncio.run(paypal.create_order("7.00","USD","case-id"))


def test_optional_local_return_urls(monkeypatch):
    monkeypatch.setenv("PAYPAL_RETURN_URL","http://127.0.0.1:8000/?paypal=approved")
    monkeypatch.setenv("PAYPAL_CANCEL_URL","http://localhost:8000/?paypal=cancelled")
    observed = {}
    async def fake_request(path,payload=None,request_id=None,method="POST"):
        observed.update(payload=payload)
        return {"id":"SBOX1234"}
    monkeypatch.setattr(paypal,"_request",fake_request)
    asyncio.run(paypal.create_order("7.00","USD","case-id"))
    exp = observed["payload"]["payment_source"]["paypal"]["experience_context"]
    assert exp["return_url"].startswith("http://127.0.0.1")
    assert exp["cancel_url"].startswith("http://localhost")


def test_inr_does_not_reach_paypal(monkeypatch):
    async def forbidden(*args,**kwargs):
        pytest.fail("INR must not call sandbox API")
    monkeypatch.setattr(paypal,"_request",forbidden)
    with pytest.raises(paypal.SandboxError):
        asyncio.run(paypal.create_order("7.00","INR","case-id"))


@pytest.mark.parametrize("id",["https://evil.test","../abc","", "123/456"])
def test_invalid_order_id_rejected(id):
    with pytest.raises(paypal.SandboxError):
        asyncio.run(paypal.get_order(id))


def test_get_order_does_not_post(monkeypatch):
    observed = {}
    async def fake_request(path,payload=None,request_id=None,method="POST"):
        observed.update(path=path,method=method)
        return {"status":"APPROVED"}
    monkeypatch.setattr(paypal,"_request",fake_request)
    result=asyncio.run(paypal.get_order("SBOXGET123"))
    assert result["status"] == "APPROVED"
    assert observed == {"path":"/v2/checkout/orders/SBOXGET123","method":"GET"}
