"""Domen modellari (eski import yo'llari uchun moslik qatlami).

Ilgari bu faylda SQLAlchemy modellari bor edi. Endi botda alohida baza
yo'q: barcha ma'lumot Laravel backend'dan olinadi. Shu sababli bu modul
endi `bot.domain` dagi DTO modellarni qayta eksport qiladi.

Bu klaviaturalar (`bot.keyboards`), `presenters` va handlerlarning
o'zgarishsiz ishlashini ta'minlaydi: ular `bot.database.models` dan
import qilishda davom etadi.
"""

from __future__ import annotations

from bot.domain import (
    Address,
    CartItem,
    Category,
    Customer,
    Order,
    OrderItem,
    Product,
    SupportRequest,
    User,
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
