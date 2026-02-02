from app.infra.store import Store
from app.domain.models import Product

class CatalogService:
    def __init__(self, store: Store):
        self.store = store

    async def list_products(self) -> list[Product]:
        return await self.store.list_products()

    async def get_product(self, product_id: str) -> Product:
        return await self.store.get_product(product_id)
