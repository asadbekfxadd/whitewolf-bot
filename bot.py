import asyncio
import logging
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from config import config
from scheduler import schedule_posts
from signals import router as signal_router
from post_handler import router as post_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("logs/bot.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="⚡️ Сигнал"),
                KeyboardButton(text="✍️ Пост"),
            ],
            [
                KeyboardButton(text="📸 Скриншот"),
                KeyboardButton(text="📅 Календарь"),
            ],
            [
                KeyboardButton(text="📊 Авто-пост"),
                KeyboardButton(text="❓ Помощь"),
            ],
        ],
        resize_keyboard=True,
        persistent=True
    )


async def main():
    bot = Bot(token=config.BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    dp.include_router(signal_router)
    dp.include_router(post_router)

    # ── Кнопки меню ───────────────────────────────────────────────────────────

    @dp.message(F.text == "⚡️ Сигнал", F.from_user.id == config.ADMIN_ID)
    async def btn_signal(message: Message):
        await bot.send_message(message.chat.id, "/signal")

    @dp.message(F.text == "✍️ Пост", F.from_user.id == config.ADMIN_ID)
    async def btn_post(message: Message):
        await bot.send_message(message.chat.id, "/post")

    @dp.message(F.text == "📅 Календарь", F.from_user.id == config.ADMIN_ID)
    async def btn_calendar(message: Message):
        await bot.send_message(message.chat.id, "/calendar")

    @dp.message(F.text == "❓ Помощь", F.from_user.id == config.ADMIN_ID)
    async def btn_help(message: Message):
        await bot.send_message(message.chat.id, "/help")

    @dp.message(F.text == "📸 Скриншот", F.from_user.id == config.ADMIN_ID)
    async def btn_screenshot(message: Message):
        await message.answer(
            "📸 Кинь фото — выберу подпись для публикации в канале.",
            reply_markup=main_menu()
        )

    @dp.message(F.text == "📊 Авто-пост", F.from_user.id == config.ADMIN_ID)
    async def btn_autopost(message: Message):
        await message.answer(
            "🤖 *Автопосты по расписанию:*\n\n"
            "🕖 07:30 — Календарь Forex Factory + AI прогноз\n"
            "🌅 08:00 — Утренний обзор рынка\n"
            "📊 13:00 — Дневной разбор / погода рынка\n"
            "📉 20:00 — Итоги дня\n"
            "🐺 20:30 — Мотивация (только пятница)\n\n"
            "Всё публикуется автоматически без твоего участия.",
            parse_mode="Markdown",
            reply_markup=main_menu()
        )

    @dp.message(Command("start"), F.from_user.id == config.ADMIN_ID)
    async def cmd_start(message: Message):
        await message.answer(
            "🐺 *White Wolf Bot*\n\n"
            "Панель управления каналом. Выбери действие:",
            parse_mode="Markdown",
            reply_markup=main_menu()
        )

    # ── Планировщик ───────────────────────────────────────────────────────────

    scheduler = AsyncIOScheduler(timezone="Asia/Tashkent")
    schedule_posts(scheduler, bot)
    scheduler.start()

    logger.info("🐺 White Wolf Bot запущен")

    try:
        await bot.send_message(
            config.ADMIN_ID,
            "🐺 Бот запущен и готов к работе!",
            reply_markup=main_menu()
        )
    except Exception:
        pass

    try:
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())

