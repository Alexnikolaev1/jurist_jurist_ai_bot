# -*- coding: utf-8 -*-
"""
handlers/document.py — генерация юридических документов: выбор типа,
пошаговый сбор недостающих данных (FSM), заполнение шаблона через Gemini,
отправка текстом и (опционально) PDF.
"""
import datetime
import json
import logging
import os

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, FSInputFile

import config
import database as db
import keyboards as kb
from services import gemini_service, pdf_service
from services.gemini_service import GeminiRateLimitError
from services.law_search import find_relevant_laws
from states import DocumentStates
from utils.text_utils import clean_text, split_long_message

logger = logging.getLogger(__name__)
router = Router(name="document")

# Человекочитаемые вопросы для каждого возможного поля шаблона.
FIELD_LABELS: dict[str, str] = {
    "full_name": "Ваше ФИО полностью",
    "address": "Ваш адрес регистрации/проживания",
    "phone": "Ваш контактный телефон",
    "recipient_name": "Наименование организации/ИП — получателя претензии",
    "recipient_address": "Адрес получателя претензии",
    "court_name": "Название и адрес суда, куда подаётся иск",
    "defendant_name": "ФИО / наименование ответчика",
    "defendant_address": "Адрес ответчика",
    "prosecutor_office": "Наименование прокуратуры (например: прокуратура Ленинского района г. Москвы)",
    "seller_name": "Наименование продавца / исполнителя услуги",
    "seller_address": "Адрес продавца / исполнителя услуги",
    "employer_name": "Наименование работодателя",
    "employer_address": "Адрес работодателя",
    "counterparty_name": "ФИО / наименование второй стороны договора",
    "counterparty_address": "Адрес второй стороны договора",
    "contract_subject": "Предмет договора, который расторгается",
    "description": "Опишите подробно суть ситуации/нарушения",
    "price": "Сумма ущерба или стоимость товара в рублях (если не применимо — напишите «нет»)",
    "demand": "Что вы требуете? (например: вернуть деньги, устранить нарушение, выплатить компенсацию)",
}

# Поля, которые заполняются автоматически и не требуют вопроса пользователю.
_AUTO_FIELDS = {"date"}
# Поля, которые по умолчанию подтягиваются из профиля пользователя (/settings),
# если они там уже заполнены.
_PROFILE_FIELDS = {"full_name", "address", "phone"}


def _load_document_types() -> list[dict]:
    with open(config.DOCUMENT_TYPES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _find_doc_type(doc_type_id: str) -> dict | None:
    for dt in _load_document_types():
        if dt["id"] == doc_type_id:
            return dt
    return None


async def start_document_flow(message: Message, state: FSMContext) -> None:
    doc_types = _load_document_types()
    await state.set_state(DocumentStates.choosing_type)
    await message.answer(
        "Выберите тип документа, который нужно составить:",
        reply_markup=kb.document_types_keyboard(doc_types),
    )


@router.message(F.text.in_({kb.BTN_DOCUMENT, "/document"}))
async def document_entry(message: Message, state: FSMContext) -> None:
    if not await db.is_disclaimer_accepted(message.from_user.id):
        from handlers.start import _prompt_disclaimer
        await _prompt_disclaimer(message)
        return
    await start_document_flow(message, state)


@router.callback_query(DocumentStates.choosing_type, F.data.startswith("doctype:"))
async def choose_document_type(callback: CallbackQuery, state: FSMContext) -> None:
    doc_type_id = callback.data.split(":", 1)[1]
    doc_type = _find_doc_type(doc_type_id)
    if not doc_type:
        await callback.answer("Неизвестный тип документа.", show_alert=True)
        return

    user_id = callback.from_user.id
    profile = await db.get_user(user_id) or {}

    collected: dict[str, str] = {"date": datetime.date.today().strftime("%d.%m.%Y")}
    pending_fields = []
    for field in doc_type["required_fields"]:
        if field in _AUTO_FIELDS:
            continue
        if field in _PROFILE_FIELDS and profile.get(field):
            collected[field] = profile[field]
            continue
        pending_fields.append(field)

    await state.update_data(
        doc_type_id=doc_type_id,
        doc_type_title=doc_type["title"],
        template_file=doc_type["template_file"],
        collected=collected,
        pending_fields=pending_fields,
    )

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer()

    if pending_fields:
        await state.set_state(DocumentStates.collecting_data)
        await callback.message.answer(
            f"Выбрано: {doc_type['title']}\n\n{FIELD_LABELS.get(pending_fields[0], pending_fields[0])}:"
        )
    else:
        await _show_confirmation(callback.message, state)


@router.message(DocumentStates.collecting_data)
async def collect_field(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    pending_fields: list[str] = data.get("pending_fields", [])
    collected: dict = data.get("collected", {})

    if not pending_fields:
        await _show_confirmation(message, state)
        return

    current_field = pending_fields.pop(0)
    collected[current_field] = clean_text(message.text or "")

    await state.update_data(collected=collected, pending_fields=pending_fields)

    if pending_fields:
        next_field = pending_fields[0]
        await message.answer(f"{FIELD_LABELS.get(next_field, next_field)}:")
    else:
        await _show_confirmation(message, state)


async def _show_confirmation(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    collected: dict = data.get("collected", {})
    summary = "\n".join(f"• {FIELD_LABELS.get(k, k)}: {v}" for k, v in collected.items())
    await state.set_state(DocumentStates.ready_to_generate)
    await message.answer(
        f"Проверьте данные перед составлением документа «{data.get('doc_type_title')}»:\n\n"
        f"{summary}\n\nВсё верно?",
        reply_markup=kb.confirm_cancel_keyboard(),
    )


@router.callback_query(DocumentStates.ready_to_generate, F.data == "cancel_doc")
async def cancel_document(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Составление документа отменено.", reply_markup=kb.main_menu_keyboard())
    await callback.answer()


@router.callback_query(DocumentStates.ready_to_generate, F.data == "confirm_doc")
async def confirm_document(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    user_id = callback.from_user.id
    collected: dict = data.get("collected", {})
    template_file: str = data["template_file"]
    doc_type_title: str = data["doc_type_title"]
    doc_type_id: str = data["doc_type_id"]

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer()
    status_msg = await callback.message.answer("📝 Составляю документ...")

    template_path = os.path.join(config.TEMPLATES_DIR, template_file)
    if not os.path.exists(template_path):
        await status_msg.edit_text("⚠️ Шаблон документа не найден на сервере. Сообщите администратору.")
        await state.clear()
        return

    with open(template_path, "r", encoding="utf-8") as f:
        template_text = f.read()

    relevant_laws = await find_relevant_laws(collected.get("description", ""))

    try:
        document_text = await gemini_service.fill_document_template(
            template_text, collected, doc_type_title, user_id, relevant_laws
        )
    except GeminiRateLimitError as exc:
        await status_msg.edit_text(str(exc))
        return
    except RuntimeError as exc:
        await status_msg.edit_text(str(exc))
        return

    await status_msg.delete()

    doc_log_id = await db.log_document(user_id, doc_type_id, document_text)

    for chunk in split_long_message(document_text):
        await callback.message.answer(chunk)

    await callback.message.answer(
        "Документ готов. Можно также скачать его в формате PDF:",
        reply_markup=kb.pdf_offer_keyboard(str(doc_log_id)),
    )
    await state.clear()


@router.callback_query(F.data.startswith("makepdf:"))
async def send_pdf(callback: CallbackQuery) -> None:
    doc_log_id = int(callback.data.split(":", 1)[1])
    user_id = callback.from_user.id

    record = await db.get_document(doc_log_id, user_id)
    if not record:
        await callback.answer("Документ не найден.", show_alert=True)
        return

    await callback.answer("Готовлю PDF...")
    filepath = pdf_service.generate_pdf(record["doc_type"], record["content"], user_id)
    if not filepath:
        await callback.message.answer(
            "⚠️ Не удалось сгенерировать PDF (возможно, на сервере отсутствует "
            "файл шрифта fonts/DejaVuSans.ttf). Текст документа отправлен выше."
        )
        return

    try:
        await callback.message.answer_document(FSInputFile(filepath, filename=os.path.basename(filepath)))
    finally:
        pdf_service.cleanup_pdf(filepath)
