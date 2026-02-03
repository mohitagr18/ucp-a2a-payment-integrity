from fastapi import APIRouter
from app.a2a.schemas import A2AMessage
from app.a2a.dispatcher import handle_message, ServiceContainer
from app.infra.store import InMemoryStore
from app.services.checkout_service import CheckoutService
from app.services.catalog_service import CatalogService
from app.services.payment_service import PaymentService
from app.infra.lock_manager import InMemoryLockManager
from app.infra.idempotency import InMemoryIdempotencyStore

router = APIRouter()

# Global singleton
store = InMemoryStore()
payment_svc = PaymentService() 
catalog_svc = CatalogService(store) 
lock_manager = InMemoryLockManager()
idempotency_store = InMemoryIdempotencyStore()

# Pass payment to checkout
checkout_svc = CheckoutService(store=store, payment=payment_svc, locks=lock_manager, idempotency=idempotency_store) 

services = ServiceContainer(
    store=store, 
    checkout=checkout_svc,
    catalog=catalog_svc, 
    payment=payment_svc
)

@router.post("/a2a")
async def a2a_jsonrpc_endpoint(payload: dict) -> dict:
    # Assume payload is the A2A message for now (simplified RPC)
    msg = A2AMessage(**payload)
    resp = await handle_message(msg, services=services)
    return resp.model_dump()
