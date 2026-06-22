# -*- coding: utf-8 -*-
"""
handlers/start.py — приветствие, дисклеймер и главное меню.
"""
import logging

from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery

import config
import database as db
import keyboards as kb
from utils.filters import DisclaimerNotAcceptedFilter, NoActiveFsmFilter, NotMenuButtonFilter

logger = logging.getLogger(__name__)
router = Router(name="start")


async def _prompt_disclaimer(message: Message) -> None:
    await message.answer(config.DISCLAIMER, reply_markup=kb.disclaimer_keyboard())


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    user = message.from_user
    await db.upsert_user(user.id, full_name=user.full_name or "")

    if await db.is_disclaimer_accepted(user.id):
        await message.answer(
            "С возвращением! Чем могу помочь?",
            reply_markup=kb.main_menu_keyboard(),
        )
        return

    await _prompt_disclaimer(message)


@router.callback_query(F.data == "accept_disclaimer")
async def accept_disclaimer(callback: CallbackQuery) -> None:
    await db.accept_disclaimer(callback.from_user.id)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        "Чем могу помочь? Опишите свою ситуацию текстом или голосом — я найду "
        "подходящие статьи закона и подскажу алгоритм действий.\n\n"
        "Также доступны разделы ниже 👇",
        reply_markup=kb.main_menu_keyboard(),
    )
    await callback.answer()


@router.message(F.text == "/help")
async def cmd_help(message: Message) -> None:
    if not await db.is_disclaimer_accepted(message.from_user.id):
        await _prompt_disclaimer(message)
        return

    await message.answer(
        "📚 <b>Что я умею:</b>\n\n"
        "⚖️ <b>Консультация</b> — опишите ситуацию текстом или голосом, я найду "
        "релевантные статьи закона и дам пошаговый план действий.\n"
        "📄 <b>Документ</b> — составлю претензию, иск, жалобу и другие документы.\n"
        "🔍 <b>Проверка договора</b> — пришлите фото договора, найду рискованные условия.\n"
        "🆘 <b>Экстренно</b> — что делать при задержании, обыске, угрозах.\n"
        "📋 <b>История</b> — последние консультации и документы.\n"
        "⚙️ <b>Настройки</b> — ваши данные для подстановки в документы.\n\n"
        "Команда /delete_data удалит все ваши данные из бота.",
        reply_markup=kb.main_menu_keyboard(),
    )


@router.message(
    F.text & ~F.text.startswith("/"),
    NotMenuButtonFilter(),
    DisclaimerNotAcceptedFilter(),
    NoActiveFsmFilter(),
)
async def require_disclaimer(message: Message) -> None:
    """Перехватывает произвольный текст от пользователей без принятого дисклеймера."""
    await _prompt_disclaimer(message)
