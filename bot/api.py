"""Backend HTTP klienti (Laravel bot API).

Botda alohida baza YO'Q - barcha ma'lumot shu klient orqali backend'dan
olinadi. Har bir metod backend endpoint'ini chaqiradi va natijani domen
obyektlariga (DTO) aylantiradi.

    from bot.api import BackendClient

    client = BackendClient(settings)
    products = await client.catalog()
"""

from __future__ import annotations

import asyncio
import logging
from decimal import Decimal
from typing import Any

import httpx

from bot.config import Settings
from bot.domain import Address, CartItem, Category, Customer, Order, Product
from bot.utils.money import to_decimal

logger = logging.getLogger("bot.api")


class BackendError(RuntimeError):
    """Backend bilan aloqa xatosi (HTTP yoki tarmoq)."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class BackendNotConfiguredError(BackendError):
    """Backend sozlanmagan (`BACKEND_URL` bo'sh)."""


class BackendClient:
    """Laravel backend bot API bilan ishlovchi async klient."""

    def __init__(self, settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.settings = settings
        self._transport = transport
        self._client: httpx.AsyncClient | None = None

    # -----------------------------------------------------------------
    @property
    def configured(self) -> bool:
        """Dinamik ravishda backend manzili sozlanganligini tekshiradi."""
        return bool(self.settings.backend_base)

    def _headers(self) -> dict[str, str]:
        token = self.settings.api_token or "mock_token_12345"
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }

    async def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.settings.backend_base,
                headers=self._headers(),
                timeout=self.settings.backend_timeout,
                transport=self._transport,
            )
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # -----------------------------------------------------------------
    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        ok_statuses: tuple[int, ...] = (200, 201),
    ) -> dict[str, Any]:
        """So'rovni yuboradi va `data` qismini qaytaradi (xatoda - BackendError)."""
        if not self.configured:
            raise BackendNotConfiguredError("Backend sozlanmagan (BACKEND_URL).")

        client = await self._http()
        last_error: Exception | None = None

        for attempt in range(self.settings.backend_retries + 1):
            try:
                response = await client.request(method, path, params=params, json=json)
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt < self.settings.backend_retries:
                    await asyncio.sleep(0.3 * (attempt + 1))
                    continue
                raise BackendError(f"Backend bilan aloqa yo'q: {exc}") from exc

            if response.status_code in ok_statuses:
                if response.status_code == 204 or not response.content:
                    return {}
                return response.json()

            if response.status_code >= 500 and attempt < self.settings.backend_retries:
                await asyncio.sleep(0.3 * (attempt + 1))
                continue

            detail = self._error_message(response)
            raise BackendError(detail, status=response.status_code)

        raise BackendError(str(last_error) if last_error else "Noma'lum xato")

    @staticmethod
    def _error_message(response: httpx.Response) -> str:
        try:
            body = response.json()
            return str(body.get("message") or body)
        except ValueError:
            return f"HTTP {response.status_code}"

    # =================================================================
    # Katalog
    # =================================================================
    async def catalog(
        self,
        *,
        search: str | None = None,
        category_id: int | None = None,
        promo: bool = False,
        limit: int = 100,
    ) -> tuple[list[Category], list[Product]]:
        """Kategoriyalar va mahsulotlar ro'yxati."""
        params: dict[str, Any] = {"limit": limit}
        if search:
            params["search"] = search
        if category_id is not None:
            params["category_id"] = category_id
        if promo:
            params["promo"] = 1

        body = await self._request("GET", "/api/bot/catalog", params=params)
        data = body.get("data") or {}
        categories = [Category.from_api(item) for item in data.get("categories") or []]
        products = [Product.from_api(item) for item in data.get("items") or []]
        return categories, products

    async def products(
        self,
        *,
        search: str | None = None,
        category_id: int | None = None,
        promo: bool = False,
        limit: int = 100,
    ) -> list[Product]:
        """Mahsulotlar ro'yxati (promo parametri qo'shildi)."""
        _, products = await self.catalog(
            search=search, category_id=category_id, promo=promo, limit=limit
        )
        return products

    # =================================================================
    # Mijoz
    # =================================================================
    async def customer(self, *, telegram_id: int) -> Customer | None:
        body = await self._request(
            "GET", "/api/bot/customer", params={"telegram_id": telegram_id}
        )
        data = body.get("data")
        return Customer.from_api(data) if data else None

    async def sync_customer(
        self,
        *,
        telegram_id: int,
        name: str,
        phone: str | None = None,
        username: str | None = None,
        language: str = "uz",
        chat_id: int | None = None,
    ) -> Customer:
        body = await self._request(
            "POST",
            "/api/bot/customer/sync",
            json={
                "telegram_id": telegram_id,
                "name": name,
                "phone": phone,
                "username": username,
                "language": language,
                "chat_id": chat_id,
            },
        )
        return Customer.from_api(body["data"])

    async def update_profile(
        self, customer_id: int, **fields: Any
    ) -> Customer:
        payload = {k: v for k, v in fields.items() if v is not None}
        body = await self._request(
            "PATCH", f"/api/bot/customers/{customer_id}/profile", json=payload
        )
        return Customer.from_api(body["data"])

    async def set_phone(self, customer_id: int, phone: str) -> Customer:
        return await self.update_profile(customer_id, phone=phone)

    async def set_language(self, customer_id: int, language: str) -> Customer:
        return await self.update_profile(customer_id, language=language)

    async def addresses(self, customer_id: int) -> list[Address]:
        body = await self._request("GET", f"/api/bot/customers/{customer_id}/addresses")
        return [Address.from_api(item) for item in body.get("data") or []]

    async def store_address(
        self,
        customer_id: int,
        *,
        address: str,
        label: str | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
    ) -> Address:
        body = await self._request(
            "POST",
            f"/api/bot/customers/{customer_id}/addresses",
            json={
                "address": address,
                "label": label,
                "latitude": latitude,
                "longitude": longitude,
            },
        )
        return Address.from_api(body["data"])

    # =================================================================
    # Savat
    # =================================================================
    async def cart(self, customer_id: int) -> list[CartItem]:
        body = await self._request("GET", f"/api/bot/customers/{customer_id}/cart")
        items = (body.get("data") or {}).get("items") or []
        return [CartItem.from_api(item) for item in items]

    async def add_to_cart(
        self,
        customer_id: int,
        product_id: int,
        quantity: Decimal | float | int,
        *,
        mode: str = "add",
    ) -> CartItem | None:
        body = await self._request(
            "POST",
            f"/api/bot/customers/{customer_id}/cart",
            json={
                "product_id": product_id,
                "quantity": float(quantity),
                "mode": mode,
            },
        )
        data = body.get("data") or {}
        if data.get("removed"):
            return None
        return CartItem(
            product_id=int(data.get("product_id", product_id)),
            quantity=to_decimal(data.get("quantity"), Decimal("0")),
        )

    async def remove_from_cart(self, customer_id: int, product_id: int) -> None:
        await self._request(
            "DELETE", f"/api/bot/customers/{customer_id}/cart/{product_id}"
        )

    async def clear_cart(self, customer_id: int) -> None:
        await self._request("DELETE", f"/api/bot/customers/{customer_id}/cart")

    # =================================================================
    # Buyurtmalar
    # =================================================================
    async def orders(
        self, customer_id: int, *, page: int = 1, per_page: int = 5
    ) -> tuple[list[Order], int]:
        body = await self._request(
            "GET",
            f"/api/bot/customers/{customer_id}/orders",
            params={"page": page, "per_page": per_page},
        )
        data = body.get("data") or {}
        orders = [Order.from_api(item) for item in data.get("items") or []]
        return orders, int(data.get("total") or 0)

    async def order(self, customer_id: int, key: int | str) -> Order:
        body = await self._request(
            "GET", f"/api/bot/customers/{customer_id}/orders/{key}"
        )
        return Order.from_api(body["data"])

    async def create_order(
        self,
        *,
        customer_id: int,
        items: list[dict[str, Any]],
        delivery_type: str = "delivery",
        delivery_address: str | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
        shipping_amount: float = 0,
        note: str | None = None,
        idempotency_key: str,
    ) -> Order:
        body = await self._request(
            "POST",
            "/api/bot/orders",
            json={
                "customer_id": customer_id,
                "delivery_type": delivery_type,
                "delivery_address": delivery_address,
                "delivery_latitude": latitude,
                "delivery_longitude": longitude,
                "shipping_amount": shipping_amount,
                "note": note,
                "idempotency_key": idempotency_key,
                "items": items,
            },
        )
        return Order.from_api(body["data"])

    async def cancel_order(
        self, customer_id: int, key: int | str, *, reason: str | None = None
    ) -> Order:
        body = await self._request(
            "POST",
            f"/api/bot/customers/{customer_id}/orders/{key}/cancel",
            json={"reason": reason},
        )
        return Order.from_api(body["data"])

    async def repeat_order(self, customer_id: int, key: int | str) -> int:
        body = await self._request(
            "POST", f"/api/bot/customers/{customer_id}/orders/{key}/repeat"
        )
        return int((body.get("data") or {}).get("added") or 0)

    # =================================================================
    # Yordam
    # =================================================================
    async def create_support(
        self, customer_id: int, message: str, *, order_id: int | None = None
    ) -> dict[str, Any]:
        body = await self._request(
            "POST",
            f"/api/bot/customers/{customer_id}/support",
            json={"message": message, "order_id": order_id},
        )
        return body.get("data") or {}


__all__ = ["BackendClient", "BackendError", "BackendNotConfiguredError"]
