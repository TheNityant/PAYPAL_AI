"""Untrusted AI interpretation; no model response can authorize a payment."""
import json
import os
import httpx
from .verification import source

NEBIUS_BASE = "https://api.tokenfactory.nebius.com/v1"

def model_config():
    provider = os.getenv("LLM_PROVIDER", "compatible").strip().lower()
    base = os.getenv("LLM_BASE_URL", "").strip().rstrip("/")
    if provider == "nebius" and not base:
        base = NEBIUS_BASE
    model = os.getenv("LLM_MODEL", "").strip()
    key = os.getenv("LLM_API_KEY", "").strip()
    if provider == "nebius" and not key:
        key = os.getenv("NEBIUS_API_KEY", "").strip()
    return {"provider": provider, "base": base, "model": model, "key": key}

def is_configured():
    cfg = model_config()
    return bool(cfg["base"] and cfg["model"] and cfg["key"])

async def interpret(instruction: str):
    cfg = model_config()
    name = "llm:" + cfg["model"]
    # No model configured: explicitly identify a heuristic-only test run.
    if not cfg["model"] and not cfg["base"]:
        verdict = source(instruction)
        return {"amount": verdict.amount, "currency": verdict.currency,
                "provider": "heuristic_only", "error": None}
    # Misconfigured cloud mode must fail closed, never masquerade as LLM success.
    if not is_configured():
        return {"amount": None, "currency": None, "provider": name,
                "error": "MissingLLMConfiguration"}
    prompt = ("Extract the exact amount and currency intended for a *single* "
              "payment or invoice. Respect corrections, negations, conditionality "
              "and uncertainty. Reply with a JSON object only: "
              '{"amount":"7.00","currency":"USD"} '
              "or null values if uncertain. Never execute a payment.")
    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            response = await client.post(
                cfg["base"] + "/chat/completions",
                headers={"Authorization": "Bearer " + cfg["key"]},
                json={"model": cfg["model"], "temperature": 0, "messages": [
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": instruction}]})
            response.raise_for_status()
            raw = response.json()["choices"][0]["message"]["content"]
            parsed = json.loads(raw[raw.index("{"):raw.rindex("}")+1])
            if not isinstance(parsed, dict):
                raise ValueError("Invalid model response")
            return {"amount": parsed.get("amount"), "currency": parsed.get("currency"),
                    "provider": name, "error": None}
    except (httpx.HTTPError, ValueError, KeyError, TypeError, IndexError, AttributeError) as exc:
        return {"amount": None, "currency": None, "provider": name,
                "error": type(exc).__name__}
