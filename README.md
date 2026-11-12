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

## Nebius cloud LLM (recommended)

IntentParity supports Nebius Token Factory through its OpenAI-compatible chat endpoint.
Set the following in a **local** `.env` (not in GitHub):

```ini
LLM_PROVIDER=nebius
LLM_MODEL=YOUR_AVAILABLE_NEBIUS_MODEL_ID
NEBIUS_API_KEY=YOUR_TOKEN_FACTORY_KEY
```

A custom `LLM_BASE_URL` is not required in Nebius mode; the adapter uses
`https://api.tokenfactory.nebius.com/v1`. Select a model actually available to
your account (see [Nebius models endpoint](https://api.tokenfactory.nebius.com/docs)).
The Nebius API key is different from cloud infrastructure credentials.

Run `python cloud_smoke_test.py` to check one **real** model response, then
`python evaluate_llm.py` for an authored 15-case text-only evaluation.
Neither command submits a payment or proves real-world model safety.

**OpenCode versus Nebius:** OpenCode is primarily an AI coding agent; OpenCode Zen
is a separate model gateway. For this application, Nebius is the simpler direct API.
Other Chat Completions-compatible endpoints can use
`LLM_PROVIDER=compatible`, `LLM_BASE_URL`, `LLM_MODEL` and `LLM_API_KEY`.
An OpenCode Zen *Responses*-only model is **not** compatible without another adapter.

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

## Real PayPal Sandbox walkthrough (no real debit/credit card required)

1. Open [PayPal Developer Dashboard](https://developer.paypal.com/dashboard/) and choose **Sandbox** under Apps & Credentials.
2. Copy the sandbox app **Client ID** and **Secret**. Do not share the secret or commit `.env`.
3. Under Testing Tools → Sandbox Accounts use a **Business** account as seller and a **Personal** account as buyer. PayPal normally creates both by default and provides fake balances/funding methods. For predictable USD tests, use two **US sandbox** accounts. Do not use real account passwords.
4. Set in your local `.env`:
   ```ini
   PAYPAL_CLIENT_ID=your_sandbox_client_id
   PAYPAL_CLIENT_SECRET=your_sandbox_secret
   ENABLE_SANDBOX_CHECKOUT=true
   ```
5. Start the app locally, open http://127.0.0.1:8000, analyze **"Charge $7, not $7000."** without any fault injection.
6. Re-enter `7.00` and `USD`, check the confirmation box and approve the verified intent.
7. Press **Create PayPal Sandbox order**, then **Approve with PayPal Sandbox buyer**. Log in with the **Personal sandbox account** credentials and approve $7.00. Never use a real card.
8. Return to IntentParity and press **Verify completed sandbox capture**. The backend first reads the authoritative PayPal order via `GET /v2/checkout/orders/{id}`, ensures that intent/amount/currency/reference ID match the original approval and the buyer approved it, then calls `POST /v2/checkout/orders/{id}/capture`.
9. Record the resulting PayPal **Order ID**, **Capture ID**, amount/currency and `verified:true`. This is a *simulated-funds real PayPal API transaction*, not real revenue.
10. Repeat with an injected wrong amount: it must HOLD and never reach order creation. The USD-only checkout demo intentionally does **not** attempt INR transactions. INR can still be analyzed locally.

**Important:** The actual live sandbox interaction must be executed with your own credentials. The automated tests use mocked PayPal responses and prove no live checkout completed. The project still lacks user accounts, durable audit storage, concurrent capture locks and CSRF/origin protection; run only locally or in an access-controlled demonstration, never as an unauthenticated public payment service.

Documentation: [Sandbox accounts](https://developer.paypal.com/sandbox-testing/accounts), [Orders API](https://developer.paypal.com/docs/api/orders/v2/), [Order read-back](https://developer.paypal.com/api/rest/integration/orders-api).
