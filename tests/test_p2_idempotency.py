import pytest
import asyncio
import uuid
from httpx import AsyncClient, ASGITransport
from app.main import create_app
from app.ucp.constants import DATAPART_CHECKOUT_KEY, PAYMENT_DATA_KEY
from app.routes import a2a_rpc
from app.infra.store import SQLiteStore
from app.infra.idempotency import SQLiteIdempotencyStore

@pytest.fixture(autouse=True)
async def reset_stores():
    """
    Resets the global store singletons to a FRESH, UNIQUE in-memory SQLite instance
    for every single test function.
    """
    # 1. Generate a random name so every test gets a completely empty, isolated DB.
    #    'mode=memory&cache=shared' ensures all connections within THIS test
    #    share the same RAM DB.
    unique_name = f"memdb_{uuid.uuid4()}"
    shared_db_uri = f"file:{unique_name}?mode=memory&cache=shared"
    
    # 2. Create fresh instances pointing to this unique URI
    new_store = SQLiteStore(shared_db_uri)
    new_idempotency = SQLiteIdempotencyStore(shared_db_uri)

    # 3. Patch the global singletons in the app
    a2a_rpc.store = new_store
    a2a_rpc.idempotency_store = new_idempotency
    
    # 4. Update the Service layer dependencies
    a2a_rpc.checkout_svc.store = new_store
    a2a_rpc.checkout_svc.idempotency = new_idempotency
    a2a_rpc.catalog_svc.store = new_store
    a2a_rpc.services.store = new_store
    a2a_rpc.services.checkout = a2a_rpc.checkout_svc 

    # 5. Initialize the tables (It will always be empty now)
    await new_store.init_db()
    await new_idempotency.init_db()

@pytest.fixture
async def client():
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

@pytest.mark.asyncio
async def test_duplicate_add_item(client):
    """
    Phase 2 Check:
    Sending the same 'add_to_checkout' message 5 times with the SAME messageId
    should result in only ONE quantity increase (Idempotency).
    """
    # 1. Create Checkout
    resp = await client.post("/a2a", json={
        "kind": "message", "role": "user", "messageId": "m_init", "contextId": "ctx_1",
        "parts": [{"kind": "data", "data": {"action": "create_checkout"}}]
    })
    assert resp.status_code == 200, f"Failed to create checkout: {resp.text}"
    cid = resp.json()["parts"][0]["data"][DATAPART_CHECKOUT_KEY]["checkout_id"]

    # 2. Send "Add Item" message 5 times with SAME messageId
    payload = {
        "kind": "message", "role": "user", "messageId": "m_add_unique_123", "contextId": "ctx_1",
        "parts": [{"kind": "data", "data": {
            "action": "add_to_checkout", 
            "checkout_id": cid, 
            "product_id": "p1", 
            "quantity": 1
        }}]
    }
    
    for _ in range(5):
        await client.post("/a2a", json=payload)

    # 3. Verify Cart State
    # Send a new message to fetch state cleanly
    resp = await client.post("/a2a", json={
        "kind": "message", "role": "user", "messageId": "m_verify_state", "contextId": "ctx_1",
        "parts": [{"kind": "data", "data": {
            "action": "add_to_checkout",  
            "checkout_id": cid, 
            "product_id": "p1", 
            "quantity": 0 # Fetch without modifying total
        }}]
    })
    
    checkout = resp.json()["parts"][0]["data"][DATAPART_CHECKOUT_KEY]
    
    # Assert total is 2000 (1 item), NOT 10000 (5 items)
    assert checkout["total_cents"] == 2000
    
    # Filter out the dummy "0 quantity" item we used to fetch the state
    real_items = [i for i in checkout["line_items"] if i["quantity"] > 0]
    
    # Now we confirm only 1 real item exists
    assert len(real_items) == 1
    assert real_items[0]["quantity"] == 1

@pytest.mark.asyncio
async def test_double_payment_safety(client):
    """
    Phase 2 Check:
    Sending 'complete_checkout' twice with the same messageId must yield 
    the EXACT SAME Order ID (no double charge).
    """
    # 1. Create & Add Item
    resp = await client.post("/a2a", json={
        "kind": "message", "role": "user", "messageId": "m_setup_pay", "contextId": "ctx_2",
        "parts": [{"kind": "data", "data": {"action": "create_checkout"}}]
    })
    cid = resp.json()["parts"][0]["data"][DATAPART_CHECKOUT_KEY]["checkout_id"]
    
    await client.post("/a2a", json={
        "kind": "message", "role": "user", "messageId": "m_add_pay", "contextId": "ctx_2",
        "parts": [{"kind": "data", "data": {"action": "add_to_checkout", "checkout_id": cid, "product_id": "p1", "quantity": 1}}]
    })

    # 2. Pay Twice (Simulate Network Retry)
    pay_payload = {
        "kind": "message", "role": "user", "messageId": "m_pay_duplicate_777", "contextId": "ctx_2",
        "parts": [
            {"kind": "data", "data": {"action": "complete_checkout", "checkout_id": cid}},
            {"kind": "data", "data": {PAYMENT_DATA_KEY: {"fake": "token"}}}
        ]
    }

    # First attempt
    resp1 = await client.post("/a2a", json=pay_payload)
    order1 = resp1.json()["parts"][0]["data"][DATAPART_CHECKOUT_KEY].get("order_id")

    # Second attempt (Duplicate)
    resp2 = await client.post("/a2a", json=pay_payload)
    order2 = resp2.json()["parts"][0]["data"][DATAPART_CHECKOUT_KEY].get("order_id")

    # Assertions
    assert order1 is not None, "First payment failed"
    assert order2 is not None, "Second payment failed"
    assert order1 == order2, f"Double spend detected! {order1} != {order2}"
