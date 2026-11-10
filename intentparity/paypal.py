"""PayPal Sandbox-only Orders v2. No production API endpoint."""
import base64
import os
import httpx

BASE = "https://api-m.sandbox.paypal.com"
class SandboxError(Exception):
    pass

async def _request(path, payload, request_id):
    user = os.getenv("PAYPAL_CLIENT_ID")
    secret = os.getenv("PAYPAL_CLIENT_SECRET")
    if not user or not secret:
        raise SandboxError("Missing sandbox credentials")
    async with httpx.AsyncClient(timeout=20) as client:
        authorization = base64.b64encode((user + ":" + secret).encode()).decode()
        token_response = await client.post(BASE + "/v1/oauth2/token",
            headers={"Authorization": "Basic " + authorization},
            data={"grant_type": "client_credentials"})
        if token_response.status_code >= 400:
            raise SandboxError("PayPal sandbox authentication failed")
        token = token_response.json()["access_token"]
        response = await client.post(BASE + path, json=payload, headers={
            "Authorization": "Bearer " + token, "Content-Type": "application/json",
            "PayPal-Request-Id": request_id})
        if response.status_code >= 400:
            raise SandboxError("PayPal Sandbox API returned HTTP " + str(response.status_code))
        return response.json()

async def create_order(amount, currency, case_id):
    return await _request("/v2/checkout/orders", {
        "intent": "CAPTURE", "purchase_units": [{"reference_id": case_id,
           "amount": {"currency_code": currency, "value": amount}}],
    }, "create-" + case_id)

async def capture_order(order_id, case_id):
    return await _request("/v2/checkout/orders/" + order_id + "/capture",
                          {}, "capture-" + case_id)
