# -*- coding: utf-8 -*-
"""
tts_service.py — озвучка длинных текстовых ответов через Microsoft Edge TTS
(библиотека edge-tts, полностью бесплатная, не требует API-ключа).
"""
import logging
import os
import re
import time

import edge_tts

import config

logger = logging.getLogger(__name__)


def _strip_for_speech(text: str) -> str:
    """Убирает HTML-теги и markdown-символы перед озвучкой."""
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"[*_`#]", "", text)
    return text.strip()


async def synthesize_speech(text: str, voice: str = config.TTS_DEFAULT_VOICE) -> str | None:
    """
    Генерирует .mp3 файл с озвучкой текста. Возвращает путь к файлу или
    None при ошибке. Файл нужно удалить после отправки (см. cleanup_audio).
    """
    clean = _strip_for_speech(text)
    if not clean:
        return None

    os.makedirs(config.TMP_DIR, exist_ok=True)
    filepath = os.path.join(config.TMP_DIR, f"tts_{int(time.time() * 1000)}.mp3")

    try:
        communicate = edge_tts.Communicate(clean, voice)
        await communicate.save(filepath)
        return filepath
    except Exception as exc:  # noqa: BLE001 — edge-tts может бросать разные исключения сети
        logger.exception("Ошибка синтеза речи edge-tts: %s", exc)
        return None


def cleanup_audio(filepath: str) -> None:
    """Удаляет временный аудиофайл после отправки пользователю."""
    try:
        if filepath and os.path.exists(filepath):
            os.remove(filepath)
    except OSError as exc:
        logger.warning("Не удалось удалить временный аудиофайл %s: %s", filepath, exc)
