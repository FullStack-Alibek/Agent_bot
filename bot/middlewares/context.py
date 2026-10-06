"""Foydalanuvchi konteksti middleware'i.

Vazifalari:
    1. Telegram foydalanuvchisini backend'da ro'yxatdan o'tkazish (sync).
    2. Bloklangan/faol bo'lmagan mijozlarni to'xtatish (backend statusi).
    3. Mijoz kartochkasini tayyorlash (mijozlar uchun).
    4. `BotContext` (backend klient + servislar) ni `data["ctx"]` ga joylash.

Diqqat: botda alohida baza YO'Q. `User` DTO mijoz uchun `id` maydonida
backend `customers.id` ni saqlaydi - shunda savat/buyurtma operatsiyalari
to'g'ri mijozga bog'lanadi.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from aiogram import BaseMiddleware, Bot
from aiogram.types import TelegramObject

from bot.api import BackendClient, BackendError, BackendNotConfiguredError
from bot.config import Settings
from bot.database.enums import UserRole
from bot.domain import Customer, User
from bot.locales import DEFAULT_LANGUAGE, normalize_language, translate
from bot.middlewares.common import Handler, answer_event, event_chat_id, event_user
from bot.middlewares.i18n import resolve_language
from bot.services import (
    CartService,
    CatalogService,
    NotificationService,
    OrderService,
    ServiceError,
    SettingsService,
    SupportService,
)

logger = logging.getLogger(__name__)

CONTEXT_KEY = "ctx"


@dataclass(slots=True)
class BotContext:
    """Bitta yangilanish uchun kontekst: foydalanuvchi, API klient va servislar."""

    settings: Settings
    bot: Bot
    api: BackendClient
    user: User | None = None
    customer: Customer | None = None
    language: str = DEFAULT_LANGUAGE

    catalog: CatalogService = field(init=False)
    cart: CartService = field(init=False)
    orders: OrderService = field(init=False)
    support: SupportService = field(init=False)
    settings_service: SettingsService = field(init=False)
    notifications: NotificationService = field(init=False)

    def __post_init__(self) -> None:
        self.language = normalize_language(self.language)
        self.catalog = CatalogService(self.api)
        self.cart = CartService(self.api, self.settings)
        self.orders = OrderService(self.api, self.settings)
        self.support = SupportService(self.api)
        self.settings_service = SettingsService(self.settings)
        self.notifications = NotificationService(self.bot, self.settings)

    # ------------------------- Qulayliklar -----------------------------
    @property
    def lang(self) -> str:
        return self.language

    @property
    def user_id(self) -> int | None:
        """Mijoz id (xodim uchun - telegram ID)."""
        return self.user.id if self.user is not None else None

    @property
    def customer_id(self) -> int | None:
        """Backend'dagi mijoz id (savat/buyurtma uchun)."""
        return self.customer.id if self.customer is not None else None

    @property
    def chat_id(self) -> int | None:
        """Foydalanuvchi bilan shaxsiy chat ID (xabar yuborish uchun)."""
        if self.user is None:
            return None
        return self.user.chat_id or self.user.telegram_id

    @property
    def is_staff(self) -> bool:
        return bool(self.user is not None and self.user.is_staff)

    @property
    def is_admin(self) -> bool:
        return bool(self.user is not None and self.user.role is UserRole.ADMIN)

    def t(self, key: str, **kwargs: object) -> str:
        """Kontekst tiliga bog'langan tarjima funksiyasi."""
        return translate(key, self.language, **kwargs)

    def error_text(self, error: ServiceError) -> str:
        """Servis xatosini foydalanuvchi tilida ko'rsatadi."""
        return error.text(self.t)


class BotContextMiddleware(BaseMiddleware):
    """Foydalanuvchini backend'ga sinxronlaydi va `BotContext` ni tayyorlaydi."""

    def __init__(self, settings: Settings, api: BackendClient) -> None:
        self.settings = settings
        self.api = api

    def _role(self, telegram_id: int) -> UserRole:
        return UserRole.ADMIN if self.settings.is_admin(telegram_id) else UserRole.CLIENT

    async def __call__(
        self,
        handler: Handler,
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        bot: Bot | None = data.get("bot")
        telegram_user = event_user(event)
        if bot is None or telegram_user is None or telegram_user.is_bot:
            return await handler(event, data)

        language = resolve_language(data.get("lang"), self.settings.default_language)
        chat_id = event_chat_id(event)
        role = self._role(telegram_user.id)

        user = User(
            id=int(telegram_user.id),
            telegram_id=int(telegram_user.id),
            chat_id=chat_id,
            username=telegram_user.username,
            full_name=telegram_user.full_name,
            language=language,
            role=role,
        )
        customer: Customer | None = None

        try:
            if not role.is_staff and self.api.configured:
                try:
                    customer = await self.api.sync_customer(
                        telegram_id=telegram_user.id,
                        name=telegram_user.full_name or f"ID {telegram_user.id}",
                        username=telegram_user.username,
                        language=language,
                        chat_id=chat_id,
                    )
                    user.id = customer.id
                    user.phone = customer.phone
                    user.language = customer.language or language
                    user.is_blocked = str(customer.status).lower() == "blocked"
                    if user.is_blocked:
                        logger.info("Bloklangan mijoz: %s", telegram_user.id)
                        await answer_event(event, translate("error_denied", language))
                        return None
                except (BackendError, BackendNotConfiguredError) as exc:
                    logger.warning("Backend sinxronizatsiya xatosi (lokal rejimda davom etilmoqda): %s", exc)
        except Exception as exc:
            logger.error("BotContextMiddleware kutilmagan xatosi: %s", exc)

        ctx = BotContext(
            settings=self.settings,
            bot=bot,
            api=self.api,
            user=user,
            customer=customer,
            language=normalize_language(user.language),
        )
        data[CONTEXT_KEY] = ctx
        data["user"] = user
        data["customer"] = customer
        data["lang"] = ctx.language
        data["t"] = ctx.t
        return await handler(event, data)


__all__ = ["CONTEXT_KEY", "BotContext", "BotContextMiddleware"]
