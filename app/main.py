"""Точка входа приложения.

Если сравнивать с C/C++, функция ``main`` здесь тоже запускает программу, но вся
основная работа асинхронна: пока бот ждёт Telegram, БД или HTTP, поток не блокируется.
"""

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.config import get_settings
from app.db import Database
from app.handlers import router, set_commands
from app.llm import AlcoholLLMClient


async def main() -> None:
    # Аннотация ``-> None`` нужна IDE и анализаторам типов. В runtime Python её
    # почти не контролирует — в отличие от сигнатуры функции в C++/Delphi.
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    db = Database(settings)
    llm = AlcoholLLMClient(settings)
    bot = Bot(
        settings.telegram_bot_token.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dispatcher = Dispatcher()
    dispatcher.include_router(router)

    # try/finally похож на try/finally в Delphi: блок finally выполнится даже при
    # исключении или остановке процесса. Здесь мы гарантированно закрываем ресурсы.
    try:
        await db.create_schema()
        await set_commands(bot)
        # await приостанавливает только эту coroutine, а не весь поток программы.
        # Dispatcher передаёт именованные зависимости db/llm/settings обработчикам.
        await dispatcher.start_polling(bot, db=db, llm=llm, settings=settings)
    finally:
        await bot.session.close()
        await llm.close()
        await db.close()


# Этот guard не выполняется, когда модуль импортируют тесты. Аналогично можно
# думать о нём как об отделении executable entry point от подключаемого unit.
if __name__ == "__main__":
    asyncio.run(main())
