"""Model proposals are untrusted data, never payment authorization."""
import json
import os
import httpx
from .verification import source

async def interpret(instruction: str):
    base = os.getenv("LLM_BASE_URL", "").strip().rstrip("/")
    model = os.getenv("LLM_MODEL", "").strip()
    if not base or not model:
        v = source(instruction)
        return {"amount": v.amount, "currency": v.currency,
                "provider": "heuristic_only", "error": None}
    # Keep remote model target fixed by an operator-owned environment variable.
    prompt = ("Extract the user's intended exact checkout amount and currency. "
              "Respect negations and corrections. Output only a JSON object "
              "with amount as a decimal string and currency USD/INR; null if uncertain.")
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(base + "/chat/completions",
                headers={"Authorization": "Bearer " + os.getenv("LLM_API_KEY", "ollama")},
                json={"model": model, "temperature": 0, "messages": [
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": instruction}]})
            response.raise_for_status()
            raw = response.json()["choices"][0]["message"]["content"]
            parsed = json.loads(raw[raw.index("{"):raw.rindex("}")+1])
            return {"amount": parsed.get("amount"), "currency": parsed.get("currency"),
                    "provider": "llm:" + model, "error": None}
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        return {"amount": None, "currency": None,
                "provider": "llm:" + model, "error": type(exc).__name__}
