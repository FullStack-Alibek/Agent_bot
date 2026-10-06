"""Profil bo'limi: ma'lumotlar, telefon raqami va manzillar (TZ 4.4).

Profil «👤 Profil» reply tugmasi yoki inline menyudagi tugma
(`MenuCB(action="profile")`) orqali ochiladi:

    * ma'lumotlar - ism, telefon, til, toifa, qarzdorlik, manzil;
    * telefon raqamini yangilash - `ProfileStates.phone` holatida
      (kontakt tugmasi yoki qo'lda kiritilgan matn);
    * manzillar ro'yxati - mijozning saqlangan manzillari.

Tilni almashtirish tugmasi profildan chaqirilganda o'sha joyda yangilanadi.
"""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Contact, Message

from bot.database.enums import Language
from bot.database.models import Address
from bot.handlers.common import TARGET, currency, menu_markup, menu_text, restore_menu
from bot.handlers.states import ProfileStates
from bot.keyboards import (
    LangCB,
    MenuCB,
    ProfileCB,
    addresses_inline,
    phone_request,
    profile_inline,
    profile_language_inline,
    reply_button_filter,
)
from bot.locales import normalize_language
from bot.middlewares import BotContext
from bot.services.presenters import segment_label
from bot.utils.money import format_money
from bot.utils.rendering import answer_callback, render
from bot.utils.text import escape
from bot.utils.validators import is_valid_phone, normalize_phone

logger = logging.getLogger(__name__)


# ------------------------- Yordamchilar -------------------------------
def _address_text(address: Address) -> str:
    """Manzil matni (nomi bo'lsa - nomi bilan)."""
    if address.label:
        return f"{address.label}: {address.address}"
    return address.address


async def _addresses(ctx: BotContext) -> list[Address]:
    """Mijozning saqlangan manzillari (xodimlar uchun - bo'sh ro'yxat)."""
    if ctx.customer is None or ctx.customer.id is None:
        return []
    return await ctx.api.addresses(ctx.customer.id)


# ------------------------- Ekranlar ------------------------------------
async def show_profile(target: TARGET, ctx: BotContext) -> None:
    """Profil kartochkasi: aloqa ma'lumotlari va CRM ko'rsatkichlari."""
    t = ctx.t
    user = ctx.user
    unknown = t("profile_unknown")
    name = user.display_name if user is not None else unknown
    phone = (user.phone if user is not None else None) or unknown
    lines = [
        t("profile_title"),
        "",
        t("profile_name", value=escape(name)),
        t("profile_phone", value=escape(phone)),
        t("profile_language", value=escape(t("lang_name"))),
    ]
    customer = ctx.customer
    if customer is not None:
        lines.append(t("profile_segment", value=escape(segment_label(t, customer.segment))))
        lines.append(t("profile_debt", value=format_money(customer.debt_amount, currency(ctx))))
        addresses = await _addresses(ctx)
        default = next((item for item in addresses if item.is_default), None)
        if default is None and addresses:
            default = addresses[0]
        if default is not None:
            lines.append(t("profile_address", value=escape(_address_text(default))))
    await render(target, "\n".join(lines), profile_inline(t))


async def show_addresses(target: TARGET, ctx: BotContext) -> None:
    """«📍 Manzillarim» - saqlangan manzillar ro'yxati."""
    t = ctx.t
    addresses = await _addresses(ctx)
    if not addresses:
        await render(target, t("profile_addresses_empty"), addresses_inline(t))
        return
    lines = [t("profile_addresses_title"), ""]
    for index, address in enumerate(addresses, start=1):
        lines.append(
            t("profile_address_line", index=index, address=escape(_address_text(address)))
        )
    await render(target, "\n".join(lines), addresses_inline(t))


# ------------------------- Kirish nuqtalari ----------------------------
async def open_profile(message: Message, ctx: BotContext, state: FSMContext) -> None:
    """«👤 Profil» reply tugmasi."""
    await state.clear()
    await show_profile(message, ctx)


async def on_menu_profile(query: CallbackQuery, ctx: BotContext, state: FSMContext) -> None:
    """Inline menyudan «Profil» (`MenuCB`)."""
    await state.clear()
    await answer_callback(query)
    await show_profile(query, ctx)


async def on_profile(
    query: CallbackQuery, ctx: BotContext, callback_data: ProfileCB, state: FSMContext
) -> None:
    """Profil tugmalari: qaytish, manzillar, til va telefon."""
    action = callback_data.action
    if action == "addresses":
        await answer_callback(query)
        await show_addresses(query, ctx)
        return
    if action == "language":
        await answer_callback(query)
        await render(query, ctx.t("start_language_title"), profile_language_inline(ctx.t))
        return
    if action == "phone":
        await answer_callback(query)
        await ask_phone(query, ctx, state)
        return
    await answer_callback(query)
    await show_profile(query, ctx)


async def on_profile_language(
    query: CallbackQuery, callback_data: LangCB, ctx: BotContext, state: FSMContext
) -> None:
    """Profildan tilni o'zgartirish va profelni yangi tilda qayta ko'rsatish."""
    code = normalize_language(callback_data.code)
    try:
        if ctx.customer_id is not None:
            await ctx.api.set_language(ctx.customer_id, code)
        elif ctx.user is not None:
            await ctx.api.sync_customer(
                telegram_id=ctx.user.telegram_id,
                name=ctx.user.display_name,
                username=ctx.user.username,
                language=code,
                chat_id=ctx.chat_id,
            )
    except Exception as exc:
        logger.error("Profilda tilni saqlashda xatolik: %s", exc)

    ctx.language = code
    await state.clear()

    t = ctx.t
    await answer_callback(query, t("lang_changed", language=t("lang_name")))
    await show_profile(query, ctx)
    logger.info("Profil ichidan til o'zgartirildi: user=%s -> %s", ctx.user_id, code)


# ------------------------- Telefon raqami ------------------------------
async def ask_phone(target: TARGET, ctx: BotContext, state: FSMContext) -> None:
    """Kutish holatini o'rnatadi va raqam so'rash klaviaturasini yuboradi."""
    await state.set_state(ProfileStates.phone)
    prompt = ctx.t("profile_phone_prompt")
    markup = phone_request(ctx.t, with_cancel=True)
    if isinstance(target, Message):
        await target.answer(prompt, reply_markup=markup)
        return
    if target.message is not None:  # callback xabari mavjud bo'lsa
        await target.message.answer(prompt, reply_markup=markup)


async def _save_phone(
    message: Message, ctx: BotContext, state: FSMContext, phone: str
) -> None:
    """Raqamni backend API orqali yozadi, holatni tozalaydi va profilni qayta ko'rsatadi."""
    try:
        if ctx.customer_id is not None:
            await ctx.api.set_phone(ctx.customer_id, phone)
        elif ctx.user is not None:
            await ctx.api.sync_customer(
                telegram_id=ctx.user.telegram_id,
                name=ctx.user.display_name,
                phone=phone,
                username=ctx.user.username,
                language=ctx.language,
                chat_id=ctx.chat_id,
            )
            ctx.user.phone = phone
    except Exception as exc:
        logger.error("Profil telefonini saqlashda xatolik: %s", exc)

    await state.clear()
    await message.answer(ctx.t("profile_phone_updated"), reply_markup=menu_markup(ctx))
    await show_profile(message, ctx)
    logger.info("Telefon yangilandi: user=%s", ctx.user_id)


async def on_phone_contact(message: Message, ctx: BotContext, state: FSMContext) -> None:
    """«📱 Raqamni ulashish» tugmasi orqali kelgan kontakt."""
    contact: Contact | None = message.contact
    if contact is None or not contact.phone_number:
        return
    await _save_phone(message, ctx, state, normalize_phone(contact.phone_number))


async def on_phone_text(message: Message, ctx: BotContext, state: FSMContext) -> None:
    """Raqam qo'lda yozilganda."""
    text = (message.text or "").strip()
    if not is_valid_phone(text):
        await message.answer(
            ctx.t("phone_invalid"), reply_markup=phone_request(ctx.t, with_cancel=True)
        )
        return
    await _save_phone(message, ctx, state, normalize_phone(text))


async def cancel_phone(message: Message, ctx: BotContext, state: FSMContext) -> None:
    """«❌ Bekor qilish» - raqam so'rash to'xtatiladi, profil qaytadi."""
    await state.clear()
    await restore_menu(message, ctx)
    await show_profile(message, ctx)


def build_router() -> Router:
    """Yangi `profile` router yasaydi."""
    router = Router(name="profile")

    router.message.register(open_profile, reply_button_filter("btn_profile"))

    router.callback_query.register(on_menu_profile, MenuCB.filter(F.action == "profile"))
    router.callback_query.register(on_profile, ProfileCB.filter())
    router.callback_query.register(on_profile_language, LangCB.filter(F.action == "set"))

    router.message.register(
        cancel_phone, StateFilter(ProfileStates.phone), reply_button_filter("btn_cancel")
    )
    router.message.register(on_phone_contact, StateFilter(ProfileStates.phone), F.contact)
    router.message.register(on_phone_text, StateFilter(ProfileStates.phone), F.text, menu_text)
    return router


__all__ = [
    "ask_phone",
    "build_router",
    "cancel_phone",
    "on_menu_profile",
    "open_profile",
    "show_addresses",
    "show_profile",
]
