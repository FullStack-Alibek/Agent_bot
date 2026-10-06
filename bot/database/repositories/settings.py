"""Tizim sozlamalari repozitoriyasi (Laravel Backend API va SettingsService ga o'tganligi sababli eski SQLAlchemy kodi tozalandi)."""

from __future__ import annotations

from bot.database.repositories.base import BaseRepository


class SettingRepository:
    """Legacy/stub repozitoriy."""

    pass


__all__ = ["SettingRepository"]
