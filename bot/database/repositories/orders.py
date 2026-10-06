"""Buyurtmalar repozitoriyasi (Laravel Backend API ga o'tganligi sababli eski SQLAlchemy modellar tozalandi)."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

from bot.database.enums import (
    DeliveryType,
    OrderSource,
    OrderStatus,
    PaymentMethod,
    PaymentProvider,
    PaymentStatus,
    Unit,
)
from bot.database.models import Order, OrderItem, User
from bot.database.repositories.base import BaseRepository

MONEY_STEP = Decimal("0.01")


class OrderRepository(BaseRepository[Order]):
    """`orders`, `order_items` uchun legacy/stub repozitoriy."""

    model = Order


__all__ = ["OrderRepository"]
