from fastapi.testclient import TestClient
from intentparity import main
import pytest

@pytest.fixture
def client(monkeypatch):
    main.cases.clear()
    main.case_locks.clear()
    monkeypatch.setenv("PAYPAL_CLIENT_ID", "mock_client_id")
    monkeypatch.setenv("PAYPAL_CLIENT_SECRET", "mock_secret")
    monkeypatch.delenv("ENABLE_SANDBOX_CHECKOUT", raising=False)
    return TestClient(main.app)

def test_mismatched_injection_is_held(client):
    r = client.post("/api/analyze", json={"instruction":"Charge $7, not $7000.",
        "injected_amount":"7000","injected_currency":"USD"})
    assert r.status_code == 200 and r.json()["status"] == "HOLD"

def test_injected_correct_proposal_cannot_be_approved(client):
    case = client.post("/api/analyze",json={"instruction":"Charge $7, not $7000.",
        "injected_amount":"7","injected_currency":"USD"}).json()
    assert case["status"] == "PASS"
    r = client.post("/api/approve",json={"case_id":case["case_id"],"confirmed":True,
        "amount":"7","currency":"USD"})
    assert r.status_code == 409

def test_payment_disabled_by_default(client):
    case = client.post("/api/analyze", json={"instruction":"Charge $7, not $7000."}).json()
    ok = client.post("/api/approve",json={"case_id":case["case_id"],"confirmed":True,
        "amount":"7","currency":"USD"})
    assert ok.status_code == 200
    assert client.post("/api/checkout",json={"case_id":case["case_id"]}).status_code == 403

def test_checkout_requires_approval(client,monkeypatch):
    monkeypatch.setenv("ENABLE_SANDBOX_CHECKOUT","true")
    case = client.post("/api/analyze",json={"instruction":"Charge $7, not $7000."}).json()
    assert client.post("/api/checkout",json={"case_id":case["case_id"]}).status_code == 409

def test_mock_sandbox_round_trip(client,monkeypatch):
    monkeypatch.setenv("ENABLE_SANDBOX_CHECKOUT","true")
    async def fake_order(amount,currency,case_id):
        assert amount == "7.00"
        return {"id":"SANDBOXFAKE123"}
    async def fake_capture(order_id,case_id):
        return {"id":order_id,"status":"COMPLETED","purchase_units":[{
            "reference_id":case_id,"payments":{"captures":[{"id":"CAPTURE-FAKE",
            "status":"COMPLETED","amount":{"currency_code":"USD","value":"7.00"}}]}}]}
    async def fake_get_order(order_id):
        return {"id": order_id, "intent": "CAPTURE", "status": "APPROVED",
            "purchase_units": [{"reference_id": case_id_box["value"],
                "amount": {"currency_code": "USD", "value": "7.00"}}]}
    case_id_box = {"value": None}
    monkeypatch.setattr(main,"get_order",fake_get_order)
    monkeypatch.setattr(main,"create_order",fake_order)
    monkeypatch.setattr(main,"capture_order",fake_capture)
    case = client.post("/api/analyze",json={"instruction":"Charge $7, not $7000."}).json()
    cid=case["case_id"]
    case_id_box["value"] = cid
    assert client.post("/api/approve",json={"case_id":cid,"confirmed":True,
        "amount":"7","currency":"USD"}).status_code==200
    assert client.post("/api/checkout",json={"case_id":cid}).json()["id"]=="SANDBOXFAKE123"
    assert client.post("/api/capture/"+cid).json()["verified"] is True

def test_lab_is_explicitly_synthetic(client):
    report = client.get("/api/lab").json()
    assert report["synthetic"] is True
    assert report["count"] == 20
    assert client.get("/api/lab.csv").status_code == 200

def test_inr_verification_cannot_be_checked_out(client, monkeypatch):
    monkeypatch.setenv("ENABLE_SANDBOX_CHECKOUT", "true")
    a = client.post("/api/analyze",json={"instruction":"Bill 1,500 rupees, not 15,000 rupees."}).json()
    assert a["status"] == "PASS" and a["currency"] == "INR"
    assert a["checkout_eligible"] is False
    approved = client.post("/api/approve",json={
        "case_id":a["case_id"],"confirmed":True,"amount":"1500","currency":"INR"})
    assert approved.status_code == 200
    assert client.post("/api/checkout",json={"case_id":a["case_id"]}).status_code == 422


@pytest.mark.parametrize("order_status", ["CREATED","PAYER_ACTION_REQUIRED","VOIDED"])
def test_unapproved_remote_order_is_never_captured(client, monkeypatch, order_status):
    monkeypatch.setenv("ENABLE_SANDBOX_CHECKOUT", "true")
    async def fake_create(amount,currency,case_id):return {"id":"SANDBOXTEST123"}
    async def fake_get(order_id):
        return {"id":order_id,"intent":"CAPTURE","status":order_status,
            "purchase_units":[{"reference_id":the_id["value"],
                "amount":{"value":"7.00","currency_code":"USD"}}]}
    async def forbidden_capture(*args):pytest.fail("Unapproved order must not be captured")
    the_id={"value":None}
    monkeypatch.setattr(main,"create_order",fake_create)
    monkeypatch.setattr(main,"get_order",fake_get)
    monkeypatch.setattr(main,"capture_order",forbidden_capture)
    a=client.post("/api/analyze",json={"instruction":"Charge $7, not $7000."}).json()
    the_id["value"]=a["case_id"]
    assert client.post("/api/approve",json={"case_id":a["case_id"],
        "confirmed":True,"amount":"7","currency":"USD"}).status_code==200
    assert client.post("/api/checkout",json={"case_id":a["case_id"]}).status_code==200
    assert client.post("/api/capture/"+a["case_id"]).status_code==409


@pytest.mark.parametrize("tamper", ["amount","currency","reference_id","intent"])
def test_changed_paypal_order_is_blocked(client, monkeypatch, tamper):
    monkeypatch.setenv("ENABLE_SANDBOX_CHECKOUT","true")
    async def fake_create(amount,currency,case_id):return {"id":"SANDBOXTEST123"}
    async def fake_get(order_id):
        order={"id":order_id,"intent":"CAPTURE","status":"APPROVED",
            "purchase_units":[{"reference_id":identity["id"],
                "amount":{"value":"7.00","currency_code":"USD"}}]}
        if tamper=="amount":order["purchase_units"][0]["amount"]["value"]="7000.00"
        if tamper=="currency":order["purchase_units"][0]["amount"]["currency_code"]="EUR"
        if tamper=="reference_id":order["purchase_units"][0]["reference_id"]="wrong-case"
        if tamper=="intent":order["intent"]="AUTHORIZE"
        return order
    async def forbidden_capture(*args):pytest.fail("Tampered PayPal order must not capture")
    identity={"id":None}
    monkeypatch.setattr(main,"create_order",fake_create)
    monkeypatch.setattr(main,"get_order",fake_get)
    monkeypatch.setattr(main,"capture_order",forbidden_capture)
    a=client.post("/api/analyze",json={"instruction":"Charge $7, not $7000."}).json()
    identity["id"]=a["case_id"]
    client.post("/api/approve",json={"case_id":a["case_id"],"confirmed":True,
                                   "amount":"7","currency":"USD"})
    client.post("/api/checkout",json={"case_id":a["case_id"]})
    assert client.post("/api/capture/"+a["case_id"]).status_code==409

def test_read_only_status_never_calls_capture(client, monkeypatch):
    monkeypatch.setenv("ENABLE_SANDBOX_CHECKOUT", "true")
    identity = {"id": None}
    async def fake_create(amount, currency, case_id):
        return {"id":"SBOXSTATUS123", "links":[
            {"rel":"payer-action","href":"https://www.sandbox.paypal.com/checkoutnow?token=SBOXSTATUS123"}]}
    async def fake_get(order_id):
        return {"id":order_id, "intent":"CAPTURE","status":"PAYER_ACTION_REQUIRED",
                "purchase_units":[{"reference_id":identity["id"],
                     "amount":{"currency_code":"USD","value":"7.00"}}]}
    async def never_capture(*args):
        pytest.fail("read-only status request must never capture")
    monkeypatch.setattr(main, "create_order", fake_create)
    monkeypatch.setattr(main, "get_order", fake_get)
    monkeypatch.setattr(main, "capture_order", never_capture)
    a = client.post("/api/analyze",json={"instruction":"Charge $7, not $7000."}).json()
    identity["id"] = a["case_id"]
    client.post("/api/approve",json={
        "case_id":a["case_id"],"confirmed":True,"amount":"7","currency":"USD"})
    created = client.post("/api/checkout",json={"case_id":a["case_id"]}).json()
    assert created["approve_url"].startswith("https://www.sandbox.paypal.com/")
    status = client.get("/api/sandbox/status/"+a["case_id"]).json()
    assert status["buyer_approved"] is False
    assert status["captured"] is False
    assert status["paypal_status"] == "PAYER_ACTION_REQUIRED"


def test_external_paypal_link_is_rejected(client, monkeypatch):
    monkeypatch.setenv("ENABLE_SANDBOX_CHECKOUT", "true")
    async def fake_create(*args):
        return {"id":"SBOXLINK123","links":[
            {"rel":"payer-action","href":"https://www.paypal.com/checkoutnow?token=SBOXLINK123"}]}
    monkeypatch.setattr(main, "create_order", fake_create)
    a = client.post("/api/analyze",json={"instruction":"Charge $7, not $7000."}).json()
    client.post("/api/approve",json={"case_id":a["case_id"],"confirmed":True,
                                    "amount":"7","currency":"USD"})
    assert client.post("/api/checkout",json={"case_id":a["case_id"]}).json()["approve_url"] is None


def test_order_creation_is_idempotent(client, monkeypatch):
    monkeypatch.setenv("ENABLE_SANDBOX_CHECKOUT", "true")
    count = {"n":0}
    async def fake_create(*args):
        count["n"] += 1
        return {"id":"SBOXIDEMPOTENT123"}
    monkeypatch.setattr(main, "create_order", fake_create)
    a = client.post("/api/analyze",json={"instruction":"Charge $7, not $7000."}).json()
    client.post("/api/approve",json={"case_id":a["case_id"],"confirmed":True,
                                    "amount":"7","currency":"USD"})
    assert client.post("/api/checkout",json={"case_id":a["case_id"]}).status_code == 200
    assert client.post("/api/checkout",json={"case_id":a["case_id"]}).status_code == 200
    assert count["n"] == 1


def test_status_rejects_tampered_remote_amount(client, monkeypatch):
    monkeypatch.setenv("ENABLE_SANDBOX_CHECKOUT", "true")
    async def fake_create(*args): return {"id":"SBOXTAMPER123"}
    async def fake_get(order_id):
        return {"id":order_id,"intent":"CAPTURE","status":"APPROVED",
          "purchase_units":[{"reference_id":identity["id"],
            "amount":{"value":"7000.00","currency_code":"USD"}}]}
    identity={"id":None}
    monkeypatch.setattr(main,"create_order",fake_create)
    monkeypatch.setattr(main,"get_order",fake_get)
    a=client.post("/api/analyze",json={"instruction":"Charge $7, not $7000."}).json()
    identity["id"]=a["case_id"]
    client.post("/api/approve",json={
        "case_id":a["case_id"],"confirmed":True,"amount":"7","currency":"USD"})
    client.post("/api/checkout",json={"case_id":a["case_id"]})
    assert client.get("/api/sandbox/status/"+a["case_id"]).status_code == 409
