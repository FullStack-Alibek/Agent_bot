"""Domen modellari (DTO) - backend JSON'idan to'ldiriladi.

Botda alohida baza yo'q: barcha ma'lumot Laravel backend'dan HTTP orqali
olinadi. Bu modullar backend javobini **SQLAlchemy modellari bilan bir xil
interfeys** beradigan oddiy obyektlarga aylantiradi. Shu sababli handlerlar,
klaviaturalar va `presenters` kodi umuman o'zgarmaydi.

Muhim: bu yerda SQLAlchemy, session va `select` YO'Q. Faqat `dataclass`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from bot.database.enums import (
    CustomerSegment,
    DeliveryType,
    OrderSource,
    OrderStatus,
    PaymentMethod,
    PaymentProvider,
    PaymentStatus,
    SupportStatus,
    Unit,
    UserRole,
)
from bot.utils.money import round_money as money, to_decimal


def _dt(value: Any) -> datetime | None:
    """ISO matnni `datetime` ga aylantiradi (bo'lmasa - `None`)."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    # SQLite/naive bilan bir xil bo'lishi uchun TZ olib tashlanadi.
    if parsed.tzinfo is not None:
        parsed = parsed.replace(tzinfo=None)
    return parsed


def _enum(cls, value: Any, default):
    """Enum qiymatini xavfsiz aylantiradi (noto'g'ri bo'lsa - standart)."""
    if value is None or value == "":
        return default
    try:
        return cls(str(value).lower())
    except ValueError:
        return default


# =====================================================================
# Katalog
# =====================================================================
@dataclass(slots=True)
class Category:
    """Mahsulot kategoriyasi (backend `categories`)."""

    id: int
    name: str
    emoji: str = ""
    sort_order: int = 100
    parent_id: int | None = None
    is_active: bool = True
    products: int = 0

    @property
    def name_uz(self) -> str:
        return self.name

    @property
    def name_ru(self) -> str:
        return self.name

    def localized_name(self, lang: str = "uz") -> str:
        return self.name

    def button_label(self, lang: str = "uz") -> str:
        return f"{self.emoji} {self.localized_name(lang)}".strip()

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Category:
        return cls(
            id=int(data.get("id", 0)),
            name=str(data.get("name") or data.get("name_uz") or ""),
            emoji=str(data.get("emoji") or ""),
            sort_order=int(data.get("sort_order") or 100),
            parent_id=data.get("parent_id"),
            is_active=bool(data.get("is_active", True)),
            products=int(data.get("products") or 0),
        )


@dataclass(slots=True)
class Product:
    """Mahsulot (backend `products` + bot uchun moslashtirilgan maydonlar)."""

    id: int
    sku: str
    name: str
    price: Decimal
    description: str | None = None
    discount_price: Decimal | None = None
    wholesale_price: Decimal | None = None
    category_id: int | None = None
    category_name: str | None = None
    unit: Unit = Unit.PCS
    box_size: int = 1
    stock: Decimal = Decimal("0")
    min_stock: Decimal = Decimal("0")
    barcode: str | None = None
    image_url: str | None = None
    is_active: bool = True
    is_promo: bool = False
    sort_order: int = 100

    # -----------------------------------------------------------------
    @property
    def name_uz(self) -> str:
        return self.name

    @property
    def name_ru(self) -> str:
        return self.name

    def localized_name(self, lang: str = "uz") -> str:
        return self.name

    def localized_description(self, lang: str = "uz") -> str | None:
        return self.description

    @property
    def image_file_id(self) -> str | None:
        """Eski handler'lar bilan moslik uchun (image_url -> image_file_id)."""
        return self.image_url

    @property
    def has_discount(self) -> bool:
        return (
            self.discount_price is not None
            and self.discount_price > 0
            and self.discount_price < self.price
        )

    @property
    def effective_price(self) -> Decimal:
        if self.has_discount and self.discount_price is not None:
            return money(self.discount_price)
        return money(self.price)

    @property
    def discount_percent(self) -> int:
        if not self.has_discount or not self.price:
            return 0
        ratio = (Decimal(1) - self.effective_price / money(self.price)) * 100
        return int(ratio.quantize(Decimal("1")))

    @property
    def in_stock(self) -> bool:
        return Decimal(self.stock or 0) > 0

    @property
    def is_low_stock(self) -> bool:
        return Decimal(self.stock or 0) <= Decimal(self.min_stock or 0)

    @property
    def step(self) -> Decimal:
        if self.unit is Unit.BOX:
            return Decimal(max(self.box_size, 1))
        return Decimal(self.unit.step)

    @property
    def box_price(self) -> Decimal | None:
        if self.box_size and self.box_size > 1:
            return money(self.effective_price * self.box_size)
        return None

    # -----------------------------------------------------------------
    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Product:
        price = money(data.get("price") or data.get("sale_price") or 0)
        discount = data.get("discount_price")
        wholesale = data.get("wholesale") or data.get("wholesale_price")
        return cls(
            id=int(data.get("id", 0)),
            sku=str(data.get("sku") or ""),
            name=str(data.get("name") or ""),
            price=price,
            description=data.get("description"),
            discount_price=money(discount) if discount not in (None, 0, "0") else None,
            wholesale_price=money(wholesale) if wholesale not in (None, 0, "0") else None,
            category_id=data.get("category_id"),
            category_name=data.get("category"),
            unit=_enum(Unit, data.get("unit"), Unit.PCS),
            box_size=int(data.get("box_size") or 1),
            stock=to_decimal(data.get("stock"), Decimal("0")),
            min_stock=to_decimal(data.get("min_stock"), Decimal("0")),
            barcode=data.get("barcode"),
            image_url=data.get("image_url"),
            is_active=bool(data.get("is_active", True)),
            is_promo=bool(data.get("is_promo", False)),
            sort_order=int(data.get("sort_order") or 100),
        )


# =====================================================================
# Savat
# =====================================================================
@dataclass(slots=True)
class CartItem:
    """Savat pozitsiyasi (backend `cart_items`)."""

    product_id: int
    quantity: Decimal
    product: Product | None = None
    id: int | None = None

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> CartItem:
        product_data = data.get("product")
        return cls(
            id=data.get("id"),
            product_id=int(data.get("product_id", 0)),
            quantity=to_decimal(data.get("quantity"), Decimal("1")),
            product=Product.from_api(product_data) if product_data else None,
        )


# =====================================================================
# Manzillar
# =====================================================================
@dataclass(slots=True)
class Address:
    """Mijozning saqlangan manzili."""

    id: int
    address: str
    label: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    is_default: bool = False

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Address:
        return cls(
            id=int(data.get("id", 0)),
            address=str(data.get("address") or ""),
            label=data.get("label"),
            latitude=data.get("latitude"),
            longitude=data.get("longitude"),
            is_default=bool(data.get("is_default", False)),
        )


# =====================================================================
# Foydalanuvchi / mijoz
# =====================================================================
@dataclass(slots=True)
class User:
    """Bot foydalanuvchisi (xodim yoki mijoz)."""

    id: int
    telegram_id: int
    chat_id: int | None = None
    username: str | None = None
    full_name: str | None = None
    phone: str | None = None
    language: str = "uz"
    role: UserRole = UserRole.CLIENT
    is_active: bool = True
    is_blocked: bool = False

    @property
    def display_name(self) -> str:
        if self.full_name:
            return self.full_name
        if self.username:
            return f"@{self.username}"
        return f"ID {self.telegram_id}"

    @property
    def is_staff(self) -> bool:
        return self.role.is_staff

    @property
    def has_phone(self) -> bool:
        return bool(self.phone)

    @classmethod
    def from_telegram(cls, tg_user, *, language: str = "uz", role: UserRole = UserRole.CLIENT) -> User:
        return cls(
            id=int(tg_user.id),
            telegram_id=int(tg_user.id),
            chat_id=int(tg_user.id),
            username=tg_user.username,
            full_name=tg_user.full_name,
            language=language,
            role=role,
        )


@dataclass(slots=True)
class Customer:
    """Mijoz kartochkasi (backend `customers`)."""

    id: int
    name: str = ""
    phone: str | None = None
    telegram_id: int | None = None
    chat_id: int | None = None
    username: str | None = None
    language: str = "uz"
    status: str = "active"
    segment: CustomerSegment = CustomerSegment.NEW
    debt_amount: Decimal = Decimal("0")
    credit_limit: Decimal = Decimal("0")
    address: str | None = None

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Customer:
        return cls(
            id=int(data.get("id", 0)),
            name=str(data.get("name") or ""),
            phone=data.get("phone"),
            telegram_id=data.get("telegram_id"),
            chat_id=data.get("chat_id"),
            username=data.get("username"),
            language=str(data.get("language") or "uz"),
            status=str(data.get("status") or "active"),
            segment=_enum(CustomerSegment, data.get("segment"), CustomerSegment.NEW),
            debt_amount=to_decimal(data.get("debt"), Decimal("0")),
            credit_limit=to_decimal(data.get("credit_limit"), Decimal("0")),
            address=data.get("address"),
        )


# =====================================================================
# Buyurtma
# =====================================================================
@dataclass(slots=True)
class OrderItem:
    """Buyurtma satri (snapshot)."""

    name: str
    quantity: Decimal
    unit_price: Decimal
    total: Decimal
    product_id: int | None = None
    sku: str | None = None
    unit: Unit = Unit.PCS
    box_size: int = 1
    discount: Decimal = Decimal("0")

    def localized_name(self, lang: str = "uz") -> str:
        return self.name

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> OrderItem:
        return cls(
            name=str(data.get("name") or ""),
            quantity=to_decimal(data.get("quantity"), Decimal("0")),
            unit_price=to_decimal(data.get("unit_price"), Decimal("0")),
            total=to_decimal(data.get("total"), Decimal("0")),
            product_id=data.get("product_id"),
            sku=data.get("sku"),
            unit=_enum(Unit, data.get("unit"), Unit.PCS),
        )


@dataclass(slots=True)
class Order:
    """Buyurtma (backend `orders`)."""

    id: int
    number: str
    status: OrderStatus = OrderStatus.NEW
    payment_status: PaymentStatus = PaymentStatus.UNPAID
    payment_method: PaymentMethod = PaymentMethod.CASH
    source: OrderSource = OrderSource.BOT
    delivery_type: DeliveryType = DeliveryType.DELIVERY
    address: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    delivery_time: str | None = None
    customer_name: str | None = None
    customer_phone: str | None = None
    comment: str | None = None
    cancel_reason: str | None = None
    subtotal: Decimal = Decimal("0")
    discount_total: Decimal = Decimal("0")
    delivery_fee: Decimal = Decimal("0")
    total: Decimal = Decimal("0")
    paid_amount: Decimal = Decimal("0")
    stock_deducted: bool = False
    created_at: datetime | None = None
    uuid: str | None = None
    user_id: int | None = None
    items: list[OrderItem] = field(default_factory=list)

    # -----------------------------------------------------------------
    @property
    def is_cancellable(self) -> bool:
        return self.status in {OrderStatus.NEW, OrderStatus.CONFIRMED}

    @property
    def is_paid(self) -> bool:
        return self.payment_status is PaymentStatus.PAID

    @property
    def positions(self) -> int:
        return len(self.items)

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Order:
        return cls(
            id=int(data.get("id") or 0),
            uuid=data.get("uuid"),
            number=str(data.get("order_number") or data.get("number") or ""),
            status=_enum(OrderStatus, data.get("status"), OrderStatus.NEW),
            payment_status=_enum(PaymentStatus, data.get("payment_status"), PaymentStatus.UNPAID),
            delivery_type=_enum(DeliveryType, data.get("delivery_type"), DeliveryType.DELIVERY),
            address=data.get("delivery_address") or data.get("address"),
            latitude=data.get("delivery_latitude"),
            longitude=data.get("delivery_longitude"),
            comment=data.get("note") or data.get("comment"),
            cancel_reason=data.get("cancel_reason"),
            subtotal=to_decimal(data.get("subtotal"), Decimal("0")),
            discount_total=to_decimal(data.get("discount"), Decimal("0")),
            delivery_fee=to_decimal(data.get("shipping"), Decimal("0")),
            total=to_decimal(data.get("total"), Decimal("0")),
            paid_amount=to_decimal(data.get("paid"), Decimal("0")),
            created_at=_dt(data.get("created_at")),
            items=[OrderItem.from_api(item) for item in (data.get("items") or [])],
        )


# =====================================================================
# Qo'llab-quvvatlash
# =====================================================================
@dataclass(slots=True)
class SupportRequest:
    """Murojaat (backend `support_requests`)."""

    id: int
    message: str
    status: SupportStatus = SupportStatus.OPEN
    answer: str | None = None
    created_at: datetime | None = None
    user: User | None = None

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> SupportRequest:
        return cls(
            id=int(data.get("id", 0)),
            message=str(data.get("message") or ""),
            status=_enum(SupportStatus, data.get("status"), SupportStatus.OPEN),
            answer=data.get("answer"),
            created_at=_dt(data.get("created_at")),
        )


__all__ = [
    "Address",
    "CartItem",
    "Category",
    "Customer",
    "Order",
    "OrderItem",
    "Product",
    "SupportRequest",
    "User",
]
