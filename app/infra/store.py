from typing import Protocol, Optional
import json
import aiosqlite
import uuid
from dataclasses import asdict
from app.domain.models import Product, Checkout, Order, CheckoutStatus, LineItem

class Store(Protocol):
    async def list_products(self) -> list[Product]: ...
    async def get_product(self, product_id: str) -> Product: ...
    async def create_checkout(self) -> Checkout: ...
    async def get_checkout(self, checkout_id: str) -> Optional[Checkout]: ...
    async def save_checkout(self, checkout: Checkout) -> None: ...
    async def create_order(self, *, checkout: Checkout) -> Order: ...
    async def get_order(self, order_id: str) -> Optional[Order]: ...

class InMemoryStore(Store):
    def __init__(self):
        self.products = {
            "p1": Product("p1", "T-Shirt", 2000, "https://placehold.co/400?text=T-Shirt"),
            "p2": Product("p2", "Mug", 1000, "https://placehold.co/400?text=Mug")
        }
        self.checkouts = {}
        self.orders = {}

    async def init_db(self):
        # No-op for memory store compatibility in tests
        pass

    async def list_products(self) -> list[Product]:
        return list(self.products.values())

    async def get_product(self, product_id: str) -> Product:
        return self.products[product_id]

    async def create_checkout(self) -> Checkout:
        cid = str(uuid.uuid4())
        c = Checkout(checkout_id=cid, status=CheckoutStatus.INCOMPLETE)
        self.checkouts[cid] = c
        return c

    async def get_checkout(self, checkout_id: str) -> Optional[Checkout]:
        return self.checkouts.get(checkout_id)

    async def save_checkout(self, checkout: Checkout) -> None:
        self.checkouts[checkout.checkout_id] = checkout

    async def create_order(self, *, checkout: Checkout) -> Order:
        oid = str(uuid.uuid4())
        o = Order(oid, checkout.checkout_id, checkout.total_cents, f"http://mock/orders/{oid}")
        self.orders[oid] = o
        return o
        
    async def get_order(self, order_id: str) -> Optional[Order]:
        return self.orders.get(order_id)

class SQLiteStore(Store):
    def __init__(self, db_path: str):
        self.db_path = db_path

    async def init_db(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS products (
                    product_id TEXT PRIMARY KEY,
                    title TEXT,
                    price_cents INTEGER,
                    image_url TEXT
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS checkouts (
                    checkout_id TEXT PRIMARY KEY,
                    status TEXT,
                    total_cents INTEGER,
                    line_items_json TEXT,
                    order_id TEXT,
                    order_permalink_url TEXT
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    order_id TEXT PRIMARY KEY,
                    checkout_id TEXT,
                    total_cents INTEGER,
                    permalink_url TEXT
                )
            """)
            await db.commit()
            await self._seed_products(db)

    async def _seed_products(self, db):
        cursor = await db.execute("SELECT count(*) FROM products")
        count = (await cursor.fetchone())[0]
        if count == 0:
            products = [
                ("p1", "T-Shirt", 2000, "https://placehold.co/400?text=T-Shirt"),
                ("p2", "Mug", 1000, "https://placehold.co/400?text=Mug")
            ]
            await db.executemany(
                "INSERT INTO products (product_id, title, price_cents, image_url) VALUES (?, ?, ?, ?)",
                products
            )
            await db.commit()

    async def list_products(self) -> list[Product]:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT product_id, title, price_cents, image_url FROM products") as cursor:
                rows = await cursor.fetchall()
                return [Product(*row) for row in rows]

    async def get_product(self, product_id: str) -> Product:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT product_id, title, price_cents, image_url FROM products WHERE product_id=?", (product_id,)) as cursor:
                row = await cursor.fetchone()
                if not row:
                    raise ValueError(f"Product {product_id} not found")
                return Product(*row)

    async def create_checkout(self) -> Checkout:
        cid = str(uuid.uuid4())
        c = Checkout(checkout_id=cid, status=CheckoutStatus.INCOMPLETE)
        
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO checkouts (checkout_id, status, total_cents, line_items_json) VALUES (?, ?, ?, ?)",
                (cid, c.status.value, 0, "[]")
            )
            await db.commit()
        return c

    async def get_checkout(self, checkout_id: str) -> Optional[Checkout]:
        async with aiosqlite.connect(self.db_path) as db:
            # FIX: Select columns explicitly to guarantee order
            query = """
                SELECT checkout_id, status, total_cents, line_items_json, order_id, order_permalink_url 
                FROM checkouts 
                WHERE checkout_id=?
            """
            async with db.execute(query, (checkout_id,)) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None
                
                cid, status_str, total, items_json, oid, url = row
                
                # Ensure items_json is a string list, or default to empty list if None/Empty
                if not items_json:
                    items_data = []
                else:
                    try:
                        items_data = json.loads(items_json)
                    except json.JSONDecodeError:
                        items_data = []

                line_items = [LineItem(**item) for item in items_data]
                
                return Checkout(
                    checkout_id=cid,
                    status=CheckoutStatus(status_str),
                    total_cents=total,
                    line_items=line_items,
                    order_id=oid,
                    order_permalink_url=url
                )


    async def save_checkout(self, checkout: Checkout) -> None:
        items_json = json.dumps([asdict(li) for li in checkout.line_items])
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                UPDATE checkouts 
                SET status=?, total_cents=?, line_items_json=?, order_id=?, order_permalink_url=?
                WHERE checkout_id=?
                """,
                (checkout.status.value, checkout.total_cents, items_json, checkout.order_id, checkout.order_permalink_url, checkout.checkout_id)
            )
            await db.commit()

    async def create_order(self, *, checkout: Checkout) -> Order:
        oid = str(uuid.uuid4())
        permalink = f"http://localhost:8000/orders/{oid}"
        o = Order(oid, checkout.checkout_id, checkout.total_cents, permalink)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO orders (order_id, checkout_id, total_cents, permalink_url) VALUES (?, ?, ?, ?)",
                (oid, o.checkout_id, o.total_cents, o.permalink_url)
            )
            await db.commit()
        return o
