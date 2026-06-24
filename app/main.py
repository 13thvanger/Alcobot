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

    try:
        await db.create_schema()
        await set_commands(bot)
        await dispatcher.start_polling(bot, db=db, llm=llm, settings=settings)
    finally:
        await bot.session.close()
        await llm.close()
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())

