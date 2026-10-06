"""Qo'llab-quvvatlash servisi (TZ 4.4 - mijoz ↔ operator aloqasi).

Murojaatlar backend `support_requests` jadvalida saqlanadi.
"""

from __future__ import annotations

from bot.api import BackendClient
from bot.database.enums import SupportStatus
from bot.domain import SupportRequest
from bot.services.errors import SupportTooShortError
from bot.utils.pagination import Pagination, paginate

#: Murojaatning minimal uzunligi.
MIN_MESSAGE_LENGTH = 5


class SupportService:
    """Murojaatlarni qabul qilish (backend API orqali)."""

    def __init__(self, api: BackendClient) -> None:
        self.api = api

    async def create(
        self, customer_id: int, message: str, *, order_id: int | None = None
    ) -> SupportRequest:
        """Yangi murojaat yaratadi (juda qisqa matn rad etiladi)."""
        text = (message or "").strip()
        if len(text) < MIN_MESSAGE_LENGTH:
            raise SupportTooShortError()
        data = await self.api.create_support(customer_id, text, order_id=order_id)
        return SupportRequest(
            id=int(data.get("id", 0)),
            message=text,
            status=SupportStatus.OPEN,
        )

    async def list_for_user(self, customer_id: int, *, limit: int = 10) -> list[SupportRequest]:
        return []

    async def open_page(
        self, *, page: int = 1, per_page: int = 5
    ) -> tuple[list[SupportRequest], Pagination]:
        return [], paginate(0, page, per_page)

    async def count_open(self) -> int:
        return 0


__all__ = ["MIN_MESSAGE_LENGTH", "SupportService"]
