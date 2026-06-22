"""
Тест бота — запусти: python test_post.py
"""
import asyncio
from aiogram import Bot
from config import config
from parser import fetch_forex_news, get_market_data
from ai_generator import generate_post


async def test():
    bot = Bot(token=config.BOT_TOKEN)

    print("🔍 Парсим новости...")
    news = await fetch_forex_news(hours_back=24)
    print(f"✅ Найдено {len(news)} новостей")
    for n in news[:2]:
        print(f"  - {n['title']}")

    print("\n📊 Получаем котировки...")
    market = await get_market_data()
    print(f"✅ Котировки: {market}")

    print("\n🤖 Генерируем утренний пост...")
    post = await generate_post("morning", news=news, market_data=market)
    print("─" * 40)
    print(post)
    print("─" * 40)

    confirm = input("\nОтправить тестовый пост в канал? (y/n): ")
    if confirm.lower() == "y":
        # Отправляем фото + текст
        photo_path = "wolf_banner.jpg"
        import os
        if os.path.exists(photo_path):
            from aiogram.types import FSInputFile
            photo = FSInputFile(photo_path)
            await bot.send_photo(
                chat_id=config.CHANNEL_ID,
                photo=photo,
                caption=post,
                parse_mode="Markdown"
            )
        else:
            await bot.send_message(
                chat_id=config.CHANNEL_ID,
                text=post,
                parse_mode="Markdown",
                disable_web_page_preview=True
            )
        print("✅ Пост отправлен!")

    await bot.session.close()


asyncio.run(test())
