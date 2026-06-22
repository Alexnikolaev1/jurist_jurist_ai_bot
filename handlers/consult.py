# -*- coding: utf-8 -*-
"""
handlers/consult.py — основной сценарий юридической консультации:
приём текста или голоса, поиск статей закона (FTS5), запрос к Gemini,
озвучка длинных ответов, логирование истории.
"""
import logging

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton

import config
import database as db
import keyboards as kb
from handlers.document import start_document_flow
from handlers.emergency import send_emergency_protocol
from handlers.start import _prompt_disclaimer
from services import gemini_service, groq_service, tts_service
from services.gemini_service import GeminiRateLimitError
from services.law_search import find_relevant_laws
from utils.filters import DisclaimerAcceptedFilter, NotMenuButtonFilter, NoActiveFsmFilter
from utils.text_utils import clean_text, detect_emergency_keywords, split_long_message

logger = logging.getLogger(__name__)
router = Router(name="consult")


def _post_consult_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⚖️ Оценить шансы в суде", callback_data="court_chances")],
            [InlineKeyboardButton(text="📄 Составить документ", callback_data="goto_document")],
        ]
    )


@router.message(F.text == kb.BTN_CONSULT)
async def consult_prompt(message: Message) -> None:
    if not await db.is_disclaimer_accepted(message.from_user.id):
        await _prompt_disclaimer(message)
        return
    await message.answer(
        "Опишите вашу ситуацию текстом или голосовым сообщением — максимально "
        "подробно: что произошло, какие документы есть на руках, что вы уже "
        "пытались сделать."
    )


async def _process_consultation(message: Message, user_text: str) -> None:
    user_id = message.from_user.id
    user_text = clean_text(user_text)

    if not user_text:
        await message.answer("Не удалось распознать текст ситуации. Попробуйте ещё раз.")
        return

    if detect_emergency_keywords(user_text):
        await send_emergency_protocol(message)
        return

    status_msg = await message.answer("🔎 Ищу подходящие статьи закона и готовлю ответ...")

    try:
        law_articles = await find_relevant_laws(user_text)
        answer = await gemini_service.generate_consultation(user_text, law_articles, user_id)
    except GeminiRateLimitError as exc:
        await status_msg.edit_text(str(exc))
        return
    except RuntimeError as exc:
        logger.exception("Ошибка консультации: %s", exc)
        await status_msg.edit_text(str(exc) or "⚠️ Произошла ошибка. Попробуйте позже.")
        return

    await status_msg.delete()

    await db.log_consultation(user_id, user_text, answer)
    await db.save_last_consultation(user_id, user_text, answer)

    for chunk in split_long_message(answer):
        await message.answer(chunk)

    await message.answer("Что дальше?", reply_markup=_post_consult_keyboard())

    if len(answer) > config.TTS_MIN_LENGTH_FOR_VOICE:
        audio_path = await tts_service.synthesize_speech(answer)
        if audio_path:
            try:
                await message.answer_voice(FSInputFile(audio_path))
            finally:
                tts_service.cleanup_audio(audio_path)


@router.message(
    F.voice,
    DisclaimerAcceptedFilter(),
    NoActiveFsmFilter(),
)
async def handle_voice_consultation(message: Message) -> None:
    status_msg = await message.answer("🎙️ Распознаю голосовое сообщение...")
    try:
        file = await message.bot.get_file(message.voice.file_id)
        file_bytes_io = await message.bot.download_file(file.file_path)
        audio_bytes = file_bytes_io.read()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Не удалось скачать голосовое сообщение: %s", exc)
        await status_msg.edit_text("⚠️ Не удалось обработать голосовое сообщение. Попробуйте текстом.")
        return

    text = await groq_service.transcribe_voice(audio_bytes)
    await status_msg.delete()

    if not text:
        await message.answer(
            "⚠️ Не удалось распознать голосовое сообщение. Попробуйте записать "
            "ещё раз или напишите текстом."
        )
        return

    await message.answer(f"📝 Распознано: <i>{text}</i>")
    await _process_consultation(message, text)


@router.callback_query(F.data == "court_chances")
async def court_chances_callback(callback: CallbackQuery) -> None:
    user_id = callback.from_user.id
    data = await db.get_last_consultation(user_id)
    if not data:
        await callback.answer("Сначала опишите ситуацию для консультации.", show_alert=True)
        return

    await callback.answer("Оцениваю...")
    try:
        assessment = await gemini_service.assess_court_chances(
            data["query"], data["answer"], user_id
        )
    except GeminiRateLimitError as exc:
        await callback.message.answer(str(exc))
        return
    except RuntimeError as exc:
        await callback.message.answer(str(exc))
        return

    await callback.message.answer(f"⚖️ <b>Оценка судебной перспективы</b>\n\n{assessment}")


@router.callback_query(F.data == "goto_document")
async def goto_document_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await start_document_flow(callback.message, state)


@router.message(
    F.text & ~F.text.startswith("/"),
    NotMenuButtonFilter(),
    DisclaimerAcceptedFilter(),
    NoActiveFsmFilter(),
)
async def handle_text_consultation(message: Message) -> None:
    await _process_consultation(message, message.text)
