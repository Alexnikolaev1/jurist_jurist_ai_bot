# -*- coding: utf-8 -*-
"""
keyboards.py — общие клавиатуры (reply и inline), переиспользуемые во
всех хендлерах.
"""
from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

BTN_CONSULT = "⚖️ Консультация"
BTN_DOCUMENT = "📄 Документ"
BTN_CONTRACT = "🔍 Проверка договора"
BTN_HISTORY = "📋 История"
BTN_SETTINGS = "⚙️ Настройки"
BTN_EMERGENCY = "🆘 Экстренно"


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    """Главное меню бота — отображается всегда внизу экрана."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_CONSULT), KeyboardButton(text=BTN_DOCUMENT)],
            [KeyboardButton(text=BTN_CONTRACT), KeyboardButton(text=BTN_HISTORY)],
            [KeyboardButton(text=BTN_SETTINGS), KeyboardButton(text=BTN_EMERGENCY)],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def disclaimer_keyboard() -> InlineKeyboardMarkup:
    """Кнопка подтверждения дисклеймера при /start."""
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="✅ Продолжить", callback_data="accept_disclaimer")]]
    )


def document_types_keyboard(document_types: list[dict]) -> InlineKeyboardMarkup:
    """Список типов документов для команды /document."""
    rows = [
        [InlineKeyboardButton(text=dt["title"], callback_data=f"doctype:{dt['id']}")]
        for dt in document_types
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def pdf_offer_keyboard(doc_log_id: str) -> InlineKeyboardMarkup:
    """Предложение скачать документ в формате PDF."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📥 Скачать PDF", callback_data=f"makepdf:{doc_log_id}")]
        ]
    )


def confirm_cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm_doc"),
                InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_doc"),
            ]
        ]
    )
