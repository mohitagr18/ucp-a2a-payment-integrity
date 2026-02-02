from pydantic import BaseModel, Field
from typing import List, Optional
from enum import Enum

class UCPCheckoutStatus(str, Enum):
    INCOMPLETE = "incomplete"
    READY_FOR_COMPLETE = "ready_for_complete"
    COMPLETED = "completed"

class UCPLineItem(BaseModel):
    product_id: str
    quantity: int
    unit_price_cents: int
    subtotal_cents: int

class UCPCheckout(BaseModel):
    """
    Represents the 'a2a.ucp.checkout' DataPart.
    """
    checkout_id: str
    status: UCPCheckoutStatus
    total_cents: int
    line_items: List[UCPLineItem] = []
    currency: str = "USD"
    
    # Only present if status == COMPLETED
    order_id: Optional[str] = None
    order_permalink_url: Optional[str] = None

class UCPPaymentData(BaseModel):
    """
    Represents 'a2a.ucp.checkout.payment_data'
    """
    token: str
    # In a real app, this would be encrypted blob or PSP token
