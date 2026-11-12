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

## PayPal Sandbox end-to-end demo (no paid credits or real cards)

PayPal supplies a **free simulated-money environment** through real PayPal developer APIs.
The application uses **Orders v2** rather than pretending a payment occurred:

| Stage | Backend | Outcome |
| --- | --- | --- |
| AI proposal | `POST /api/analyze` | AI proposes amount/currency, independent verifier returns PASS/HOLD |
| Human confirmation | `POST /api/approve` | User re-enters and confirms the exact amount and currency |
| Sandbox order | `POST /api/checkout` | Creates a USD order with server-owned values and a sandbox PayPal hosted approval URL |
| Buyer approval | PayPal-hosted checkout | Personal sandbox buyer approves with mock funds |
| Read-only inspection | `GET /api/sandbox/status/{case_id}` | Server checks PayPal order status and original intent without charging |
| Server-side capture | `POST /api/capture/{case_id}` | Only if APPROVED and amount/currency/reference match; return verified capture ID and status |
| Negative test | `POST /api/analyze` with injected wrong amount | HOLD; cannot reach any payment operation |

### Set up real PayPal Sandbox

1. Sign in to the [PayPal Developer Dashboard](https://developer.paypal.com/dashboard/) and create/select a **Sandbox REST app**. Obtain the app's Client ID and Secret.
2. Go to **Testing Tools → Sandbox Accounts**. Use a **Business** account as merchant and a **Personal** account as the buyer. The dashboard normally creates both for you. Use USD-capable test accounts.
3. Copy `.env.example` to local `.env` and set:

   ```ini
   PAYPAL_CLIENT_ID=YOUR_SANDBOX_APP_CLIENT_ID
   PAYPAL_CLIENT_SECRET=YOUR_SANDBOX_APP_SECRET
   ENABLE_SANDBOX_CHECKOUT=true
   ```

4. Optionally set `PAYPAL_RETURN_URL` and `PAYPAL_CANCEL_URL` to HTTPS hosted pages (or localhost HTTP for a development-only redirect). For the two-tab demo leave them empty and manually return to the original IntentParity tab.
5. Run `python sandbox_smoke_test.py`. This authenticates via Sandbox OAuth **without transferring funds**. Then start the FastAPI app at `http://127.0.0.1:8000`.
6. Enter **Charge $7, not $7000.**, keep adversarial overrides empty, select **Analyze**, re-enter `7.00` and `USD`, tick the confirmation box and select **Approve verified intent**.
7. Select **Create PayPal Sandbox order**, then open the returned **Approve with PayPal Sandbox buyer** link. Use your **Personal Sandbox account**, never a real personal PayPal password or actual card.
8. Return to the original IntentParity tab and press **Check buyer approval**. Only after PayPal reports APPROVED press **Capture approved sandbox order**.
9. Save the order ID, capture ID, `verified: true`, `status: COMPLETED`, `USD` and `7.00` result. These are real API-issued test transaction IDs, **not real revenue**.
10. Run an injected `7000` amount. Its verdict is HOLD and the checkout button remains disabled.

### Documentation and boundaries

- [PayPal Sandbox accounts](https://developer.paypal.com/sandbox-testing/accounts)
- [PayPal Checkout integration](https://developer.paypal.com/checkout/integrate)
- [Orders API integration and buyer approval](https://developer.paypal.com/whats-an-order/)
- [Sandbox API endpoint / OAuth](https://developer.paypal.com/api/make-api-requests)
- [Orders v2 show order details](https://developer.paypal.com/sdk/orders/v2/orders-get/)

**Security scope:** This demonstration remains local-only. It does not have multi-user authentication, CSRF protections, durable order persistence or multi-worker distributed locks. The per-case in-process async lock and stable PayPal request IDs are for safe single-process demo behavior; they do not make a public production checkout secure. All API calls go to `api-m.sandbox.paypal.com` and can never move live funds. INR can be parsed in the evaluation lab, but only USD is enabled for sandbox checkout.


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
- `tests/`: authored safety, PayPal REST client and mocked checkout tests
- `sandbox_smoke_test.py`: real OAuth-only test with sandbox credentials
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
