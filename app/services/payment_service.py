from typing import Literal

class PaymentService:
    """
    Mock Payment Service Provider (PSP).
    """
    async def authorize_charge(self, amount_cents: int, payment_token: dict) -> Literal["success", "declined"]:
        # Mock logic: Fail if token explicitly asks for error
        if isinstance(payment_token, dict) and payment_token.get("force_decline") == "true":
            return "declined"
        return "success"
    
    async def capture_charge(self, transaction_id: str) -> None:
        # No-op for mock; in real world this settles the money
        pass
