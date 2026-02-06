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


class StateConflictError(Exception):
    """Raised when checkout state was modified during payment (optimistic lock failure).
    
    This indicates a mutation race: an item was added/removed between reading
    the cart and attempting to complete payment. The payment should be retried
    with fresh cart state.
    """
    def __init__(self, checkout_id: str, expected_version: int, actual_version: int):
        self.checkout_id = checkout_id
        self.expected_version = expected_version
        self.actual_version = actual_version
        super().__init__(
            f"Cart {checkout_id} was modified during payment "
            f"(expected version {expected_version}, found {actual_version})"
        )
