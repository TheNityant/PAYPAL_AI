"""PayPal REST Orders v2 client. SANDBOX ONLY: never targets production money.

Payment creation and capture are only called by IntentParity's approved intent gate.
No credentials or raw access tokens are returned to the browser.
"""
import base64
import os
import re
from urllib.parse import urlsplit
import httpx

BASE = "https://api-m.sandbox.paypal.com"
ORDER_ID = re.compile(r"[A-Za-z0-9-]{5,64}")

class SandboxError(Exception):
    """Safe-to-display error. Does not contain credentials or response bodies."""


def sandbox_enabled():
    return (os.getenv("ENABLE_SANDBOX_CHECKOUT", "").lower() == "true"
            and bool(os.getenv("PAYPAL_CLIENT_ID"))
            and bool(os.getenv("PAYPAL_CLIENT_SECRET")))


def _callback_url(variable):
    """A redirect is optional. Never trust unvalidated URL environment values."""
    value = os.getenv(variable, "").strip()
    if not value:
        return None
    parsed = urlsplit(value)
    valid = parsed.scheme == "https" or (
        parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1"})
    if not valid or not parsed.hostname or parsed.username or parsed.password:
        raise SandboxError(variable + " must be HTTPS or local loopback HTTP")
    return value


async def _token(client):
    user = os.getenv("PAYPAL_CLIENT_ID", "")
    secret = os.getenv("PAYPAL_CLIENT_SECRET", "")
    if not user or not secret:
        raise SandboxError("Missing PayPal Sandbox credentials")
    auth = base64.b64encode((user + ":" + secret).encode()).decode()
    response = await client.post(
        BASE + "/v1/oauth2/token",
        headers={"Authorization": "Basic " + auth},
        data={"grant_type": "client_credentials"},
    )
    if response.status_code >= 400:
        raise SandboxError("PayPal Sandbox OAuth authentication failed (HTTP "
                           + str(response.status_code) + ")")
    token = response.json().get("access_token")
    if not token:
        raise SandboxError("PayPal Sandbox did not supply an OAuth access token")
    return token


async def verify_sandbox_credentials():
    """Read-only OAuth smoke test; cannot create or capture any order."""
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            await _token(client)
            return True
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        raise SandboxError("PayPal Sandbox authentication request failed") from exc


async def _request(path, payload=None, request_id=None, method="POST"):
    if not path.startswith("/v2/checkout/orders"):
        raise SandboxError("Unsupported PayPal API path")
    try:
        async with httpx.AsyncClient(timeout=25) as client:
            token = await _token(client)
            headers = {"Authorization": "Bearer " + token}
            if method == "GET":
                response = await client.get(BASE + path, headers=headers)
            elif method == "POST" and request_id:
                headers["Content-Type"] = "application/json"
                headers["PayPal-Request-Id"] = request_id
                response = await client.post(BASE + path, json=payload or {}, headers=headers)
            else:
                raise SandboxError("Unsupported PayPal API request")
            if response.status_code >= 400:
                raise SandboxError("PayPal Sandbox Orders API returned HTTP "
                                   + str(response.status_code))
            return response.json()
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        raise SandboxError("PayPal Sandbox request failed or returned invalid data") from exc


async def create_order(amount, currency, case_id):
    if currency != "USD":
        raise SandboxError("Only USD sandbox checkout is enabled")
    body = {
        "intent": "CAPTURE",
        "purchase_units": [{
            "reference_id": case_id,
            "description": "IntentParity verified AI payment instruction (SANDBOX)",
            "amount": {"currency_code": currency, "value": amount},
        }],
    }
    # Native PayPal-hosted approval link (rel=payer-action) is returned by create.
    # Optional return/cancel URLs improve the redirect journey for a public demo.
    return_url = _callback_url("PAYPAL_RETURN_URL")
    cancel_url = _callback_url("PAYPAL_CANCEL_URL")
    experience = {
        "brand_name": "IntentParity Sandbox",
        "user_action": "PAY_NOW",
        "shipping_preference": "NO_SHIPPING",
    }
    if return_url:
        experience["return_url"] = return_url
    if cancel_url:
        experience["cancel_url"] = cancel_url
    body["payment_source"] = {"paypal": {"experience_context": experience}}
    return await _request("/v2/checkout/orders", body, "create-" + case_id)


async def get_order(order_id):
    if not ORDER_ID.fullmatch(str(order_id)):
        raise SandboxError("Malformed sandbox order ID")
    return await _request("/v2/checkout/orders/" + order_id, method="GET")


async def capture_order(order_id, case_id):
    if not ORDER_ID.fullmatch(str(order_id)):
        raise SandboxError("Malformed sandbox order ID")
    return await _request(
        "/v2/checkout/orders/" + order_id + "/capture", {},
        "capture-" + case_id)
