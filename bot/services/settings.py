"""Sozlamalar servisi: do'kon sozlamalari.

Sozlamalar Laravel backend (`settings`) orqali boshqariladi. Bu servis
`.env` standart qiymatlarini ishlatadi va backend'dan kelgan qiymatlar
bo'lsa ularni ustuvor qiladi (hozircha `.env`).
"""

from __future__ import annotations

from decimal import Decimal

from bot.config import Settings
from bot.utils.money import to_decimal

#: Boshqariladigan sozlamalar va ularning tavsifi (admin panel uchun).
SETTING_KEYS: dict[str, str] = {
    "brand_name": "Do'kon nomi",
    "support_phone": "Qo'llab-quvvatlash raqami",
    "pickup_address": "Olib ketish manzili",
    "working_hours": "Ish vaqti",
    "delivery_fee": "Yetkazish narxi",
    "free_delivery_from": "Bepul yetkazish chegarasi",
    "min_order_amount": "Minimal buyurtma summasi",
    "order_prefix": "Buyurtma raqami prefiksi",
}


class SettingsService:
    """Do'kon sozlamalari (`.env` asosida)."""

    def __init__(self, config: Settings) -> None:
        self.config = config

    def _value(self, key: str) -> str | None:
        mapping: dict[str, object] = {
            "brand_name": self.config.brand_name,
            "support_phone": self.config.support_phone,
            "pickup_address": self.config.pickup_address,
            "working_hours": self.config.working_hours,
            "delivery_fee": self.config.delivery_fee,
            "free_delivery_from": self.config.free_delivery_from,
            "min_order_amount": self.config.min_order_amount,
            "order_prefix": self.config.order_prefix,
        }
        value = mapping.get(key)
        return None if value is None else str(value)

    async def get(self, key: str) -> str | None:
        return self._value(key)

    async def all(self) -> dict[str, str]:
        result: dict[str, str] = {}
        for key in SETTING_KEYS:
            value = self._value(key)
            if value is not None:
                result[key] = value
        return result

    async def info(self) -> dict[str, str]:
        """Botning «Ma'lumot» bo'limi uchun matnli qiymatlar."""
        return {
            "brand_name": self.config.brand_name,
            "support_phone": self.config.support_phone or "—",
            "pickup_address": self.config.pickup_address or "—",
            "working_hours": self.config.working_hours or "—",
        }

    def _decimal(self, key: str, default: Decimal) -> Decimal:
        raw = self._value(key)
        if raw is None or str(raw).strip() == "":
            return default
        try:
            return to_decimal(raw)
        except (ValueError, ArithmeticError):
            return default

    async def delivery_fee(self) -> Decimal:
        return self._decimal("delivery_fee", to_decimal(self.config.delivery_fee))

    async def free_delivery_from(self) -> Decimal:
        return self._decimal(
            "free_delivery_from", to_decimal(self.config.free_delivery_from)
        )

    async def min_order_amount(self) -> Decimal:
        return self._decimal(
            "min_order_amount", to_decimal(self.config.min_order_amount)
        )

    async def order_prefix(self) -> str:
        return self.config.order_prefix


__all__ = ["SETTING_KEYS", "SettingsService"]
