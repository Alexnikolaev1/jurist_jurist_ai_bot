# -*- coding: utf-8 -*-
"""
pdf_service.py — генерация PDF-документов через ReportLab с поддержкой
кириллицы (шрифт DejaVu Sans).
"""
import logging
import os
import time

import aiohttp
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import ParagraphStyle

import config

logger = logging.getLogger(__name__)

_FONT_NAME = "DejaVuSans"
_font_registered = False


async def ensure_font() -> bool:
    """Скачивает шрифт DejaVu Sans при первом запуске, если его нет локально."""
    os.makedirs(config.FONTS_DIR, exist_ok=True)
    if os.path.exists(config.FONT_PATH):
        return True
    logger.info("Шрифт не найден, скачиваю DejaVuSans.ttf...")
    try:
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(config.DEJAVU_FONT_URL) as resp:
                if resp.status != 200:
                    logger.error("Не удалось скачать шрифт: HTTP %s", resp.status)
                    return False
                content = await resp.read()
        with open(config.FONT_PATH, "wb") as f:
            f.write(content)
        logger.info("Шрифт DejaVuSans.ttf успешно загружен.")
        return True
    except aiohttp.ClientError as exc:
        logger.error("Ошибка загрузки шрифта: %s", exc)
        return False


def _ensure_font_registered() -> bool:
    """Регистрирует шрифт DejaVu Sans один раз. Возвращает True при успехе."""
    global _font_registered
    if _font_registered:
        return True
    if not os.path.exists(config.FONT_PATH):
        logger.error(
            "Не найден файл шрифта %s. Скачайте DejaVuSans.ttf и положите в "
            "папку fonts/ — без него кириллица в PDF не отобразится.",
            config.FONT_PATH,
        )
        return False
    pdfmetrics.registerFont(TTFont(_FONT_NAME, config.FONT_PATH))
    _font_registered = True
    return True


def generate_pdf(doc_type: str, content: str, user_id: int) -> str | None:
    """
    Генерирует PDF-файл из текста документа.
    Возвращает путь к созданному файлу, либо None при ошибке (например,
    отсутствует шрифт).
    """
    if not _ensure_font_registered():
        return None

    os.makedirs(config.TMP_DIR, exist_ok=True)
    timestamp = int(time.time())
    safe_doc_type = "".join(c for c in doc_type if c.isalnum() or c in "_-") or "document"
    filename = f"{safe_doc_type}_{user_id}_{timestamp}.pdf"
    filepath = os.path.join(config.TMP_DIR, filename)

    doc = SimpleDocTemplate(
        filepath,
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )

    style = ParagraphStyle(
        name="Normal_RU",
        fontName=_FONT_NAME,
        fontSize=11,
        leading=15,
        spaceAfter=10,
    )

    story = []
    for paragraph_text in content.split("\n"):
        if paragraph_text.strip():
            # Экранируем спецсимволы XML, которые platypus интерпретирует как разметку.
            safe_text = (
                paragraph_text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )
            story.append(Paragraph(safe_text, style))
        else:
            story.append(Spacer(1, 8))

    try:
        doc.build(story)
    except Exception as exc:  # noqa: BLE001 — генерация PDF может падать по разным причинам ReportLab
        logger.exception("Ошибка генерации PDF: %s", exc)
        return None

    return filepath


def cleanup_pdf(filepath: str) -> None:
    """Удаляет временный PDF-файл после отправки пользователю."""
    try:
        if filepath and os.path.exists(filepath):
            os.remove(filepath)
    except OSError as exc:
        logger.warning("Не удалось удалить временный файл %s: %s", filepath, exc)
