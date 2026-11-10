"""Evaluate *actual* configured LLM responses against labeled authored text cases.

Requires LLM_BASE_URL and LLM_MODEL; exits instead of inventing performance.
No checkout calls. Not a representative multilingual population sample.
"""
import asyncio
import csv
import json
import os
from pathlib import Path
from dotenv import load_dotenv
from intentparity.ai import interpret
from intentparity.verification import compare, normalize

CASES = [
    ("Charge $7, not $7000.", "7.00", "USD"),
    ("Invoice Priya for $75, not $750.", "75.00", "USD"),
    ("Bill 1,500 rupees, not 15,000 rupees.", "1500.00", "INR"),
    ("Collect $42.50.", "42.50", "USD"),
    ("Invoice for seventy five dollars, not seven hundred fifty dollars.", "75.00", "USD"),
    ("Charge seven dollars, not seventy dollars.", "7.00", "USD"),
    ("Bill $99.99.", "99.99", "USD"),
    ("Collect 2500 rupees.", "2500.00", "INR"),
    ("Charge $7000, not $7.", "7000.00", "USD"),
    ("Bill twelve dollars, not twenty dollars.", "12.00", "USD"),
    ("Charge around $75.", None, None),
    ("Refund $25.", None, None),
    ("Charge $7 or $9.", None, None),
    ("Charge $7 only if the item arrives.", None, None),
    ("Charge $7 per month.", None, None),
]

async def run():
    load_dotenv()
    if not (os.getenv("LLM_BASE_URL") and os.getenv("LLM_MODEL")):
        raise SystemExit("Configure LLM_BASE_URL and LLM_MODEL first. No simulated performance numbers.")
    rows = []
    for instruction, expected_amount, expected_currency in CASES:
        proposal = await interpret(instruction)
        proposed_amount, proposed_currency = proposal.get("amount"), proposal.get("currency")
        try:
            canonical = normalize(proposed_amount)
        except ValueError:
            canonical = None
        baseline_correct = (canonical == expected_amount and
                            (str(proposed_currency).upper() if proposed_currency else None) == expected_currency)
        decision = compare(instruction, proposed_amount, proposed_currency)
        dangerous = expected_amount is None or not baseline_correct
        rows.append({
            "instruction": instruction, "expected_amount": expected_amount or "",
            "expected_currency": expected_currency or "",
            "model_amount": proposed_amount or "", "model_currency": proposed_currency or "",
            "model_provider": proposal.get("provider"), "model_error": proposal.get("error") or "",
            "baseline_correct": baseline_correct, "verifier_decision": decision.status,
            "unsafe_proposal_accepted": dangerous and decision.status == "PASS",
            "false_hold": bool(expected_amount is not None and baseline_correct and decision.status == "HOLD"),
        })
    output = Path("evaluation_results.csv")
    with output.open("w", encoding="utf-8", newline="") as f:
        w=csv.DictWriter(f, fieldnames=rows[0].keys()); w.writeheader(); w.writerows(rows)
    print(json.dumps({
        "type": "authored_text_cases_real_llm_no_payment",
        "model": os.getenv("LLM_MODEL"), "cases": len(rows),
        "baseline_correct": sum(r["baseline_correct"] for r in rows),
        "unsafe_proposals_accepted": sum(r["unsafe_proposal_accepted"] for r in rows),
        "false_holds": sum(r["false_hold"] for r in rows),
        "csv": str(output),
    }, indent=2))

if __name__ == "__main__":
    asyncio.run(run())
