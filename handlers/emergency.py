# -*- coding: utf-8 -*-
"""
handlers/emergency.py — экстренный протокол при задержании, обыске, допросе
и т.п. Срабатывает как по кнопке меню, так и автоматически при обнаружении
тревожных ключевых слов в обычной консультации (см. handlers/consult.py).
"""
import json
import logging
import os

from aiogram import Router, F
from aiogram.types import Message

import config
import keyboards as kb

logger = logging.getLogger(__name__)
router = Router(name="emergency")

EMERGENCY_PROTOCOL_TEXT = (
    "🆘 <b>Экстренный протокол</b>\n\n"
    "1. Сохраняйте спокойствие, не оказывайте сопротивления и не вступайте "
    "в конфликт.\n"
    "2. Вы имеете право хранить молчание и не свидетельствовать против себя "
    "и близких родственников (<b>ст. 51 Конституции РФ</b>).\n"
    "3. Вы имеете право на немедленный звонок адвокату и на его присутствие "
    "при любых процессуальных действиях (<b>ст. 14, 16, 49–53 УПК РФ</b>, "
    "<b>ст. 48 Конституции РФ</b>).\n"
    "4. Не подписывайте никакие документы и не давайте показания до прибытия "
    "адвоката.\n"
    "5. Попросите назвать причину и основание задержания, представиться "
    "и предъявить служебное удостоверение.\n"
    "6. Запомните или зафиксируйте ФИО и должности сотрудников, номер "
    "протокола, время и место.\n"
    "7. Если есть возможность — сообщите близким или адвокату о случившемся "
    "(один звонок гарантирован законом).\n\n"
    "Ниже — контакты бесплатной юридической помощи."
)


def _load_emergency_contacts(country: str = "RU") -> list[dict]:
    if not os.path.exists(config.EMERGENCY_CONTACTS_PATH):
        return []
    with open(config.EMERGENCY_CONTACTS_PATH, "r", encoding="utf-8") as f:
        all_contacts = json.load(f)
    # Фильтр по стране, если в JSON указано поле country; иначе — общие контакты.
    filtered = [
        c for c in all_contacts
        if not c.get("country") or c.get("country", "").upper() == country.upper()
    ]
    return filtered or all_contacts


def _format_contacts(contacts: list[dict]) -> str:
    if not contacts:
        return (
            "⚠️ Список контактов экстренной юридической помощи пока не "
            "заполнен в data/emergency_contacts.json."
        )
    lines = []
    for c in contacts:
        line = f"• <b>{c.get('name', '')}</b>"
        if c.get("phone"):
            line += f" — {c['phone']}"
        if c.get("note"):
            line += f"\n  {c['note']}"
        if c.get("url"):
            line += f"\n  {c['url']}"
        lines.append(line)
    return "\n\n".join(lines)


async def send_emergency_protocol(message: Message) -> None:
    """Отправляет экстренный протокол и контакты. Вызывается из consult.py и по кнопке."""
    import database as db
    profile = await db.get_user(message.from_user.id) or {}
    country = profile.get("country") or "RU"
    contacts = _load_emergency_contacts(country)
    await message.answer(EMERGENCY_PROTOCOL_TEXT)
    await message.answer(_format_contacts(contacts), reply_markup=kb.main_menu_keyboard())


@router.message(F.text == kb.BTN_EMERGENCY)
async def emergency_button(message: Message) -> None:
    await send_emergency_protocol(message)


@router.message(F.text == "/emergency")
async def emergency_command(message: Message) -> None:
    await send_emergency_protocol(message)
