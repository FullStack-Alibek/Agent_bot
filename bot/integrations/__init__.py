"""Backend (Laravel) bilan integratsiya qatlami.

Bot biznes ma'lumotlarini (katalog, mijoz, buyurtma) backend'dan olishi yoki
backend'ga yozishi mumkin. Bu paket HTTP orqali ishlaydi va botning ichki
ma'lumotlar bazasiga bog'liq emas.
"""

from bot.integrations.backend import (
    BackendCatalogItem,
    BackendClient,
    BackendCustomer,
    BackendError,
    BackendNotConfiguredError,
    BackendOrderSummary,
)

__all__ = [
    "BackendCatalogItem",
    "BackendClient",
    "BackendCustomer",
    "BackendError",
    "BackendNotConfiguredError",
    "BackendOrderSummary",
]
