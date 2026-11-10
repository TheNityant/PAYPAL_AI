from fastapi.testclient import TestClient
from intentparity import main
import pytest

@pytest.fixture
def client(monkeypatch):
    main.cases.clear()
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
        return {"id":"SANDBOX-FAKE"}
    async def fake_capture(order_id,case_id):
        return {"id":order_id,"status":"COMPLETED","purchase_units":[{
            "reference_id":case_id,"payments":{"captures":[{"id":"CAPTURE-FAKE",
            "status":"COMPLETED","amount":{"currency_code":"USD","value":"7.00"}}]}}]}
    monkeypatch.setattr(main,"create_order",fake_order)
    monkeypatch.setattr(main,"capture_order",fake_capture)
    case = client.post("/api/analyze",json={"instruction":"Charge $7, not $7000."}).json()
    cid=case["case_id"]
    assert client.post("/api/approve",json={"case_id":cid,"confirmed":True,
        "amount":"7","currency":"USD"}).status_code==200
    assert client.post("/api/checkout",json={"case_id":cid}).json()["id"]=="SANDBOX-FAKE"
    assert client.post("/api/capture/"+cid).json()["verified"] is True

def test_lab_is_explicitly_synthetic(client):
    report = client.get("/api/lab").json()
    assert report["synthetic"] is True
    assert report["count"] == 20
    assert client.get("/api/lab.csv").status_code == 200
