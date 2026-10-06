"""Katalog servisi (TZ 4.4 - katalog, qidiruv, aksiyalar).

Ma'lumot manbai: Laravel backend (`bot.api.BackendClient`). Botda alohida
baza yo'q - kategoriyalar va mahsulotlar backend'dan olinadi.
"""

from __future__ import annotations

from dataclasses import dataclass

from bot.api import BackendClient
from bot.domain import Category, Product
from bot.services.errors import NotFoundError
from bot.utils.pagination import Pagination, paginate


@dataclass(slots=True)
class CategoryCard:
    """Kategoriya + undagi mahsulotlar soni (inline tugma uchun)."""

    category: Category
    products: int

    def label(self, lang: str) -> str:
        return self.category.button_label(lang)


class CatalogService:
    """Kategoriya va mahsulotlar bilan ishlash (backend API orqali)."""

    def __init__(self, api: BackendClient) -> None:
        self.api = api
        # Kichik kesh: bir yangilanish ichida takroriy so'rovlarni kamaytiradi.
        self._products_cache: list[Product] | None = None
        self._categories_cache: list[Category] | None = None

    async def _load(self) -> tuple[list[Category], list[Product]]:
        if self._products_cache is None or self._categories_cache is None:
            categories, products = await self.api.catalog(limit=200)
            self._categories_cache = categories
            self._products_cache = products
        return self._categories_cache, self._products_cache

    # ------------------------- Kategoriyalar ---------------------------
    async def category_cards(self) -> list[CategoryCard]:
        """Faol kategoriyalar va mahsulotlar soni (katalog menyusi uchun)."""
        categories, _ = await self._load()
        return [CategoryCard(category=item, products=item.products) for item in categories]

    async def get_category(self, category_id: int | None) -> Category:
        if category_id is None:
            raise NotFoundError()
        categories, _ = await self._load()
        for category in categories:
            if category.id == category_id:
                return category
        raise NotFoundError()

    # ------------------------- Mahsulotlar -----------------------------
    async def _all_products(self) -> list[Product]:
        _, products = await self._load()
        return products

    async def product_page(
        self,
        *,
        category_id: int | None = None,
        page: int = 1,
        per_page: int = 5,
    ) -> tuple[list[Product], Pagination]:
        products = await self._all_products()
        if category_id is not None:
            products = [p for p in products if p.category_id == category_id]
        total = len(products)
        pagination = paginate(total, page, per_page)
        return products[pagination.offset : pagination.offset + pagination.limit], pagination

    async def promo_page(
        self, *, page: int = 1, per_page: int = 5
    ) -> tuple[list[Product], Pagination]:
        products = await self.api.products(promo=True, limit=200)
        total = len(products)
        pagination = paginate(total, page, per_page)
        return products[pagination.offset : pagination.offset + pagination.limit], pagination

    async def search_page(
        self, query: str, *, page: int = 1, per_page: int = 5
    ) -> tuple[list[Product], Pagination]:
        products = await self.api.products(search=query, limit=100)
        total = len(products)
        pagination = paginate(total, page, per_page)
        return products[pagination.offset : pagination.offset + pagination.limit], pagination

    async def get_product(self, product_id: int | None) -> Product:
        if product_id is None:
            raise NotFoundError()
        products = await self._all_products()
        for product in products:
            if product.id == product_id and product.is_active:
                return product
        # Keshda bo'lmasa - backend'dan qidiramiz.
        for product in await self.api.products(limit=200):
            if product.id == product_id and product.is_active:
                return product
        raise NotFoundError()

    async def find_product(self, query: str) -> list[Product]:
        """Aniq artikul/shtrix-kod yoki nomi bo'yicha qidiruv."""
        text = (query or "").strip()
        if not text:
            return []
        products = await self.api.products(search=text, limit=10)
        for product in products:
            if product.sku and product.sku.upper() == text.upper():
                return [product]
        return products

    async def low_stock(self, *, limit: int = 20) -> list[Product]:
        products = await self._all_products()
        low = [p for p in products if p.is_low_stock]
        return low[:limit]


__all__ = ["CatalogService", "CategoryCard"]
