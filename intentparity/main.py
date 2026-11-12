"""Local-only hackathon prototype. Do not expose externally: no user authentication."""
import csv
import io
import os
import uuid
from pathlib import Path
from urllib.parse import urlparse
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from .verification import compare, normalize
from .ai import interpret, is_configured
from .paypal import create_order, get_order, capture_order, SandboxError

load_dotenv()
app = FastAPI(title="IntentParity", version="0.2.0")
ROOT = Path(__file__).resolve().parent.parent
cases = {}

class Analyze(BaseModel):
    instruction: str = Field(min_length=1, max_length=1000)
    # Fault injections must never reach checkout.
    injected_amount: str | None = None
    injected_currency: str | None = None

class Approval(BaseModel):
    case_id: str
    confirmed: bool
    amount: str
    currency: str

class CaseRef(BaseModel):
    case_id: str

@app.get("/")
def home():
    return FileResponse(ROOT / "static" / "index.html")

@app.get("/api/health")
def health():
    return {"status": "ok", "environment": "sandbox_only"}

@app.get("/api/config")
def config():
    return {"ai_enabled": is_configured(),
            "sandbox_checkout_enabled": os.getenv("ENABLE_SANDBOX_CHECKOUT","").lower() == "true",
            "paypal_client_id": os.getenv("PAYPAL_CLIENT_ID","")}

@app.post("/api/analyze")
async def analyze(req: Analyze):
    model = await interpret(req.instruction)
    injected = req.injected_amount is not None or req.injected_currency is not None
    if injected:
        model = {**model, "amount": req.injected_amount if req.injected_amount is not None else model["amount"],
                 "currency": req.injected_currency if req.injected_currency is not None else model["currency"],
                 "provider": "injected_test"}
    verdict = compare(req.instruction, model.get("amount"), model.get("currency"))
    cid = str(uuid.uuid4())
    case = {"case_id":cid, "status":verdict.status, "reason":verdict.reason,
            "amount":verdict.amount, "currency":verdict.currency,
            "proposed":model, "injected":injected, "approved":False,
            "order_id":None, "approve_url":None, "capture":None}
    case["checkout_eligible"] = verdict.status == "PASS" and verdict.currency == "USD" and not injected
    cases[cid] = case
    return {k:v for k,v in case.items() if k != "capture"}

@app.post("/api/approve")
def approve(req: Approval):
    case = cases.get(req.case_id)
    if not case:
        raise HTTPException(404, "Case not found")
    if case["status"] != "PASS" or case["injected"] or not req.confirmed:
        raise HTTPException(409, "Cannot approve held or injected test cases")
    try:
        normalized = normalize(req.amount)
    except ValueError:
        raise HTTPException(409, "Invalid amount")
    if normalized != case["amount"] or req.currency.strip().upper() != case["currency"]:
        raise HTTPException(409, "Explicit confirmation must match verified details")
    case["approved"] = True
    return {"approved": True, "case_id":req.case_id}

@app.post("/api/checkout")
async def checkout(req: CaseRef):
    if os.getenv("ENABLE_SANDBOX_CHECKOUT","").lower() != "true":
        raise HTTPException(403, "Sandbox checkout disabled by operator")
    case = cases.get(req.case_id)
    if not case or case["status"] != "PASS" or case["injected"] or not case["approved"]:
        raise HTTPException(409, "Not independently verified and approved")
    if case["currency"] != "USD":
        raise HTTPException(422, "This demo only processes USD sandbox orders; INR is evaluation-only.")
    if case["order_id"]:
        return {"id":case["order_id"],"approve_url":case["approve_url"],"environment":"sandbox"}
    try:
        result = await create_order(case["amount"],case["currency"],case["case_id"])
    except SandboxError as exc:
        raise HTTPException(502, str(exc))
    case["order_id"] = result["id"]
    approval_links = [item.get("href") for item in result.get("links", [])
                      if item.get("rel") in ("approve", "payer-action")]
    approval_link = approval_links[0] if approval_links else None
    if approval_link:
        parsed = urlparse(approval_link)
        if parsed.scheme != "https" or parsed.hostname not in ("www.sandbox.paypal.com", "sandbox.paypal.com"):
            approval_link = None
    case["approve_url"] = approval_link
    return {"id": case["order_id"], "approve_url": approval_link, "environment":"sandbox"}

def _verified_capture(order, case):
    """Validate an order and its single COMPLETED capture against approved intent."""
    units = order.get("purchase_units") or []
    record = {}
    valid = False
    if len(units) == 1:
        unit = units[0]
        records = (unit.get("payments") or {}).get("captures") or []
        if len(records) == 1:
            record = records[0]
            paid = record.get("amount") or {}
            try:
                amount_matches = normalize(paid.get("value")) == case["amount"]
            except ValueError:
                amount_matches = False
            valid = (
                order.get("id") == case["order_id"]
                and order.get("status") == "COMPLETED"
                and unit.get("reference_id") == case["case_id"]
                and record.get("status") == "COMPLETED"
                and bool(record.get("id"))
                and amount_matches
                and paid.get("currency_code") == case["currency"]
            )
    return {"verified": valid, "environment": "sandbox",
            "order_id": case["order_id"],
            "capture_id": record.get("id") if valid else None,
            "paid": record.get("amount", {}) if valid else {},
            "status": "COMPLETED" if valid else "UNVERIFIED"}


def _approved_order_matches(order, case):
    """PayPal is authoritative: do not trust local state or buyer redirect alone."""
    units = order.get("purchase_units") or []
    if order.get("id") != case["order_id"] or order.get("intent") != "CAPTURE":
        return False
    if len(units) != 1 or units[0].get("reference_id") != case["case_id"]:
        return False
    amount = units[0].get("amount") or {}
    try:
        matching_total = normalize(amount.get("value")) == case["amount"]
    except ValueError:
        return False
    return matching_total and amount.get("currency_code") == case["currency"]


@app.post("/api/capture/{case_id}")
async def capture(case_id: str):
    if os.getenv("ENABLE_SANDBOX_CHECKOUT","").lower() != "true":
        raise HTTPException(403, "Sandbox checkout disabled by operator")
    case = cases.get(case_id)
    if not case or not case["approved"] or not case["order_id"] or case["injected"]:
        raise HTTPException(409, "No authorized sandbox order")
    if case["currency"] != "USD":
        raise HTTPException(422, "This demo supports USD sandbox payments only")
    if case["capture"] and case["capture"]["verified"]:
        return case["capture"]
    try:
        remote = await get_order(case["order_id"])
    except SandboxError as exc:
        raise HTTPException(502, str(exc))
    if not _approved_order_matches(remote, case):
        raise HTTPException(409, "Remote PayPal order does not match verified intent")
    if remote.get("status") == "COMPLETED":
        receipt = _verified_capture(remote, case)
        if not receipt["verified"]:
            raise HTTPException(409, "Remote completed order has a mismatched capture")
        case["capture"] = receipt
        return receipt
    if remote.get("status") != "APPROVED":
        raise HTTPException(409, "Buyer has not approved this exact PayPal sandbox order")
    try:
        captured = await capture_order(case["order_id"], case_id)
    except SandboxError as exc:
        raise HTTPException(502, str(exc))
    receipt = _verified_capture(captured, case)
    if receipt["verified"]:
        case["capture"] = receipt
    return receipt

TESTS = [
    ("Invoice Priya for $75, not $750.", "75.00", "USD"),
    ("Charge $7, not $7000.", "7.00", "USD"),
    ("Charge seventy five dollars, not seven hundred fifty dollars.", "75.00", "USD"),
    ("Bill 1,500 rupees, not 15,000 rupees.", "1500.00", "INR"),
    ("Collect $42.50.", "42.50", "USD"),
]

@app.get("/api/lab")
def lab():
    rows = []
    for instruction, expected, currency in TESTS:
        for label, amount, unit in [("correct",expected,currency),
                                    ("amount_mismatch",str(float(expected)*10),currency),
                                    ("currency_swap",expected,"INR" if currency=="USD" else "USD"),
                                    ("missing_amount",None,currency)]:
            verdict = compare(instruction,amount,unit)
            rows.append({"instruction":instruction,"scenario":label,
                         "expected_amount":expected,"expected_currency":currency,
                         "proposed_amount":amount,"proposed_currency":unit,
                         "decision":verdict.status,"reason":verdict.reason})
    return {"synthetic":True,"note":"Authored simulated proposals, not actual LLM evaluations",
            "count":len(rows),"rows":rows}

@app.get("/api/lab.csv")
def csv_report():
    rows = lab()["rows"]
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return Response(output.getvalue(),media_type="text/csv",
           headers={"Content-Disposition":'attachment; filename="synthetic-lab.csv"'})
