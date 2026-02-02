from typing import Protocol, Dict
import uuid
from app.domain.models import Product, Checkout, Order

class Store(Protocol):
    async def list_products(self) -> list[Product]: ...
    async def get_product(self, product_id: str) -> Product: ...
    async def create_checkout(self) -> Checkout: ...
    async def get_checkout(self, checkout_id: str) -> Checkout: ...
    async def save_checkout(self, checkout: Checkout) -> None: ...
    async def create_order(self, *, checkout: Checkout) -> Order: ...
    async def get_order(self, order_id: str) -> Order: ...

class InMemoryStore(Store):
    def __init__(self):
        self.products = {
            "p1": Product("p1", "T-Shirt", 2000, "https://placehold.co/400?text=T-Shirt"),
            "p2": Product("p2", "Mug", 1000, "https://placehold.co/400?text=Mug")
        }
        self.checkouts: Dict[str, Checkout] = {}
        self.orders: Dict[str, Order] = {}

    async def list_products(self) -> list[Product]:
        return list(self.products.values())

    async def get_product(self, product_id: str) -> Product:
        return self.products[product_id]

    async def create_checkout(self) -> Checkout:
        cid = str(uuid.uuid4())
        c = Checkout(checkout_id=cid, status="incomplete")
        self.checkouts[cid] = c
        return c

    async def get_checkout(self, checkout_id: str) -> Checkout:
        return self.checkouts.get(checkout_id)

    async def save_checkout(self, checkout: Checkout) -> None:
        self.checkouts[checkout.checkout_id] = checkout

    async def create_order(self, *, checkout: Checkout) -> Order:
        oid = str(uuid.uuid4())
        o = Order(oid, checkout.checkout_id, checkout.total_cents, f"http://mock/orders/{oid}")
        self.orders[oid] = o
        return o
        
    async def get_order(self, order_id: str) -> Order:
        return self.orders.get(order_id)
