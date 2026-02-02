from app.infra.store import Store
from app.domain.models import Checkout, LineItem, CheckoutStatus

class CheckoutService:
    def __init__(self, *, store: Store, locks=None, idempotency=None, payment=None) -> None:
        self.store = store

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
        # Phase 1: No locks/idempotency checks yet
        checkout = await self.store.get_checkout(checkout_id)
        if not checkout:
            raise ValueError("Checkout not found")
        
        product = await self.store.get_product(product_id)
        checkout.line_items.append(LineItem(product.product_id, quantity, product.price_cents))
        checkout.total_cents += (quantity * product.price_cents)
        
        await self.store.save_checkout(checkout)
        return checkout

    async def start_payment(self, *, context_id: str, message_id: str, checkout_id: str) -> Checkout:
        checkout = await self.store.get_checkout(checkout_id)
        if not checkout:
             raise ValueError("Checkout not found")
             
        checkout.status = CheckoutStatus.READY_FOR_COMPLETE
        await self.store.save_checkout(checkout)
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
        checkout = await self.store.get_checkout(checkout_id)
        
        # Basic logic
        order = await self.store.create_order(checkout=checkout)
        checkout.order_id = order.order_id
        checkout.order_permalink_url = order.permalink_url
        checkout.status = CheckoutStatus.COMPLETED
        
        await self.store.save_checkout(checkout)
        return checkout
