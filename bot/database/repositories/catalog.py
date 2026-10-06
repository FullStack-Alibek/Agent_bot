"""Katalog repozitoriylari (Laravel Backend API ga o'tganligi sababli eski SQLAlchemy kodi tozalandi)."""

from __future__ import annotations

from bot.database.repositories.base import BaseRepository


class CategoryRepository:
    """Legacy/stub repozitoriy."""

    pass


class ProductRepository:
    """Legacy/stub repozitoriy."""

    pass


__all__ = ["CategoryRepository", "ProductRepository"]
