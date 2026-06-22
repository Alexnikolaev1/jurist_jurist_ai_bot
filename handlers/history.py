# -*- coding: utf-8 -*-
"""
handlers/history.py — просмотр истории консультаций и удаление всех данных
пользователя (право на забвение / GDPR-подобный механизм).
"""
import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

import database as db
import keyboards as kb

logger = logging.getLogger(__name__)
router = Router(name="history")

_DOC_TYPE_LABELS = {
    "pretension": "Претензия",
    "claim": "Исковое заявление",
    "complaint_prosecutor": "Жалоба в прокуратуру",
    "complaint_rospotrebnadzor": "Жалоба в Роспотребнадзор",
    "labor_complaint": "Жалоба в трудовую инспекцию",
    "agreement": "Соглашение о расторжении",
}


def _confirm_delete_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🗑 Да, удалить всё", callback_data="confirm_delete_data"),
                InlineKeyboardButton(text="Отмена", callback_data="cancel_delete_data"),
            ]
        ]
    )


def _truncate(text: str, limit: int = 120) -> str:
    return (text[:limit] + "…") if len(text) > limit else text


@router.message(F.text.in_({kb.BTN_HISTORY, "/history"}))
async def show_history(message: Message) -> None:
    user_id = message.from_user.id
    consultations = await db.get_history(user_id, limit=5)
    documents = await db.get_document_history(user_id, limit=5)

    if not consultations and not documents:
        await message.answer("История пока пуста.")
        return

    lines: list[str] = []

    if consultations:
        lines.append("📋 <b>Последние консультации:</b>\n")
        for r in consultations:
            response_preview = _truncate(r.get("response") or "", 80)
            lines.append(
                f"🕐 {r['timestamp']}\n"
                f"❓ {_truncate(r['query'])}\n"
                f"💬 {response_preview}\n"
            )

    if documents:
        lines.append("\n📄 <b>Составленные документы:</b>\n")
        for d in documents:
            label = _DOC_TYPE_LABELS.get(d["doc_type"], d["doc_type"])
            lines.append(
                f"🕐 {d['timestamp']} — {label}\n"
                f"   <i>Скачать PDF:</i> /pdf_{d['id']}\n"
            )

    await message.answer("\n".join(lines))


@router.message(F.text.regexp(r"^/pdf_(\d+)$"))
async def resend_pdf_hint(message: Message) -> None:
    """Подсказка для повторного скачивания PDF — кнопка в истории."""
    import re
    match = re.match(r"^/pdf_(\d+)$", message.text or "")
    if not match:
        return
    doc_id = int(match.group(1))
    record = await db.get_document(doc_id, message.from_user.id)
    if not record:
        await message.answer("Документ не найден.")
        return
    await message.answer(
        "Нажмите кнопку ниже, чтобы скачать PDF:",
        reply_markup=kb.pdf_offer_keyboard(str(doc_id)),
    )


@router.message(F.text == "/delete_data")
async def delete_data_prompt(message: Message) -> None:
    await message.answer(
        "⚠️ Будут безвозвратно удалены: ваш профиль, история консультаций и "
        "составленных документов. Продолжить?",
        reply_markup=_confirm_delete_keyboard(),
    )


@router.callback_query(F.data == "confirm_delete_data")
async def confirm_delete_data(callback: CallbackQuery) -> None:
    await db.delete_user_data(callback.from_user.id)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        "✅ Все ваши данные удалены из бота. При необходимости можно начать заново через /start.",
        reply_markup=kb.main_menu_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "cancel_delete_data")
async def cancel_delete_data(callback: CallbackQuery) -> None:
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Удаление отменено.")
    await callback.answer()
