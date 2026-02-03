from fastapi import APIRouter
from app.a2a.schemas import A2AMessage
from app.a2a.dispatcher import handle_message, ServiceContainer
from app.services.checkout_service import CheckoutService
from app.services.catalog_service import CatalogService
from app.services.payment_service import PaymentService
from app.infra.store import SQLiteStore
from app.infra.idempotency import SQLiteIdempotencyStore
from app.infra.lock_manager import InMemoryLockManager
from app.settings import settings

router = APIRouter()

# --- PHASE 3: Persistence Wiring ---

# 1. Get DB path from settings (defaults to ./app.db)
# We strip the scheme if present because aiosqlite expects a file path
db_path = settings.DATABASE_URL.replace("sqlite:///", "") 

# 2. Initialize Persistent Stores
store = SQLiteStore(db_path=db_path)
idempotency_store = SQLiteIdempotencyStore(db_path=db_path)

# 3. Initialize Logic Services
# Locks remain in-memory because they are for runtime concurrency (per process)
lock_manager = InMemoryLockManager()

payment_svc = PaymentService()
catalog_svc = CatalogService(store)

checkout_svc = CheckoutService(
    store=store, 
    payment=payment_svc,
    locks=lock_manager,
    idempotency=idempotency_store
)

# 4. Create Container
services = ServiceContainer(store, checkout_svc, catalog_svc, payment_svc)

@router.post("/a2a")
async def a2a_jsonrpc_endpoint(payload: dict) -> dict:
    msg = A2AMessage(**payload)
    resp = await handle_message(msg, services=services)
    return resp.model_dump()
