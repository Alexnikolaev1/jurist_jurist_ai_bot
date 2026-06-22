# -*- coding: utf-8 -*-
"""
gemini_service.py — обёртка над Google Gemini API (бесплатный тариф
Google AI Studio, модель gemini-1.5-flash). Поддерживает:
  - текстовые запросы (консультация, анализ договора, заполнение шаблона)
  - vision-запросы (распознавание текста с фото договора)

Все запросы кэшируются в SQLite (таблица cache) по хэшу промпта на 24 часа
и проходят через rate limiter, чтобы не вылететь за пределы бесплатной квоты.
"""
import base64
import logging

import aiohttp

import config
import database as db
from utils.rate_limiter import gemini_rate_limiter
from utils.text_utils import hash_text

logger = logging.getLogger(__name__)

FRIENDLY_ERROR = (
    "⚠️ Не удалось получить ответ от юридического AI-модуля. "
    "Попробуйте, пожалуйста, ещё раз через минуту."
)
RATE_LIMIT_ERROR_TEMPLATE = (
    "⏳ Слишком много запросов. Подождите примерно {seconds} сек. и попробуйте снова."
)


class GeminiRateLimitError(Exception):
    """Превышен лимит запросов к Gemini (персональный или общий)."""

    def __init__(self, wait_seconds: int):
        self.wait_seconds = wait_seconds
        super().__init__(RATE_LIMIT_ERROR_TEMPLATE.format(seconds=wait_seconds))


async def _call_gemini_raw(parts: list[dict], user_id: int, use_cache: bool = True) -> str:
    """
    Низкоуровневый вызов Gemini generateContent.
    parts — список content-частей запроса (текст и/или inline_data с картинкой).
    """
    cache_key = None
    if use_cache:
        cache_key = "gemini:" + hash_text(str(parts))
        cached = await db.cache_get(cache_key)
        if cached is not None:
            logger.info("Ответ Gemini взят из кэша (user_id=%s)", user_id)
            return cached

    allowed = await gemini_rate_limiter.allow(user_id)
    if not allowed:
        wait = await gemini_rate_limiter.seconds_until_available(user_id)
        raise GeminiRateLimitError(wait)

    url = f"{config.GEMINI_API_URL}?key={config.GEMINI_API_KEY}"
    payload = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": 2048,
        },
    }

    try:
        timeout = aiohttp.ClientTimeout(total=60)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload) as resp:
                data = await resp.json()
                if resp.status != 200:
                    logger.error("Ошибка Gemini API (%s): %s", resp.status, data)
                    raise RuntimeError(f"Gemini API вернул статус {resp.status}")

                candidates = data.get("candidates", [])
                if not candidates:
                    # Скорее всего сработал safety-фильтр Gemini
                    logger.warning("Gemini не вернул кандидатов: %s", data)
                    return (
                        "Не удалось обработать запрос автоматически — возможно, "
                        "ситуация слишком специфична. Рекомендую обратиться "
                        "к практикующему юристу очно."
                    )
                text_parts = candidates[0]["content"]["parts"]
                result = "".join(p.get("text", "") for p in text_parts).strip()
    except (aiohttp.ClientError, KeyError, ValueError) as exc:
        logger.exception("Сбой при обращении к Gemini API: %s", exc)
        raise RuntimeError(FRIENDLY_ERROR) from exc

    if use_cache and cache_key:
        await db.cache_set(cache_key, result)
    return result


async def generate_consultation(user_query: str, law_articles: list[dict], user_id: int) -> str:
    """
    Основная юридическая консультация: на основе найденных статей закона
    Gemini формирует понятный ответ со ссылками на конкретные нормы.
    """
    if law_articles:
        context = "\n\n".join(
            f"{a['codex']}, статья {a['article_number']} "
            f"«{a.get('article_title') or ''}»:\n{a['article_text']}"
            for a in law_articles
        )
    else:
        context = "Релевантные статьи закона в локальной базе не найдены."

    prompt = (
        "Ты — опытный российский юрист, который консультирует обычных граждан "
        "простым и понятным языком, без лишнего канцелярита.\n\n"
        f"Ситуация пользователя:\n{user_query}\n\n"
        f"Найденные в базе статьи закона, которые могут относиться к ситуации:\n{context}\n\n"
        "Задача:\n"
        "1. Объясни ситуацию простым языком — есть ли нарушение прав пользователя.\n"
        "2. Сошлись на конкретные пункты и статьи закона из предоставленного списка "
        "(если они действительно относятся к делу). Не выдумывай номера статей, "
        "которых нет в списке.\n"
        "3. Дай пошаговый план действий пользователя.\n"
        "4. Укажи, в какие государственные органы можно обратиться "
        "(Роспотребнадзор, прокуратура, суд, трудовая инспекция, ГИБДД и т.д.), "
        "если это уместно.\n"
        "5. Если предоставленных статей недостаточно, чтобы дать точный ответ, "
        "честно скажи: «Мне нужна более подробная информация, либо это сложный "
        "случай, требующий очной консультации юриста» — и поясни, какая именно "
        "информация нужна.\n\n"
        "Отвечай структурированно, используй короткие абзацы. Не используй Markdown-таблицы."
    )
    return await _call_gemini_raw([{"text": prompt}], user_id)


async def assess_court_chances(user_query: str, gemini_consultation: str, user_id: int) -> str:
    """Примерная оценка судебной перспективы на основе обобщённой практики."""
    prompt = (
        "На основе следующей юридической ситуации и уже данной консультации "
        "оцени примерные шансы пользователя в случае обращения в суд.\n\n"
        f"Ситуация: {user_query}\n\nКонсультация: {gemini_consultation}\n\n"
        "Ответь в формате:\n"
        "Оценка: <Высокая / Средняя / Низкая>\n"
        "Обоснование: <2-3 предложения на основе типичной судебной практики по "
        "аналогичным делам>\n\n"
        "Обязательно заверши ответ фразой: «Это предварительная оценка на основе "
        "обобщённой судебной практики и не является гарантией результата. "
        "Для точного прогноза обратитесь к адвокату.»"
    )
    return await _call_gemini_raw([{"text": prompt}], user_id)


async def analyze_contract(contract_text: str, user_id: int) -> str:
    """Анализ текста договора на кабальные условия и нарушения закона."""
    word_count = len(contract_text.split())
    warning = ""
    if word_count > config.MAX_CONTRACT_TEXT_WORDS:
        warning = (
            "\n\n(Текст договора очень большой, анализ может быть поверхностным — "
            "рекомендуем также показать договор юристу очно.)"
        )

    prompt = (
        "Ты — юрист, специализирующийся на проверке договоров по законодательству РФ.\n\n"
        f"Текст договора (распознан с фото):\n{contract_text}\n\n"
        "Проанализируй договор и найди:\n"
        "- кабальные условия;\n"
        "- односторонние права одной из сторон;\n"
        "- несоответствия законодательству РФ (ГК РФ, Закон о защите прав "
        "потребителей, ТК РФ — в зависимости от типа договора);\n"
        "- скрытые комиссии и платежи;\n"
        "- невыгодные или непропорциональные штрафные санкции.\n\n"
        "По каждому найденному риску укажи: пункт договора (если можно "
        "определить), в чём проблема, и какая статья закона потенциально "
        "нарушена. Если рисков мало или их нет — так и напиши, не выдумывай "
        "проблемы. В конце дай краткую общую рекомендацию: подписывать ли "
        "договор в текущем виде или сначала требовать изменений."
    )
    result = await _call_gemini_raw([{"text": prompt}], user_id, use_cache=False)
    return result + warning


async def ocr_contract_image(image_bytes: bytes, mime_type: str, user_id: int) -> str:
    """Распознаёт текст с фотографии договора через Gemini Vision."""
    encoded = base64.b64encode(image_bytes).decode("utf-8")
    parts = [
        {
            "text": (
                "Распознай и верни ВЕСЬ текст с этого изображения страницы договора "
                "максимально точно, сохраняя нумерацию пунктов. Ничего не добавляй "
                "от себя, не анализируй — только распознанный текст."
            )
        },
        {"inline_data": {"mime_type": mime_type, "data": encoded}},
    ]
    return await _call_gemini_raw(parts, user_id, use_cache=False)


async def fill_document_template(
    template_text: str,
    data: dict,
    doc_type_title: str,
    user_id: int,
    relevant_laws: list[dict] | None = None,
) -> str:
    """Заполняет шаблон документа данными пользователя через Gemini."""
    data_str = "\n".join(f"{k}: {v}" for k, v in data.items() if v)

    laws_context = ""
    if relevant_laws:
        laws_context = "\n\nВозможно релевантные статьи закона (используй для плейсхолдера {article}, если подходят):\n" + "\n".join(
            f"- {a['codex']}, ст. {a['article_number']} «{a.get('article_title') or ''}»"
            for a in relevant_laws
        )

    prompt = (
        f"Заполни шаблон документа «{doc_type_title}» на основе данных пользователя.\n\n"
        f"Шаблон:\n{template_text}\n\n"
        f"Данные пользователя:\n{data_str}"
        f"{laws_context}\n\n"
        "Верни готовый документ с заполненными полями вместо плейсхолдеров "
        "(плейсхолдеры выглядят как {имя_поля}). Плейсхолдер {article} замени на "
        "конкретную ссылку на статью закона, если она есть в списке выше и "
        "подходит по смыслу; если подходящей статьи нет — сформулируй общую "
        "корректную правовую отсылку, не выдумывая номера статей. Если данных "
        "для какого-то поля не хватает — оставь разумную нейтральную "
        "формулировку или прочерк, не выдумывай факты. Сохрани официальный "
        "деловой стиль документа. Верни только текст готового документа, без "
        "пояснений и комментариев."
    )
    return await _call_gemini_raw([{"text": prompt}], user_id, use_cache=False)
