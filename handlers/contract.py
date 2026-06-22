# -*- coding: utf-8 -*-
"""
handlers/contract.py — проверка договора по фотографии: распознавание
текста через Gemini Vision и анализ на кабальные условия и нарушения закона.
"""
import logging

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

import config
import database as db
import keyboards as kb
from handlers.start import _prompt_disclaimer
from services import gemini_service
from services.gemini_service import GeminiRateLimitError
from states import ContractStates
from utils.text_utils import split_long_message

logger = logging.getLogger(__name__)
router = Router(name="contract")

_MIN_OCR_TEXT_LENGTH = 30


@router.message(F.text == kb.BTN_CONTRACT)
async def contract_prompt(message: Message, state: FSMContext) -> None:
    if not await db.is_disclaimer_accepted(message.from_user.id):
        await _prompt_disclaimer(message)
        return
    await state.set_state(ContractStates.awaiting_photo)
    await message.answer(
        "📷 Пришлите фото страницы договора (одна страница за раз, текст должен "
        "быть хорошо читаем, без бликов и размытия).\n\n"
        "Для отмены нажмите любую кнопку меню."
    )


@router.message(ContractStates.awaiting_photo, F.photo)
async def handle_contract_photo(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id
    status_msg = await message.answer("🔍 Распознаю текст договора...")

    try:
        photo = message.photo[-1]
        file = await message.bot.get_file(photo.file_id)
        file_bytes_io = await message.bot.download_file(file.file_path)
        image_bytes = file_bytes_io.read()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Не удалось скачать фото договора: %s", exc)
        await status_msg.edit_text("⚠️ Не удалось загрузить фото. Попробуйте отправить ещё раз.")
        return

    try:
        recognized_text = await gemini_service.ocr_contract_image(
            image_bytes, "image/jpeg", user_id
        )
    except GeminiRateLimitError as exc:
        await status_msg.edit_text(str(exc))
        return
    except RuntimeError as exc:
        await status_msg.edit_text(str(exc))
        return

    if not recognized_text or len(recognized_text.strip()) < _MIN_OCR_TEXT_LENGTH:
        await status_msg.edit_text(
            "⚠️ Не удалось распознать текст договора — фото слишком низкого "
            "качества. Пожалуйста, переснимите страницу при хорошем освещении, "
            "без бликов, и пришлите снова."
        )
        return

    await status_msg.edit_text("⚖️ Анализирую договор на риски...")

    try:
        analysis = await gemini_service.analyze_contract(recognized_text, user_id)
    except GeminiRateLimitError as exc:
        await status_msg.edit_text(str(exc))
        return
    except RuntimeError as exc:
        await status_msg.edit_text(str(exc))
        return

    await status_msg.delete()
    await state.clear()

    for chunk in split_long_message(analysis):
        await message.answer(chunk)

    await db.log_consultation(user_id, "[Проверка договора по фото]", analysis)


@router.message(ContractStates.awaiting_photo, F.text.in_({
    kb.BTN_CONSULT, kb.BTN_DOCUMENT, kb.BTN_HISTORY,
    kb.BTN_SETTINGS, kb.BTN_EMERGENCY,
}))
async def cancel_contract_mode(message: Message, state: FSMContext) -> None:
    await state.clear()
