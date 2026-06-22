import logging
import os
from aiogram import Bot
from aiogram.types import FSInputFile
from aiogram.exceptions import TelegramAPIError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from config import config
from parser import fetch_forex_news, get_market_data
from ai_generator import generate_post
from calendar_parser import fetch_forex_factory_calendar, format_calendar_post

logger = logging.getLogger(__name__)
BANNER_PATH = "wolf_banner.jpg"


async def post_to_channel(bot: Bot, text: str):
    try:
        if os.path.exists(BANNER_PATH):
            photo = FSInputFile(BANNER_PATH)
            await bot.send_photo(
                chat_id=config.CHANNEL_ID,
                photo=photo,
                caption=text,
                parse_mode="Markdown"
            )
        else:
            await bot.send_message(
                chat_id=config.CHANNEL_ID,
                text=text,
                parse_mode="Markdown",
                disable_web_page_preview=True
            )
        logger.info("✅ Пост опубликован")
    except TelegramAPIError as e:
        logger.error(f"❌ Ошибка: {e}")
        try:
            await bot.send_message(config.ADMIN_ID, f"⚠️ Ошибка:\n{e}")
        except Exception:
            pass


async def calendar_post(bot: Bot):
    """07:30 — Экономический календарь на день"""
    logger.info("📅 Календарь событий...")
    events = await fetch_forex_factory_calendar(days_ahead=0)
    text = await format_calendar_post(events)
    await post_to_channel(bot, text)


async def morning_post(bot: Bot):
    """08:00 — Утренний обзор"""
    logger.info("📅 Утренний пост...")
    news = await fetch_forex_news(hours_back=8)
    market = await get_market_data()
    text = await generate_post("morning", news=news, market_data=market)
    await post_to_channel(bot, text)


async def midday_post(bot: Bot):
    """13:00 — Дневной разбор"""
    logger.info("📅 Дневной пост...")
    news = await fetch_forex_news(hours_back=5)
    market = await get_market_data()
    from datetime import datetime
    if datetime.now().day % 2 == 0:
        text = await generate_post("breaking", news=news, market_data=market)
    else:
        text = await generate_post("market_weather", market_data=market)
    await post_to_channel(bot, text)


async def evening_post(bot: Bot):
    """20:00 — Итоги дня"""
    logger.info("📅 Вечерний пост...")
    news = await fetch_forex_news(hours_back=12)
    market = await get_market_data()
    text = await generate_post("evening", news=news, market_data=market)
    await post_to_channel(bot, text)

    from datetime import datetime
    import asyncio
    if datetime.now().weekday() == 4:
        await asyncio.sleep(1800)
        motivation = await generate_post("motivation")
        await post_to_channel(bot, motivation)


def schedule_posts(scheduler: AsyncIOScheduler, bot: Bot):
    # 07:30 — Календарь событий (Пн-Пт)
    scheduler.add_job(calendar_post, "cron", hour=7, minute=30,
                      day_of_week="mon-fri", args=[bot], id="calendar")

    # 08:00 — Утренний обзор (Пн-Пт)
    scheduler.add_job(morning_post, "cron", hour=8, minute=0,
                      day_of_week="mon-fri", args=[bot], id="morning")

    # 09:00 — Субботний обзор
    scheduler.add_job(morning_post, "cron", hour=9, minute=0,
                      day_of_week="sat", args=[bot], id="saturday")

    # 13:00 — Дневной (Пн-Пт)
    scheduler.add_job(midday_post, "cron", hour=13, minute=0,
                      day_of_week="mon-fri", args=[bot], id="midday")

    # 20:00 — Вечерний (каждый день)
    scheduler.add_job(evening_post, "cron", hour=20, minute=0,
                      args=[bot], id="evening")

    logger.info("✅ Планировщик: календарь 07:30 + 3 поста в день")
