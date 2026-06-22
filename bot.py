import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from config import config
from scheduler import schedule_posts
from signals import router as signal_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("logs/bot.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


async def main():
    bot = Bot(token=config.BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    dp.include_router(signal_router)

    scheduler = AsyncIOScheduler(timezone="Asia/Tashkent")
    schedule_posts(scheduler, bot)
    scheduler.start()

    logger.info("🐺 White Wolf Bot запущен")
    logger.info(f"📢 Канал: {config.CHANNEL_ID}")
    logger.info("💬 Команды: /signal /calendar /cancel /help")

    try:
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
