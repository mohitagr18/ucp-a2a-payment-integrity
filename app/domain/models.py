from dataclasses import dataclass, field
from enum import Enum

@dataclass(frozen=True)
class Product:
    product_id: str
    title: str
    price_cents: int
    image_url: str = "https://placehold.co/600x400?text=Product" 

@dataclass
class LineItem:
    product_id: str
    quantity: int
    unit_price_cents: int

class CheckoutStatus(Enum):
    INCOMPLETE = "incomplete"
    READY_FOR_COMPLETE = "ready_for_complete"
    COMPLETED = "completed"

@dataclass
class Checkout:
    checkout_id: str
    status: CheckoutStatus
    line_items: list[LineItem] = field(default_factory=list)
    total_cents: int = 0
    version: int = 1  # Optimistic concurrency control
    order_id: str | None = None
    order_permalink_url: str | None = None

@dataclass(frozen=True)
class Order:
    order_id: str
    checkout_id: str
    total_cents: int
    permalink_url: str
