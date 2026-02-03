import asyncio
import httpx
import json
from app.ucp.constants import DATAPART_CHECKOUT_KEY, PAYMENT_DATA_KEY

# Colors for "Chat" UI
USER_COLOR = "\033[94m"  # Blue
AGENT_COLOR = "\033[92m" # Green
RESET = "\033[0m"

async def print_card(step_name, data):
    """Pretty prints the 'Card' the agent returns."""
    print(f"\n{AGENT_COLOR}--- AGENT REPLY ({step_name}) ---{RESET}")
    
    # Extract the checkout card data
    try:
        msg = data["parts"][0]
        if msg["kind"] == "text":
            print(f"Agent says: {msg['text']}")
            return

        checkout = msg["data"].get(DATAPART_CHECKOUT_KEY)
        if not checkout:
            print("No checkout card found.")
            return

        # Render a "Text Card"
        status = checkout['status']
        total = checkout['total_cents'] / 100
        print(f"🛒  **Shopping Cart**")
        print(f"Status: [{status}]")
        print(f"Total:  ${total:.2f}")
        
        if checkout['line_items']:
            print("Items:")
            for item in checkout['line_items']:
                print(f" - Product {item['product_id']}: x{item['quantity']}")
        
        if status == "completed":
            print(f"✅ ORDER CONFIRMED! ID: {checkout['order_id']}")
        
        # Save ID for next steps
        return checkout['checkout_id']
    except Exception as e:
        print(f"Error parsing card: {e}")
        print(json.dumps(data, indent=2))
        return None

async def run_demo():
    async with httpx.AsyncClient(base_url="http://localhost:8000", timeout=10.0) as client:
        print(f"{USER_COLOR}User: 'I want to start a checkout.'{RESET}")
        
        # 1. Create
        resp = await client.post("/a2a", json={
            "kind": "message", "role": "user", "messageId": "m1", "contextId": "c1",
            "parts": [{"kind": "data", "data": {"action": "create_checkout"}}]
        })
        cid = await print_card("Created", resp.json())

        # 2. Add Item
        print(f"\n{USER_COLOR}User: 'Add 1 T-Shirt (p1) to cart.'{RESET}")
        resp = await client.post("/a2a", json={
            "kind": "message", "role": "user", "messageId": "m2", "contextId": "c1",
            "parts": [{"kind": "data", "data": {
                "action": "add_to_checkout", 
                "checkout_id": cid, 
                "product_id": "p1", 
                "quantity": 1
            }}]
        })
        await print_card("Item Added", resp.json())

        # 3. Pay
        print(f"\n{USER_COLOR}User: 'Here is my payment. Complete order.'{RESET}")
        resp = await client.post("/a2a", json={
            "kind": "message", "role": "user", "messageId": "m3", "contextId": "c1",
            "parts": [
                {"kind": "data", "data": {"action": "complete_checkout", "checkout_id": cid}},
                {"kind": "data", "data": {PAYMENT_DATA_KEY: {"fake": "token"}}}
            ]
        })
        await print_card("Payment Complete", resp.json())

if __name__ == "__main__":
    # Ensure server is running first!
    try:
        asyncio.run(run_demo())
    except Exception as e:
        print(f"Could not connect. Is the server running? ({e})")
