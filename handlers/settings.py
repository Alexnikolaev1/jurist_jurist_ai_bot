# -*- coding: utf-8 -*-
"""
handlers/settings.py — личный кабинет: ФИО, адрес, телефон, страна/регион.
Эти данные используются для автоподстановки в юридические документы и
выбора актуальных экстренных контактов.
"""
import logging

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

import database as db
import keyboards as kb
from handlers.start import _prompt_disclaimer
from states import SettingsStates
from utils.text_utils import clean_text

logger = logging.getLogger(__name__)
router = Router(name="settings")


@router.message(F.text.in_({kb.BTN_SETTINGS, "/settings"}))
async def settings_entry(message: Message, state: FSMContext) -> None:
    if not await db.is_disclaimer_accepted(message.from_user.id):
        await _prompt_disclaimer(message)
        return
    profile = await db.get_user(message.from_user.id) or {}
    current = (
        f"Текущие данные:\n"
        f"ФИО: {profile.get('full_name') or '—'}\n"
        f"Адрес: {profile.get('address') or '—'}\n"
        f"Телефон: {profile.get('phone') or '—'}\n"
        f"Страна/регион: {profile.get('country') or 'RU'}\n\n"
        f"Эти данные используются для автоподстановки в документы.\n\n"
        f"Введите ваше ФИО полностью (или отправьте «-», чтобы оставить без изменений):"
    )
    await state.set_state(SettingsStates.full_name)
    await message.answer(current)


@router.message(SettingsStates.full_name)
async def settings_full_name(message: Message, state: FSMContext) -> None:
    text = clean_text(message.text or "")
    if text and text != "-":
        await state.update_data(full_name=text)
    await state.set_state(SettingsStates.address)
    await message.answer("Введите ваш адрес регистрации/проживания (или «-», чтобы пропустить):")


@router.message(SettingsStates.address)
async def settings_address(message: Message, state: FSMContext) -> None:
    text = clean_text(message.text or "")
    if text and text != "-":
        await state.update_data(address=text)
    await state.set_state(SettingsStates.phone)
    await message.answer("Введите ваш контактный телефон (или «-», чтобы пропустить):")


@router.message(SettingsStates.phone)
async def settings_phone(message: Message, state: FSMContext) -> None:
    text = clean_text(message.text or "")
    if text and text != "-":
        await state.update_data(phone=text)
    await state.set_state(SettingsStates.country)
    await message.answer("Введите страну/регион (например, RU) или «-», чтобы оставить по умолчанию:")


@router.message(SettingsStates.country)
async def settings_country(message: Message, state: FSMContext) -> None:
    text = clean_text(message.text or "")
    data = await state.get_data()
    if text and text != "-":
        data["country"] = text

    if data:
        await db.upsert_user(message.from_user.id, **data)

    await state.clear()
    await message.answer("✅ Настройки сохранены.", reply_markup=kb.main_menu_keyboard())
