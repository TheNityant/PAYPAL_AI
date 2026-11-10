# IntentParity — PayPal AI Hackathon

**Experimental AI payment-intent verification lab and PayPal Sandbox demonstration.**

> **Status:** Hackathon MVP, not production-ready. No claims of universal financial-language understanding, real-world safety certification, or unique invention. No live funds.

## What it does

- Extracts payment amounts from a **limited** set of English financial instructions using independently testable rules.
- Compares untrusted AI proposals with source evidence and **holds** mismatches.
- Requires a user to type the exact amount and currency again before an order.
- Keeps adversarial fault-injection cases entirely outside payment authorization.
- Provides a reproducible synthetic test lab; simulated faults are **not measured AI model accuracy**.
- Optionally creates and captures PayPal **Sandbox** orders using server-side verification.

## Run locally

```bash
python -m venv .venv
# Activate the venv (Windows: .venv\\Scripts\\activate; macOS/Linux: source .venv/bin/activate)
python -m pip install -r requirements.txt
cp .env.example .env  # on PowerShell: Copy-Item .env.example .env
python -m pytest -q
python -m uvicorn intentparity.main:app --host 127.0.0.1 --port 8000
```

Visit http://127.0.0.1:8000. API documentation: http://127.0.0.1:8000/docs.

## PayPal sandbox

1. Create PayPal Sandbox REST app in the [Developer Dashboard](https://developer.paypal.com/dashboard/).
2. Put **sandbox** client ID and secret in local `.env` and set `ENABLE_SANDBOX_CHECKOUT=true`.
3. Restart the server. In the UI, run an instruction and provide explicit confirmation.
4. Order creation/capture uses PayPal **sandbox** APIs only. Complete the buyer approval in a sandbox account.
5. Never add credentials to source control. All payment endpoints are disabled unless explicitly opted in.

This prototype is **local-only and unauthenticated**. Do not deploy publicly until adding user authentication, persistence, concurrency controls, rate limiting, request origin/CSRF protection, and a security review.

## Real-model experiment (not simulated)

With a trusted local model running (for example Ollama), configure the two environment variables below in your local `.env`:

```ini
LLM_BASE_URL=http://127.0.0.1:11434/v1
LLM_MODEL=qwen2.5:3b
```

Then run:

```bash
python evaluate_llm.py
```

The script tests 15 manually authored text cases, writes an ignored local `evaluation_results.csv`, and reports baseline model correctness, unsafe proposals accepted, and false holds. **Do not interpret these results as representative payment-industry error rates**; independent human-labeled multilingual and audio cases are a future milestone.

## Experimental limitations

- Real LLM behavior has not been evaluated here. Set `LLM_BASE_URL` / `LLM_MODEL` only to a trusted operator-configured endpoint to try one.
- No automated multilingual ASR or full Hindi/Marathi parser is claimed.
- The synthetic lab is a deterministic illustration; tests provide no real-world failure rate.
- PayPal integration is coded but live Sandbox credentials/capture must still be tested.
- Checkout verification is based on a mocked test by default.
- Innovation is a hypothesis requiring comparison against academic/commercial alternatives.

## Repo structure

- `intentparity/verification.py`: conservative amount parser & gate
- `intentparity/ai.py`: optional compatible chat-completions adapter
- `intentparity/paypal.py`: Sandbox-only API
- `intentparity/main.py`: FastAPI routes and test lab
- `static/index.html`: browser interface
- `tests/`: authored safety and mocked PayPal tests
- `evaluate_llm.py`: optional real-LLM labeled text evaluation
- `.github/workflows/tests.yml`: automated PR checks

MIT license.
