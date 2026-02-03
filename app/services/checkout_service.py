from app.infra.store import Store
from app.domain.models import Checkout, LineItem, CheckoutStatus
from app.infra.lock_manager import LockManager, InMemoryLockManager
from app.infra.idempotency import IdempotencyStore, IdempotencyKey, InMemoryIdempotencyStore

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
        # 1. Idempotency Check
        key = IdempotencyKey(context_id, message_id, "add_to_checkout")
        cached = await self.idempotency.get(key)
        if cached:
            # We need to return a Checkout object, but we stored a dict or similar.
            # For simplicity in Phase 2, we re-fetch the checkout state.
            # In a strict system, we'd store the specific return value.
            return await self.store.get_checkout(checkout_id)

        # 2. Lock
        async with self.locks.lock(checkout_id):
            # 3. Double-check idempotency inside lock (advanced, but good practice)
            # (Skipping for minimal academic scope, relying on outer check)

            checkout = await self.store.get_checkout(checkout_id)
            if not checkout:
                raise ValueError("Checkout not found")
            
            # Logic
            product = await self.store.get_product(product_id)
            checkout.line_items.append(LineItem(product.product_id, quantity, product.price_cents))
            checkout.total_cents += (quantity * product.price_cents)
            
            await self.store.save_checkout(checkout)
            
            # 4. Save Idempotency
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
        # Idempotency
        key = IdempotencyKey(context_id, message_id, "complete_checkout")
        if await self.idempotency.get(key):
            return await self.store.get_checkout(checkout_id)

        async with self.locks.lock(checkout_id):
            checkout = await self.store.get_checkout(checkout_id)
            
            # Guard: If already completed, do nothing (even if new messageId!)
            if checkout.status == CheckoutStatus.COMPLETED:
                return checkout

            # Logic
            order = await self.store.create_order(checkout=checkout)
            checkout.order_id = order.order_id
            checkout.order_permalink_url = order.permalink_url
            checkout.status = CheckoutStatus.COMPLETED
            
            await self.store.save_checkout(checkout)
            
            await self.idempotency.put(key, {"status": "done"})
            return checkout
