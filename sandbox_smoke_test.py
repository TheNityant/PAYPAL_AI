"""PayPal OAuth SANDBOX-only credential check. Does NOT create or capture payments.

Usage: python sandbox_smoke_test.py
Credentials stay exclusively in your local .env.
"""
import asyncio
from dotenv import load_dotenv
from intentparity.paypal import verify_sandbox_credentials, SandboxError

async def main():
    load_dotenv()
    try:
        await verify_sandbox_credentials()
    except SandboxError as exc:
        raise SystemExit("PayPal Sandbox auth check failed: " + str(exc)) from exc
    print("SUCCESS: PayPal Sandbox OAuth authenticated.")
    print("This did NOT create an order, capture a payment, or move real money.")

if __name__ == "__main__":
    asyncio.run(main())
