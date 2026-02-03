import asyncio
import httpx
import json
from app.ucp.constants import DATAPART_CHECKOUT_KEY, PAYMENT_DATA_KEY

USER_COLOR = "\033[94m"  # Blue
FAIL_COLOR = "\033[91m"  # Red
SUCCESS_COLOR = "\033[92m" # Green
RESET = "\033[0m"

async def run_fail_demo():
    print(f"{FAIL_COLOR}=== SIMULATING 'DOUBLE SPEND' BUG ==={RESET}\n")
    
    async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
        # 1. Setup: Create Cart & Add Item
        print("1. Setting up cart...")
        resp = await client.post("/a2a", json={
            "kind": "message", "role": "user", "messageId": "setup1", "contextId": "c_fail",
            "parts": [{"kind": "data", "data": {"action": "create_checkout"}}]
        })
        cid = resp.json()["parts"][0]["data"][DATAPART_CHECKOUT_KEY]["checkout_id"]

        await client.post("/a2a", json={
            "kind": "message", "role": "user", "messageId": "setup2", "contextId": "c_fail",
            "parts": [{"kind": "data", "data": {"action": "add_to_checkout", "checkout_id": cid, "product_id": "p1", "quantity": 1}}]
        })
        print("   Cart ready. Total: $20.00\n")

        # 2. THE BUG: Send Payment Twice (Network Retry Simulation)
        payment_payload = {
            "kind": "message", "role": "user", "messageId": "pay_msg_123", "contextId": "c_fail",
            "parts": [
                {"kind": "data", "data": {"action": "complete_checkout", "checkout_id": cid}},
                {"kind": "data", "data": {PAYMENT_DATA_KEY: {"fake": "token"}}}
            ]
        }

        print(f"{USER_COLOR}User clicks 'Pay' (Attempt #1){RESET}")
        resp1 = await client.post("/a2a", json=payment_payload)
        order1 = resp1.json()["parts"][0]["data"][DATAPART_CHECKOUT_KEY].get("order_id")
        print(f"   Server: Payment processed. Order ID: {order1}")

        print(f"\n{USER_COLOR}User clicks 'Pay' AGAIN (or Network Retry) (Attempt #2){RESET}")
        resp2 = await client.post("/a2a", json=payment_payload)
        
        # 3. Analyze Results
        data2 = resp2.json()["parts"][0]["data"][DATAPART_CHECKOUT_KEY]
        order2 = data2.get("order_id")

        print(f"   Server: Payment processed. Order ID: {order2}")

        print(f"\n{FAIL_COLOR}=== ANALYSIS ==={RESET}")
        if order1 != order2:
            print(f"❌ {FAIL_COLOR}FAILURE: The server created TWO different orders for the same button click!{RESET}")
            print(f"   Order 1: {order1}")
            print(f"   Order 2: {order2}")
            print(f"   You just charged the customer twice.")
        else:
            print(f"✅ SUCCESS: The server recognized the duplicate and returned the same order.")

if __name__ == "__main__":
    asyncio.run(run_fail_demo())
