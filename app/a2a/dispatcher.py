from app.a2a.schemas import A2AMessage, A2APart
from app.services.checkout_service import CheckoutService
from app.services.catalog_service import CatalogService
from app.services.payment_service import PaymentService
from app.infra.store import Store
from app.ucp.constants import DATAPART_CHECKOUT_KEY, PAYMENT_DATA_KEY
from dataclasses import asdict



class ServiceContainer:
    def __init__(self, store: Store, checkout: CheckoutService, catalog: CatalogService, payment: PaymentService):
        self.store = store
        self.checkout = checkout
        self.catalog = catalog
        self.payment = payment

async def handle_message(message: A2AMessage, *, services: ServiceContainer) -> A2AMessage:
    # Minimal logic for Phase 1
    response_parts = []
    
    # Simple action dispatch based on data part content
    input_data = next((p.data for p in message.parts if p.kind == "data" and p.data), {})
    action = input_data.get("action")
    
    checkout_data = None

    if action == "list_products":
        products = await services.catalog.list_products()
        # Return simple text list or data part for now
        response_parts.append(A2APart(
            kind="data", 
            data={"products": [asdict(p) for p in products]}
        ))

    elif action == "create_checkout":
        c = await services.checkout.create_checkout()
        checkout_data = c
        
    elif action == "add_to_checkout":
        c = await services.checkout.add_to_checkout(
            context_id=message.contextId,
            message_id=message.messageId,
            checkout_id=input_data["checkout_id"],
            product_id=input_data["product_id"],
            quantity=input_data["quantity"]
        )
        checkout_data = c

    elif action == "complete_checkout":
         # Check for payment data in any part
         payment_part = next((p.data for p in message.parts if p.kind == "data" and p.data and PAYMENT_DATA_KEY in p.data), None)
         if payment_part:
             c = await services.checkout.complete_checkout(
                 context_id=message.contextId,
                 message_id=message.messageId,
                 checkout_id=input_data.get("checkout_id", "unknown"), # simplified
                 payment_data=payment_part[PAYMENT_DATA_KEY]
             )
             checkout_data = c

    if checkout_data:
        # Convert dataclass to dict
        c_dict = asdict(checkout_data)
        # Convert Enum to string
        c_dict['status'] = c_dict['status'].value
        
        response_parts.append(A2APart(
            kind="data", 
            data={DATAPART_CHECKOUT_KEY: c_dict}
        ))
    else:
        response_parts.append(A2APart(kind="text", text="Unknown action"))

    return A2AMessage(
        kind="message",
        role="agent",
        messageId=message.messageId + "_reply", # Simple echo
        contextId=message.contextId,
        parts=response_parts
    )
