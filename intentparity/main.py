"""Local-only hackathon prototype. Do not expose externally: no user authentication."""
import csv
import io
import os
import uuid
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from .verification import compare, normalize
from .ai import interpret
from .paypal import create_order, capture_order, SandboxError

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
    return {"ai_enabled": bool(os.getenv("LLM_BASE_URL") and os.getenv("LLM_MODEL")),
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
    if case["order_id"]:
        return {"id":case["order_id"],"approve_url":case["approve_url"]}
    try:
        result = await create_order(case["amount"],case["currency"],case["case_id"])
    except SandboxError as exc:
        raise HTTPException(502, str(exc))
    case["order_id"] = result["id"]
    approval_links = [item.get("href") for item in result.get("links", [])
                      if item.get("rel") in ("approve", "payer-action")]
    approval_link = approval_links[0] if approval_links else None
    if approval_link and not approval_link.startswith(("https://www.sandbox.paypal.com/", "https://www.paypal.com/")):
        approval_link = None
    case["approve_url"] = approval_link
    return {"id": case["order_id"], "approve_url": approval_link}

@app.post("/api/capture/{case_id}")
async def capture(case_id: str):
    if os.getenv("ENABLE_SANDBOX_CHECKOUT","").lower() != "true":
        raise HTTPException(403, "Sandbox checkout disabled by operator")
    case = cases.get(case_id)
    if not case or not case["approved"] or not case["order_id"] or case["injected"]:
        raise HTTPException(409, "No authorized sandbox order")
    if case["capture"]:
        return case["capture"]
    try:
        result = await capture_order(case["order_id"], case_id)
    except SandboxError as exc:
        raise HTTPException(502, str(exc))
    units = result.get("purchase_units", [])
    if len(units) != 1:
        valid, record = False, {}
    else:
        records = units[0].get("payments",{}).get("captures",[])
        record = records[0] if len(records) == 1 else {}
        value = record.get("amount", {})
        valid = (result.get("id") == case["order_id"] and result.get("status") == "COMPLETED"
          and record.get("status") == "COMPLETED" and value.get("value") == case["amount"]
          and value.get("currency_code") == case["currency"]
          and units[0].get("reference_id") == case_id)
    case["capture"] = {"verified":valid, "order_id":case["order_id"],
                       "capture_id":record.get("id"), "paid":record.get("amount",{})}
    return case["capture"]

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
