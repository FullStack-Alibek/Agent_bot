"""Buyurtma servisi (TZ 4.1.6 / 4.4).

Buyurtmalar Laravel backend'da saqlanadi va boshqariladi. Bu servis backend
API orqali ishlaydi. Bu yerdagi `customer_id` - backend `customers.id`.
"""

from __future__ import annotations

import uuid as uuid_lib
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from bot.api import BackendClient
from bot.config import Settings
from bot.database.enums import (
    CustomerSegment,
    DeliveryType,
    OrderSource,
    OrderStatus,
    PaymentMethod,
    PaymentStatus,
)
from bot.domain import Order, Product, User
from bot.services.cart import CartService
from bot.services.errors import (
    AddressRequiredError,
    NotFoundError,
    NotCancellableError,
    StatusSameError,
    StatusTransitionError,
)
from bot.utils.money import ZERO, round_money, to_decimal
from bot.utils.pagination import Pagination, paginate

#: TZ 4.1.6: ruxsat etilgan holat o'tishlari (bot tomonidagi ko'rsatma).
TRANSITIONS: dict[OrderStatus, tuple[OrderStatus, ...]] = {
    OrderStatus.NEW: (OrderStatus.CONFIRMED, OrderStatus.CANCELLED),
    OrderStatus.CONFIRMED: (OrderStatus.PICKING, OrderStatus.CANCELLED),
    OrderStatus.PICKING: (
        OrderStatus.ON_THE_WAY,
        OrderStatus.DELIVERED,
        OrderStatus.CANCELLED,
    ),
    OrderStatus.ON_THE_WAY: (
        OrderStatus.DELIVERED,
        OrderStatus.PARTIALLY_DELIVERED,
        OrderStatus.RETURNED,
    ),
    OrderStatus.PARTIALLY_DELIVERED: (OrderStatus.DELIVERED, OrderStatus.RETURNED),
    OrderStatus.DELIVERED: (),
    OrderStatus.CANCELLED: (),
    OrderStatus.RETURNED: (),
}

#: Mijoz o'zi bekor qila oladigan holatlar.
CUSTOMER_CANCELLABLE: tuple[OrderStatus, ...] = (OrderStatus.NEW, OrderStatus.CONFIRMED)

#: Ombor qoldig'i qaytariladigan holatlar.
STOCK_RELEASE_STATUSES: frozenset[OrderStatus] = frozenset(
    {OrderStatus.CANCELLED, OrderStatus.RETURNED}
)

#: Mijoz segmenti chegaralari (yetkazilgan buyurtmalar soni).
REGULAR_FROM = 3
VIP_FROM = 10


@dataclass(slots=True)
class CheckoutData:
    """Buyurtma berish FSM yakunidagi ma'lumotlar."""

    delivery_type: DeliveryType = DeliveryType.DELIVERY
    address: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    delivery_time: str | None = None
    comment: str | None = None
    payment_method: PaymentMethod = PaymentMethod.CASH
    customer_name: str | None = None
    customer_phone: str | None = None
    source: OrderSource = OrderSource.BOT
    save_address: bool = True


@dataclass(slots=True)
class StatusChange:
    """Holat o'zgarishi natijasi (xabar yuborish uchun bayroqlar bilan)."""

    order: Order
    old_status: OrderStatus
    new_status: OrderStatus
    stock_deducted: bool = False
    stock_released: bool = False

    @property
    def is_cancelled(self) -> bool:
        return self.new_status in STOCK_RELEASE_STATUSES

    @property
    def is_delivered(self) -> bool:
        return self.new_status in {
            OrderStatus.DELIVERED,
            OrderStatus.PARTIALLY_DELIVERED,
        }


class OrderService:
    """Buyurtmalar bilan ishlashning yagona kirish nuqtasi (backend API)."""

    def __init__(self, api: BackendClient, settings: Settings) -> None:
        self.api = api
        self.settings = settings
        self.cart = CartService(api, settings)

    # ------------------------- Yaratish --------------------------------
    async def create_from_cart(self, customer_id: int, data: CheckoutData) -> Order:
        """Savatdagi mahsulotlardan buyurtma yaratadi va savatni tozalaydi."""
        address = (data.address or "").strip() or None
        if data.delivery_type is DeliveryType.DELIVERY and not address:
            raise AddressRequiredError()

        summary = await self.cart.validate_for_checkout(
            customer_id, delivery_type=data.delivery_type
        )

        if address and data.save_address:
            try:
                await self.api.store_address(
                    customer_id,
                    address=address,
                    latitude=data.latitude,
                    longitude=data.longitude,
                )
            except Exception:  # manzil saqlash majburiy emas
                pass

        items = [
            {
                "product_id": line.product.id,
                "quantity": float(line.quantity),
                "unit_price": float(line.price),
            }
            for line in summary.lines
        ]

        order = await self.api.create_order(
            customer_id=customer_id,
            items=items,
            delivery_type=str(data.delivery_type),
            delivery_address=address,
            latitude=data.latitude,
            longitude=data.longitude,
            shipping_amount=float(summary.delivery_fee),
            note=data.comment,
            idempotency_key=str(uuid_lib.uuid4()),
        )
        return order

    # ------------------------- O'qish ----------------------------------
    async def get_full(self, customer_id: int, order_key: int | str | None) -> Order:
        if order_key in (None, ""):
            raise NotFoundError()
        try:
            return await self.api.order(customer_id, order_key)
        except Exception as exc:
            raise NotFoundError() from exc

    async def get_for_user(self, customer_id: int, order_key: int | str | None) -> Order:
        return await self.get_full(customer_id, order_key)

    async def page_for_user(
        self, customer_id: int, *, page: int = 1, per_page: int | None = None
    ) -> tuple[list[Order], Pagination]:
        size = per_page or self.settings.orders_per_page
        orders, total = await self.api.orders(customer_id, page=page, per_page=size)
        pagination = paginate(total, page, size)
        return orders, pagination

    async def history(self, order_uuid: str) -> list:
        # Backend buyurtma kartochkasida holat tarixi alohida berilmaydi.
        return []

    # ------------------------- Holatlar zanjiri ------------------------
    @staticmethod
    def allowed_transitions(status: OrderStatus | str) -> tuple[OrderStatus, ...]:
        return TRANSITIONS.get(OrderStatus(str(status)), ())

    @classmethod
    def can_customer_cancel(cls, order: Order) -> bool:
        return OrderStatus(str(order.status)) in CUSTOMER_CANCELLABLE

    async def cancel_by_customer(
        self, customer_id: int, order: Order, reason: str | None = None
    ) -> StatusChange:
        """Mijozning o'zi bekor qilishi (faqat Yangi/Tasdiqlangan)."""
        if not self.can_customer_cancel(order):
            raise NotCancellableError()
        old = order.status
        updated = await self.api.cancel_order(customer_id, order.id, reason=reason)
        return StatusChange(
            order=updated, old_status=old, new_status=OrderStatus.CANCELLED
        )

    # ------------------------- Takrorlash ------------------------------
    async def repeat(self, customer_id: int, order: Order) -> int:
        """Buyurtma tarkibini savatga qaytaradi; qo'shilgan pozitsiyalar soni."""
        if not order.id:
            return 0
        return await self.api.repeat_order(customer_id, order.id)

    # ------------------------- Statistika ------------------------------
    @staticmethod
    def day_bounds(day: date | None = None) -> tuple[datetime, datetime]:
        target = day or datetime.utcnow().date()
        start = datetime.combine(target, time.min)
        return start, start + timedelta(days=1)

    async def active_order_counts(self) -> dict[str, int]:
        """Yangi va faol buyurtmalar soni (admin menyu uchun)."""
        return {"new": 0, "active": 0}


__all__ = [
    "CUSTOMER_CANCELLABLE",
    "CheckoutData",
    "OrderService",
    "REGULAR_FROM",
    "STOCK_RELEASE_STATUSES",
    "StatusChange",
    "TRANSITIONS",
    "VIP_FROM",
]
