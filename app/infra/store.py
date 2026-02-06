from typing import Protocol, Optional
import json
import sqlite3
import aiosqlite
import uuid
from dataclasses import asdict
from app.domain.models import Product, Checkout, Order, CheckoutStatus, LineItem
from app.domain.errors import DuplicateOrderError, StateConflictError

class Store(Protocol):
    async def list_products(self) -> list[Product]: ...
    async def get_product(self, product_id: str) -> Product: ...
    async def create_checkout(self) -> Checkout: ...
    async def get_checkout(self, checkout_id: str) -> Optional[Checkout]: ...
    async def save_checkout(self, checkout: Checkout) -> None: ...
    async def create_order(self, *, checkout: Checkout) -> Order: ...
    async def create_order_safe(self, *, checkout: Checkout, expected_version: int) -> Order: ...
    async def get_order(self, order_id: str) -> Optional[Order]: ...
    async def get_order_by_checkout_id(self, checkout_id: str) -> Optional[Order]: ...

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
        # Check if order already exists for this checkout (in-memory simulation)
        for existing in self.orders.values():
            if existing.checkout_id == checkout.checkout_id:
                raise DuplicateOrderError(checkout.checkout_id)
        oid = str(uuid.uuid4())
        o = Order(oid, checkout.checkout_id, checkout.total_cents, f"http://mock/orders/{oid}")
        self.orders[oid] = o
        return o

    async def create_order_safe(self, *, checkout: Checkout, expected_version: int) -> Order:
        """Create order with optimistic concurrency check."""
        current = self.checkouts.get(checkout.checkout_id)
        if current and current.version != expected_version:
            raise StateConflictError(checkout.checkout_id, expected_version, current.version)
        return await self.create_order(checkout=checkout)
        
    async def get_order(self, order_id: str) -> Optional[Order]:
        return self.orders.get(order_id)

    async def get_order_by_checkout_id(self, checkout_id: str) -> Optional[Order]:
        for order in self.orders.values():
            if order.checkout_id == checkout_id:
                return order
        return None

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
                    version INTEGER DEFAULT 1,
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
            # Ensure at most one order per checkout (multi-worker safety)
            await db.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_orders_checkout_id 
                ON orders(checkout_id)
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
        c = Checkout(checkout_id=cid, status=CheckoutStatus.INCOMPLETE, version=1)
        
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO checkouts (checkout_id, status, total_cents, line_items_json, version) VALUES (?, ?, ?, ?, ?)",
                (cid, c.status.value, 0, "[]", 1)
            )
            await db.commit()
        return c

    async def get_checkout(self, checkout_id: str) -> Optional[Checkout]:
        async with aiosqlite.connect(self.db_path) as db:
            query = """
                SELECT checkout_id, status, total_cents, line_items_json, version, order_id, order_permalink_url 
                FROM checkouts 
                WHERE checkout_id=?
            """
            async with db.execute(query, (checkout_id,)) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None
                
                cid, status_str, total, items_json, version, oid, url = row
                
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
                    version=version or 1,
                    order_id=oid,
                    order_permalink_url=url
                )


    async def save_checkout(self, checkout: Checkout) -> None:
        """Save checkout and increment version (for mutation tracking)."""
        items_json = json.dumps([asdict(li) for li in checkout.line_items])
        new_version = checkout.version + 1
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                UPDATE checkouts 
                SET status=?, total_cents=?, line_items_json=?, version=?, order_id=?, order_permalink_url=?
                WHERE checkout_id=?
                """,
                (checkout.status.value, checkout.total_cents, items_json, new_version, 
                 checkout.order_id, checkout.order_permalink_url, checkout.checkout_id)
            )
            await db.commit()
        # Update the in-memory version
        checkout.version = new_version

    async def create_order(self, *, checkout: Checkout) -> Order:
        oid = str(uuid.uuid4())
        permalink = f"http://localhost:8000/orders/{oid}"
        o = Order(oid, checkout.checkout_id, checkout.total_cents, permalink)
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "INSERT INTO orders (order_id, checkout_id, total_cents, permalink_url) VALUES (?, ?, ?, ?)",
                    (oid, o.checkout_id, o.total_cents, o.permalink_url)
                )
                await db.commit()
            return o
        except sqlite3.IntegrityError as e:
            if "UNIQUE constraint failed" in str(e) or "idx_orders_checkout_id" in str(e):
                raise DuplicateOrderError(checkout.checkout_id) from e
            raise

    async def create_order_safe(self, *, checkout: Checkout, expected_version: int) -> Order:
        """Create order with optimistic concurrency check.
        
        Verifies that the checkout version hasn't changed since checkout was read,
        preventing the 'sneaky add' race where items are added during payment.
        """
        async with aiosqlite.connect(self.db_path) as db:
            # 1. Verify cart state (optimistic lock check)
            async with db.execute(
                "SELECT version, total_cents FROM checkouts WHERE checkout_id=?",
                (checkout.checkout_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    raise ValueError(f"Checkout {checkout.checkout_id} not found")
                
                real_version, real_total = row
                
                # RACE DETECTED: cart was modified during payment!
                if real_version != expected_version:
                    raise StateConflictError(checkout.checkout_id, expected_version, real_version)
                
                # Also check total hasn't changed (belt and suspenders)
                if real_total != checkout.total_cents:
                    raise StateConflictError(checkout.checkout_id, expected_version, real_version)
        
        # 2. If safe, proceed with normal order creation
        return await self.create_order(checkout=checkout)

    async def get_order_by_checkout_id(self, checkout_id: str) -> Order | None:
        """Fetch an existing order by checkout_id for idempotent responses."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT order_id, checkout_id, total_cents, permalink_url FROM orders WHERE checkout_id=?",
                (checkout_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None
                return Order(*row)

