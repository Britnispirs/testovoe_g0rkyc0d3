import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand

from bots.telegram.config import TELEGRAM_BOT_TOKEN
from bots.telegram.handlers import router


async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if not TELEGRAM_BOT_TOKEN:
        logging.error("TELEGRAM_BOT_TOKEN is not configured in environment variables.")
        sys.exit(1)

    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)

    try:
        await bot.set_my_commands([
            BotCommand(command="start", description="Главное меню и приветствие"),
            BotCommand(command="help", description="Справка и примеры команд"),
            BotCommand(command="cancel", description="Сбросить текущий диалог"),
        ])
    except Exception as e:
        logging.warning(f"Could not register commands: {e}")

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
