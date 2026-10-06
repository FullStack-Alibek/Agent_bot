"""Backend (Laravel) ichki API klienti.

Bot backend bilan `Authorization: Bearer <BOT_API_TOKEN>` orqali gaplashadi:
katalogni oladi, mijozni sinxronlaydi va buyurtmani backend'ga uzatadi.

Muhim: backend mavjud bo'lmasa yoki sozlangan bo'lmasa (`backend_active` False)
klient `BackendNotConfiguredError` ko'taradi - chaqiruvchi tomon buni ushlab,
lokal rejimga qaytishi mumkin. Bu botning ishlashini to'xtatmaydi.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

import aiohttp

from bot.config import Settings

logger = logging.getLogger(__name__)


class BackendError(Exception):
    """Backend bilan aloqa xatosi (tarmoq yoki API xatosi)."""

    def __init__(self, message: str, *, status: int | None = None) -> None:
        self.status = status
        super().__init__(message)


class BackendNotConfiguredError(BackendError):
    """Backend sozlanmagan (`BACKEND_URL`/`BOT_API_TOKEN` bo'sh)."""


@dataclass(slots=True)
class BackendCatalogItem:
    """Backend'dagi bitta mahsulot (bot uchun soddalashtirilgan ko'rinish)."""

    id: int
    uuid: str | None
    name: str
    sku: str | None
    price: Decimal
    currency: str
    category: str | None = None
    unit: str | None = None
    description: str | None = None
    image_url: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> "BackendCatalogItem":
        return cls(
            id=int(data.get("id") or 0),
            uuid=data.get("uuid"),
            name=str(data.get("name") or ""),
            sku=data.get("sku"),
            price=Decimal(str(data.get("price") or 0)),
            currency=str(data.get("currency") or "UZS"),
            category=data.get("category"),
            unit=data.get("unit"),
            description=data.get("description"),
            image_url=data.get("image_url"),
            raw=data,
        )


@dataclass(slots=True)
class BackendOrderSummary:
    """Backend'dagi buyurtma (qisqa ko'rinish)."""

    uuid: str
    number: str
    status: str
    total: Decimal
    currency: str
    payment_status: str | None = None
    created_at: str | None = None

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> "BackendOrderSummary":
        return cls(
            uuid=str(data.get("uuid") or ""),
            number=str(data.get("order_number") or ""),
            status=str(data.get("status") or ""),
            total=Decimal(str(data.get("total") or 0)),
            currency=str(data.get("currency") or "UZS"),
            payment_status=data.get("payment_status"),
            created_at=data.get("created_at"),
        )


@dataclass(slots=True)
class BackendCustomer:
    """Backend'dagi mijoz + uning buyurtmalari."""

    id: int
    uuid: str
    name: str
    phone: str | None = None
    telegram_id: int | None = None
    status: str | None = None
    orders: list[BackendOrderSummary] = field(default_factory=list)

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> "BackendCustomer":
        return cls(
            id=int(data.get("id") or 0),
            uuid=str(data.get("uuid") or ""),
            name=str(data.get("name") or ""),
            phone=data.get("phone"),
            telegram_id=data.get("telegram_id"),
            status=data.get("status"),
            orders=[
                BackendOrderSummary.from_payload(item)
                for item in (data.get("orders") or [])
            ],
        )


class BackendClient:
    """Backend ichki API bilan ishlovchi async HTTP klient.

    Klient `aiohttp.ClientSession` ni qayta ishlatadi. Uni yopish uchun
    `close()` chaqiriladi (odatda bot to'xtaganda).
    """

    def __init__(self, settings: Settings, session: aiohttp.ClientSession | None = None) -> None:
        self.settings = settings
        self._session = session
        self._owns_session = session is None

    # ------------------------- Hayotiy sikl ----------------------------
    @property
    def configured(self) -> bool:
        return self.settings.backend_active

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.settings.backend_timeout)
            )
            self._owns_session = True
        return self._session

    async def close(self) -> None:
        if self._session is not None and not self._session.closed and self._owns_session:
            await self._session.close()
        self._session = None

    # ------------------------- Past daraja -----------------------------
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.settings.backend_api_token}",
            "Accept": "application/json",
        }

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self.configured:
            raise BackendNotConfiguredError("Backend sozlanmagan (BACKEND_URL yoki BOT_API_TOKEN).")

        url = f"{self.settings.backend_api_url}/{path.lstrip('/')}"
        session = await self._get_session()
        try:
            async with session.request(
                method, url, headers=self._headers(), json=json, params=params
            ) as response:
                payload = await response.json(content_type=None)
                if response.status >= 400:
                    message = ""
                    if isinstance(payload, dict):
                        message = str(payload.get("message") or "")
                    raise BackendError(
                        message or f"Backend xatosi ({response.status})",
                        status=response.status,
                    )
                return payload if isinstance(payload, dict) else {"data": payload}
        except aiohttp.ClientError as error:
            logger.warning("Backend aloqa xatosi: %s (%s %s)", error, method, url)
            raise BackendError(f"Backend aloqasi uzildi: {error}") from error

    # ------------------------- Katalog ---------------------------------
    async def fetch_catalog(self, *, limit: int = 100) -> list[BackendCatalogItem]:
        """Backend'dan faol mahsulotlar ro'yxatini oladi."""
        payload = await self._request("GET", "bot/catalog", params={"limit": limit})
        items = (payload.get("data") or {}).get("items") or []
        return [BackendCatalogItem.from_payload(item) for item in items]

    # ------------------------- Mijoz -----------------------------------
    async def fetch_customer(
        self, *, telegram_id: int | None = None, phone: str | None = None
    ) -> BackendCustomer | None:
        """Telegram ID yoki telefon bo'yicha mijozni topadi."""
        params: dict[str, Any] = {}
        if telegram_id is not None:
            params["telegram_id"] = telegram_id
        elif phone:
            params["phone"] = phone
        else:
            return None

        payload = await self._request("GET", "bot/customer", params=params)
        data = payload.get("data")
        return BackendCustomer.from_payload(data) if data else None

    async def sync_customer(
        self,
        *,
        telegram_id: int,
        name: str,
        phone: str | None = None,
        username: str | None = None,
        language: str | None = None,
    ) -> BackendCustomer:
        """Mijozni backend'ga bog'laydi (yaratadi yoki yangilaydi)."""
        payload = await self._request(
            "POST",
            "bot/customer/sync",
            json={
                "telegram_id": telegram_id,
                "name": name,
                "phone": phone,
                "username": username,
                "language": language,
            },
        )
        return BackendCustomer.from_payload(payload.get("data") or {})

    # ------------------------- Buyurtmalar -----------------------------
    async def push_order(
        self,
        *,
        customer_id: int,
        idempotency_key: str,
        items: list[dict[str, Any]],
        delivery_type: str = "delivery",
        delivery_address: str | None = None,
        delivery_latitude: float | None = None,
        delivery_longitude: float | None = None,
        shipping_amount: float | None = None,
        note: str | None = None,
    ) -> BackendOrderSummary:
        """Botdan yaratilgan buyurtmani backend'ga yozadi (idempotent)."""
        payload = await self._request(
            "POST",
            "bot/orders",
            json={
                "customer_id": customer_id,
                "idempotency_key": idempotency_key,
                "items": items,
                "delivery_type": delivery_type,
                "delivery_address": delivery_address,
                "delivery_latitude": delivery_latitude,
                "delivery_longitude": delivery_longitude,
                "shipping_amount": shipping_amount,
                "note": note,
            },
        )
        return BackendOrderSummary.from_payload({"number": payload.get("data", {}).get("order_number"), **payload.get("data", {})})

    async def fetch_order(self, uuid: str) -> BackendOrderSummary | None:
        payload = await self._request("GET", f"bot/orders/{uuid}")
        data = payload.get("data")
        return BackendOrderSummary.from_payload(data) if data else None


__all__ = [
    "BackendCatalogItem",
    "BackendClient",
    "BackendCustomer",
    "BackendError",
    "BackendNotConfiguredError",
    "BackendOrderSummary",
]
