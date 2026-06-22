# -*- coding: utf-8 -*-
"""
bot.py — точка входа JURIST AI. Регистрирует все хендлеры, middleware,
инициализирует базу данных и запускает бота в режиме вебхука (если задан
WEBHOOK_URL / Railway-домен) либо поллинга (для локальной разработки).
"""
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

import config
import database as db
from handlers import start, settings as settings_handler, document, contract, emergency, history, consult
from middlewares import ErrorMiddleware, UserContextMiddleware
from services import pdf_service
from storage import SQLiteStorage

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


def create_dispatcher() -> Dispatcher:
    dp = Dispatcher(storage=SQLiteStorage())

    dp.update.middleware(ErrorMiddleware())
    dp.update.middleware(UserContextMiddleware())

    # ВАЖНО: порядок регистрации роутеров имеет значение. Роутеры с
    # узкоспециализированными хендлерами регистрируются раньше, а consult.py
    # с универсальным catch-all обработчиком текста — последним.
    dp.include_router(start.router)
    dp.include_router(settings_handler.router)
    dp.include_router(document.router)
    dp.include_router(contract.router)
    dp.include_router(emergency.router)
    dp.include_router(history.router)
    dp.include_router(consult.router)

    return dp


async def on_startup(bot: Bot) -> None:
    logger.info("Инициализация базы данных...")
    await db.init_db()

    for warning in config.validate_api_keys():
        logger.warning(warning)

    await pdf_service.ensure_font()

    if config.USE_WEBHOOK:
        logger.info("Устанавливаю webhook: %s", config.WEBHOOK_HOST + config.WEBHOOK_PATH)
        await bot.set_webhook(
            url=config.WEBHOOK_URL,
            drop_pending_updates=True,
        )
    else:
        logger.info("Webhook не настроен — бот будет работать в режиме polling.")

    logger.info("JURIST AI запущен.")


async def on_shutdown(bot: Bot) -> None:
    logger.info("Останавливаю бота...")
    if config.USE_WEBHOOK:
        await bot.delete_webhook()
    await bot.session.close()


def run_polling() -> None:
    bot = Bot(
        token=config.TELEGRAM_BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = create_dispatcher()
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    asyncio.run(dp.start_polling(bot))


def run_webhook() -> None:
    bot = Bot(
        token=config.TELEGRAM_BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = create_dispatcher()
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    app = web.Application()
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=config.WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)

    async def health_check(_request: web.Request) -> web.Response:
        return web.Response(text="JURIST AI is running")

    app.router.add_get("/", health_check)

    web.run_app(app, host="0.0.0.0", port=config.PORT)


if __name__ == "__main__":
    if config.USE_WEBHOOK:
        run_webhook()
    else:
        run_polling()
