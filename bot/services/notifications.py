"""Bildirishnomalar servisi (TZ 4.4).

Vazifasi:
    * buyurtma yaratilganda/bekor qilinganda xodimlarga xabar yuborish;
    * buyurtma holati o'zgarganda mijozga xabar yuborish;
    * murojaatlar (support) bo'yicha xodimlar va mijozga xabar.

Xodimlar `ADMIN_IDS` (`.env`) orqali aniqlanadi. Xabar loglari endi backend'da
saqlanadi; bot tomonida faqat Telegram'ga yuborish amalga oshiriladi.
"""

from __future__ import annotations

import logging
from typing import Iterable

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup

from bot.config import Settings
from bot.database.enums import NotificationKind, OrderStatus
from bot.domain import Order, SupportRequest, User
from bot.locales import translator
from bot.services.presenters import staff_order_caption, support_line

logger = logging.getLogger(__name__)


class NotificationService:
    """Telegram orqali xabar yuborish (xodimlar va mijozlar)."""

    def __init__(self, bot: Bot, settings: Settings) -> None:
        self.bot = bot
        self.settings = settings

    # ------------------------- Xodimlar --------------------------------
    async def staff_chat_ids(self) -> list[int]:
        """Xabarnoma yuboriladigan chat ID lar."""
        ids: list[int] = list(self.settings.admin_ids)
        if self.settings.support_chat_id:
            ids.append(self.settings.support_chat_id)
        return sorted(set(ids))

    async def notify_staff(
        self,
        text: str,
        *,
        kind: NotificationKind = NotificationKind.BROADCAST,
        order_id: int | None = None,
        markup: InlineKeyboardMarkup | None = None,
    ) -> int:
        """Barcha xodimlarga matn yuboradi; yuborilganlar soni qaytadi."""
        sent = 0
        for chat_id in await self.staff_chat_ids():
            try:
                await self.bot.send_message(chat_id, text, reply_markup=markup)
                sent += 1
            except Exception as exc:  # pragma: no cover - tarmoq himoyasi
                logger.warning("Xodimga xabar yuborilmadi (%s): %s", chat_id, exc)
        return sent

    async def order_created(
        self, order: Order, *, markup: InlineKeyboardMarkup | None = None
    ) -> int:
        """Yangi buyurtma haqida xodimlarga xabar."""
        text = staff_order_caption(translator("uz"), order, self.settings.currency)
        return await self.notify_staff(
            text, kind=NotificationKind.ORDER_CREATED, order_id=order.id, markup=markup
        )

    async def status_changed(self, order: Order, status: OrderStatus | str) -> int:
        """Buyurtma holati o'zgargani haqida xodimlarga xabar."""
        text = translator("uz")(
            "notif_status_changed",
            number=order.number,
            status=str(status),
        )
        return await self.notify_staff(
            text, kind=NotificationKind.ORDER_STATUS, order_id=order.id
        )

    async def support_created(self, request: SupportRequest) -> int:
        """Yangi murojaat haqida xodimlarga xabar."""
        text = support_line(translator("uz"), request)
        return await self.notify_staff(text, kind=NotificationKind.SUPPORT)

    async def support_answered(self, request: SupportRequest) -> int:
        """Murojaatga javob berilgani haqida xodimlarga xabar."""
        text = translator("uz")("notif_support_answered", id=request.id)
        return await self.notify_staff(text, kind=NotificationKind.SUPPORT)

    # ------------------------- Mijozlar --------------------------------
    async def send_to_user(
        self,
        user: User | None,
        text: str,
        *,
        kind: NotificationKind = NotificationKind.BROADCAST,
        markup: InlineKeyboardMarkup | None = None,
    ) -> bool:
        """Bitta foydalanuvchiga xabar yuboradi."""
        if user is None:
            return False
        chat_id = user.chat_id or user.telegram_id
        if not chat_id:
            return False
        try:
            await self.bot.send_message(chat_id, text, reply_markup=markup)
            return True
        except Exception as exc:  # pragma: no cover
            logger.warning("Mijozga xabar yuborilmadi (%s): %s", chat_id, exc)
            return False

    async def order_user(self, order: Order) -> User | None:
        """Buyurtma egasi (chat ID ma'lum bo'lsa)."""
        return None


__all__ = ["NotificationService"]
