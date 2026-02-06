"""
Shared pytest fixtures for all test modules.
"""
import pytest
import uuid
from httpx import AsyncClient, ASGITransport
from app.main import create_app
from app.infra.store import SQLiteStore
from app.infra.idempotency import SQLiteIdempotencyStore
from app.routes import a2a_rpc


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
    """
    Creates an async HTTP client bound to the FastAPI app.
    """
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
