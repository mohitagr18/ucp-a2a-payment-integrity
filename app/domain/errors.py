"""Domain errors for checkout integrity."""


class DuplicateOrderError(Exception):
    """Raised when an order already exists for the given checkout_id.
    
    This exception enables idempotent handling when the database's unique
    constraint on orders.checkout_id is violated, allowing the service
    layer to detect races and return the existing order instead of failing.
    """
    def __init__(self, checkout_id: str):
        self.checkout_id = checkout_id
        super().__init__(f"Order already exists for checkout {checkout_id}")
