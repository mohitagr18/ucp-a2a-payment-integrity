from app.infra.store import Store
from app.domain.models import Checkout, LineItem, CheckoutStatus
from app.domain.errors import DuplicateOrderError, StateConflictError
from app.infra.lock_manager import LockManager, InMemoryLockManager
from app.infra.idempotency import IdempotencyStore, IdempotencyKey, InMemoryIdempotencyStore
from app.settings import settings

class CheckoutService:
    def __init__(
        self, 
        *, 
        store: Store, 
        payment, # kept generic to avoid circular imports in this snippet
        locks: LockManager | None = None,
        idempotency: IdempotencyStore | None = None,
    ) -> None:
        self.store = store
        self.payment = payment
        # Default to memory implementations if not provided (Phase 2 scaffolds)
        self.locks = locks or InMemoryLockManager()
        self.idempotency = idempotency or InMemoryIdempotencyStore()

    async def create_checkout(self) -> Checkout:
        return await self.store.create_checkout()

    async def add_to_checkout(
        self,
        *,
        context_id: str,
        message_id: str,
        checkout_id: str,
        product_id: str,
        quantity: int,
    ) -> Checkout:
        
        # --- UNSAFE MODE (For Baseline Experiments) ---
        if settings.SAFETY_MODE == "off":
            checkout = await self.store.get_checkout(checkout_id)
            product = await self.store.get_product(product_id)
            checkout.line_items.append(LineItem(product.product_id, quantity, product.price_cents))
            checkout.total_cents += (quantity * product.price_cents)
            await self.store.save_checkout(checkout)
            return checkout

        # --- HARDENED MODE ---
        key = IdempotencyKey(context_id, message_id, "add_to_checkout")
        cached = await self.idempotency.get(key)
        if cached:
            return await self.store.get_checkout(checkout_id)

        async with self.locks.lock(checkout_id):
            checkout = await self.store.get_checkout(checkout_id)
            
            # CRITICAL CHECK: Don't allow adding items if already paid!
            if checkout.status == CheckoutStatus.COMPLETED:
                # Return current state without changes
                return checkout
                
            product = await self.store.get_product(product_id)
            checkout.line_items.append(LineItem(product.product_id, quantity, product.price_cents))
            checkout.total_cents += (quantity * product.price_cents)
            
            await self.store.save_checkout(checkout)
            await self.idempotency.put(key, {"status": "done"})
            
            return checkout


    async def start_payment(self, *, context_id: str, message_id: str, checkout_id: str) -> Checkout:
        # Idempotency
        key = IdempotencyKey(context_id, message_id, "start_payment")
        if await self.idempotency.get(key):
            return await self.store.get_checkout(checkout_id)

        async with self.locks.lock(checkout_id):
            checkout = await self.store.get_checkout(checkout_id)
            if not checkout:
                 raise ValueError("Checkout not found")
                 
            checkout.status = CheckoutStatus.READY_FOR_COMPLETE
            await self.store.save_checkout(checkout)
            
            await self.idempotency.put(key, {"status": "done"})
            return checkout

    async def complete_checkout(
        self,
        *,
        context_id: str,
        message_id: str,
        checkout_id: str,
        payment_data: dict,
        risk_signals: dict | None = None,
    ) -> Checkout:
        
        # --- BYPASS IF SAFETY OFF ---
        if settings.SAFETY_MODE == "off":
            # Naive implementation (The "Before" state)
            checkout = await self.store.get_checkout(checkout_id)
            order = await self.store.create_order(checkout=checkout)
            checkout.order_id = order.order_id
            checkout.status = CheckoutStatus.COMPLETED
            await self.store.save_checkout(checkout)
            return checkout

        # --- NORMAL HARDENED LOGIC ---
        key = IdempotencyKey(context_id, message_id, "complete_checkout")
        if await self.idempotency.get(key):
             return await self.store.get_checkout(checkout_id)

        async with self.locks.lock(checkout_id):
            checkout = await self.store.get_checkout(checkout_id)
            
            # Guard: If already completed, do nothing (even if new messageId!)
            if checkout.status == CheckoutStatus.COMPLETED:
                return checkout

            # Capture version for optimistic concurrency check
            expected_version = checkout.version

            # Logic - with DB-level idempotency + optimistic concurrency for multi-worker safety
            try:
                order = await self.store.create_order_safe(
                    checkout=checkout, 
                    expected_version=expected_version
                )
            except StateConflictError:
                # Cart was modified during payment (mutation race)
                # Re-fetch current state and return error/stale response
                # In a real system, you'd retry or return an error to the client
                checkout = await self.store.get_checkout(checkout_id)
                return checkout  # Return current state, client should retry
            except DuplicateOrderError:
                # Another worker won the race - fetch their order (idempotent success)
                order = await self.store.get_order_by_checkout_id(checkout_id)
                if order:
                    checkout.order_id = order.order_id
                    checkout.order_permalink_url = order.permalink_url
                    checkout.status = CheckoutStatus.COMPLETED
                    return checkout
                raise  # Should never happen if constraint is working
            
            checkout.order_id = order.order_id
            checkout.order_permalink_url = order.permalink_url
            checkout.status = CheckoutStatus.COMPLETED
            
            await self.store.save_checkout(checkout)
            
            await self.idempotency.put(key, {"status": "done"})
            return checkout

