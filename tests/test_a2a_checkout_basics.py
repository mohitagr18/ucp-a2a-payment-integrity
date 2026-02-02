import pytest
from app.main import create_app
from app.ucp.constants import DATAPART_CHECKOUT_KEY, PAYMENT_DATA_KEY
from httpx import AsyncClient

@pytest.fixture
def client():
    app = create_app()
    return AsyncClient(app=app, base_url="http://test")

@pytest.mark.asyncio
async def test_checkout_flow(client):
    # 1. Create Checkout
    resp = await client.post("/a2a", json={
        "kind": "message", "role": "user", "messageId": "m1", "contextId": "c1",
        "parts": [{"kind": "data", "data": {"action": "create_checkout"}}]
    })
    assert resp.status_code == 200
    data = resp.json()
    checkout = data["parts"][0]["data"][DATAPART_CHECKOUT_KEY]
    cid = checkout["checkout_id"]
    assert checkout["status"] == "incomplete"

    # 2. Add Item
    resp = await client.post("/a2a", json={
        "kind": "message", "role": "user", "messageId": "m2", "contextId": "c1",
        "parts": [{"kind": "data", "data": {
            "action": "add_to_checkout", "checkout_id": cid, 
            "product_id": "p1", "quantity": 1
        }}]
    })
    checkout = resp.json()["parts"][0]["data"][DATAPART_CHECKOUT_KEY]
    assert checkout["total_cents"] == 2000
    
    # 3. Complete
    resp = await client.post("/a2a", json={
        "kind": "message", "role": "user", "messageId": "m3", "contextId": "c1",
        "parts": [
            {"kind": "data", "data": {"action": "complete_checkout", "checkout_id": cid}},
            {"kind": "data", "data": {PAYMENT_DATA_KEY: {"fake": "token"}}}
        ]
    })
    checkout = resp.json()["parts"][0]["data"][DATAPART_CHECKOUT_KEY]
    assert checkout["status"] == "completed"
    assert checkout["order_id"] is not None
