"""Real Nebius/model inference sanity check. No PayPal or money transfer."""
import asyncio
from dotenv import load_dotenv
from intentparity.ai import interpret, is_configured
from intentparity.verification import compare

async def main():
    load_dotenv()
    if not is_configured():
        raise SystemExit("Set LLM_PROVIDER=nebius, LLM_MODEL, and NEBIUS_API_KEY in .env first.")
    sample = "Charge $7, not $7000."
    result = await interpret(sample)
    print("Provider:", result["provider"])
    print("Model amount:", result["amount"])
    print("Model currency:", result["currency"])
    print("Error:", result["error"])
    print("Independent verifier:", compare(sample, result["amount"], result["currency"]).status)
    if result["error"]:
        raise SystemExit("Cloud inference failed; check provider, credentials, and model availability.")
    print("This is one real cloud response, not a benchmark or PayPal payment.")

if __name__ == "__main__":
    asyncio.run(main())
