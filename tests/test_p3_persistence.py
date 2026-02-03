import pytest
import os
import uuid
import asyncio
from app.infra.store import SQLiteStore
from app.domain.models import CheckoutStatus, LineItem

TEST_DB_FILE = "test_persistence.db"

@pytest.fixture
async def db_path():
    # Setup: Use a specific file
    path = f"file:{TEST_DB_FILE}" # Simplest relative path
    # Ensure clean start
    if os.path.exists(TEST_DB_FILE):
        os.remove(TEST_DB_FILE)
    
    yield TEST_DB_FILE
    
    # Teardown: Cleanup file
    if os.path.exists(TEST_DB_FILE):
        os.remove(TEST_DB_FILE)

@pytest.mark.asyncio
async def test_restart_recovery(db_path):
    """
    Phase 3 Check:
    Data written by one Store instance must be readable by a NEW instance 
    pointing to the same file (simulating a server restart).
    """
    
    # --- SESSION 1: The "Before Restart" ---
    store_1 = SQLiteStore(db_path)
    await store_1.init_db() # Create tables
    
    # Create Checkout & Add Item
    c1 = await store_1.create_checkout()
    checkout_id = c1.checkout_id
    
    # Manually add item (mimicking what service does)
    product = await store_1.get_product("p1")
    c1.line_items.append(LineItem(product.product_id, 2, product.price_cents))
    c1.total_cents = 4000
    await store_1.save_checkout(c1)
    
    print(f"Session 1: Saved checkout {checkout_id} with 2 items.")
    
    # --- "RESTART" (Session 2) ---
    # We discard store_1 and create a BRAND NEW store_2 logic
    del store_1
    
    store_2 = SQLiteStore(db_path)
    # We call init_db again (mimicking startup), it should be safe (IF NOT EXISTS)
    await store_2.init_db()
    
    # --- VERIFY ---
    # Can store_2 see what store_1 wrote?
    c2 = await store_2.get_checkout(checkout_id)
    
    assert c2 is not None, "Data lost after restart!"
    assert c2.checkout_id == checkout_id
    assert c2.total_cents == 4000
    assert len(c2.line_items) == 1
    assert c2.line_items[0].quantity == 2
    
    print("Session 2: Successfully recovered data.")
