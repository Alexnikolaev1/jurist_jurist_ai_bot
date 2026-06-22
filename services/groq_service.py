# -*- coding: utf-8 -*-
"""
groq_service.py — транскрибация голосовых сообщений через Groq Whisper
Large v3 (бесплатный API Groq, OpenAI-совместимый эндпоинт).
"""
import logging

import aiohttp

import config

logger = logging.getLogger(__name__)


async def transcribe_voice(audio_bytes: bytes, filename: str = "voice.ogg") -> str | None:
    """
    Отправляет аудио в Groq Whisper и возвращает распознанный текст.
    Возвращает None при ошибке (вызывающий код должен сообщить пользователю
    дружелюбное сообщение об ошибке).
    """
    headers = {"Authorization": f"Bearer {config.GROQ_API_KEY}"}

    form = aiohttp.FormData()
    form.add_field("file", audio_bytes, filename=filename, content_type="audio/ogg")
    form.add_field("model", config.GROQ_WHISPER_MODEL)
    form.add_field("language", "ru")
    form.add_field("response_format", "json")

    try:
        timeout = aiohttp.ClientTimeout(total=60)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(config.GROQ_TRANSCRIPTION_URL, headers=headers, data=form) as resp:
                data = await resp.json()
                if resp.status != 200:
                    logger.error("Ошибка Groq Whisper (%s): %s", resp.status, data)
                    return None
                return data.get("text", "").strip() or None
    except (aiohttp.ClientError, ValueError) as exc:
        logger.exception("Сбой при обращении к Groq Whisper: %s", exc)
        return None
