import httpx
import logging
from datetime import datetime
from config import config

logger = logging.getLogger(__name__)
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"

SYSTEM_PROMPT = """Ты пишешь посты для Telegram канала White Wolf — анонимный форекс-трейдер.

СТРОГИЙ ФОРМАТ КАЖДОГО ПОСТА:

🔹 Заголовок (жирный, 1 строка)
🔹 Пустая строка
🔹 Блок РЫНОК — котировки списком
🔹 Пустая строка  
🔹 Блок ГЛАВНОЕ — 2-3 пункта стрелками, что важно сейчас
🔹 Пустая строка
🔹 Блок СМОТРИМ — конкретные уровни для каждого инструмента
🔹 Пустая строка
🔹 Комментарий волка — курсив, 1 предложение
🔹 Хэштеги

ПРАВИЛА:
— Русский язык
— Каждый блок чётко отделён пустой строкой
— Цифры конкретные — без "около" и "примерно"
— Коротко и ясно — без воды
— В конце: 🐺"""


async def generate_post(post_type: str, news: list = None, market_data: dict = None) -> str:
    prompts = {
        "morning":        _morning(news, market_data),
        "midday":         _midday(news, market_data),
        "evening":        _evening(news, market_data),
        "motivation":     _motivation(),
        "breaking":       _breaking(news),
        "market_weather": _weather(market_data),
    }
    user_prompt = prompts.get(post_type, _breaking(news))

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                ANTHROPIC_URL,
                headers={
                    "x-api-key": config.ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-sonnet-4-6",
                    "max_tokens": 600,
                    "system": SYSTEM_PROMPT,
                    "messages": [{"role": "user", "content": user_prompt}]
                }
            )
            data = response.json()
            text = data["content"][0]["text"]
            logger.info(f"✅ Пост готов: {post_type}")
            return text
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        return _fallback(post_type)


def _morning(news, market):
    news_block = _fmt_news(news)
    market_block = _fmt_market(market)
    today = datetime.now().strftime("%d.%m.%Y, %A")
    return f"""Напиши УТРЕННИЙ ОБЗОР на {today}.

Котировки прямо сейчас:
{market_block}

Свежие новости:
{news_block}

Используй СТРОГО этот формат:

**🌅 УТРЕННИЙ ОБЗОР | [дата]**

📊 *РЫНОК:*
• XAUUSD: [цена] — [↑/↓/→] [1 слово]
• EURUSD: [цена] — [↑/↓/→] [1 слово]
• GBPUSD: [цена] — [↑/↓/→] [1 слово]
• USDJPY: [цена] — [↑/↓/→] [1 слово]
• DXY: [значение] — [↑/↓/→] [1 слово]

📌 *ГЛАВНОЕ СЕГОДНЯ:*
→ [факт 1]
→ [факт 2]
→ [факт 3]

🎯 *СМОТРИМ:*
• GOLD: поддержка [уровень] / сопротивление [уровень]
• EURUSD: поддержка [уровень] / сопротивление [уровень]
• GBPUSD: поддержка [уровень] / сопротивление [уровень]

_[Комментарий Белого Волка — 1 предложение, уверенно]_

#whitewolf #forex #gold #аналитика"""


def _midday(news, market):
    news_block = _fmt_news(news)
    market_block = _fmt_market(market)
    return f"""Напиши ДНЕВНОЙ РАЗБОР новости.

Котировки: {market_block}
Новости: {news_block}

Формат СТРОГО:

**📊 [ЗАГОЛОВОК НОВОСТИ ЗАГЛАВНЫМИ]**

📌 *ЧТО СЛУЧИЛОСЬ:*
→ [факт 1]
→ [факт 2]

💥 *ВЛИЯНИЕ НА РЫНОК:*
→ [как влияет на GOLD]
→ [как влияет на доллар/EUR]

🎯 *УРОВНИ:*
• XAUUSD: [уровень поддержки] / [уровень сопротивления]
• EURUSD: [уровень поддержки] / [уровень сопротивления]

_[Вывод Волка — коротко]_

#whitewolf #forex #аналитика"""


def _evening(news, market):
    news_block = _fmt_news(news)
    today = datetime.now().strftime("%d.%m.%Y")
    return f"""Напиши ИТОГИ ДНЯ на {today}.

Новости: {news_block}

Формат СТРОГО:

**📉 ИТОГИ ДНЯ | {today}**

📊 *КАК ЗАКРЫЛИСЬ:*
• XAUUSD: [цена] [↑/↓]
• EURUSD: [цена] [↑/↓]
• GBPUSD: [цена] [↑/↓]

📌 *ТОП СОБЫТИЯ ДНЯ:*
→ [событие 1]
→ [событие 2]
→ [событие 3]

👁 *ЗАВТРА:*
→ [на что смотреть — загадочно, без конкретики]

_[Комментарий Волка — VIP уже знают]_

#whitewolf #forex #итоги"""


def _weather(market):
    market_block = _fmt_market(market)
    return f"""Напиши ПОГОДА РЫНКА.

Котировки: {market_block}

Формат СТРОГО:

**🌤 ПОГОДА РЫНКА**

☀️/🌧/⛈/🌪 XAUUSD [цена] — [настроение рынка 3-4 слова]
☀️/🌧/⛈/🌪 EURUSD [цена] — [настроение 3-4 слова]
☀️/🌧/⛈/🌪 GBPUSD [цена] — [настроение 3-4 слова]
☀️/🌧/⛈/🌪 DXY [значение] — [настроение 3-4 слова]

_[Вывод Волка]_

#whitewolf #forex"""


def _breaking(news):
    if not news:
        return "Напиши: рынок тихий, волк наблюдает. Строго по формату. 50 слов."
    item = news[0]
    return f"""Напиши СРОЧНЫЙ РАЗБОР новости:

Заголовок: {item['title']}
Детали: {item['summary'][:300]}

Формат СТРОГО:

**⚡ [СУТЬ НОВОСТИ ЗАГЛАВНЫМИ]**

📌 *ЧТО СЛУЧИЛОСЬ:*
→ [факт]
→ [факт]

💥 *РЕАКЦИЯ РЫНКА:*
→ [GOLD: влияние]
→ [USD: влияние]

🎯 *УРОВНИ НА СЕЙЧАС:*
• XAUUSD: [поддержка] / [сопротивление]

_[Вывод Волка]_

#whitewolf #forex #breaking"""


def _motivation():
    return """Напиши философский пост про волка и трейдинг.

Формат:

**🐺 [АФОРИЗМ ЗАГЛАВНЫМИ]**

[абзац 1 — метафора волка и рынка]

[абзац 2 — вывод для трейдера]

_[Финальная строка как афоризм]_

#whitewolf #психология"""


def _fmt_news(news):
    if not news:
        return "нет свежих новостей"
    return "\n".join([f"• {n['title']}: {n['summary'][:150]}" for n in news[:3]])


def _fmt_market(market):
    if not market:
        return "данные недоступны"
    return " | ".join([f"{k}: {v}" for k, v in market.items()])


def _fallback(post_type):
    fb = {
        "morning":  "**🌅 УТРЕННИЙ ОБЗОР**\n\n📊 *РЫНОК:*\n• Данные загружаются...\n\n_🐺 Волк наблюдает._\n\n#whitewolf #forex",
        "evening":  "**📉 ИТОГИ ДНЯ**\n\n📌 *СОБЫТИЯ:*\n• День закрыт\n\n_🐺 Завтра интереснее._\n\n#whitewolf",
        "breaking": "**⚡ СОБЫТИЕ НА РЫНКЕ**\n\n📌 Следим за развитием.\n\n_🐺 Волк в позиции._\n\n#whitewolf #forex",
        "motivation":"**🐺 ВОЛК НЕ ТОРОПИТСЯ**\n\nОн ждёт. Изучает. Бьёт точно.\n\n_Терпение — это тоже стратегия._\n\n#whitewolf",
        "market_weather": "**🌤 ПОГОДА РЫНКА**\n\n⛈ GOLD — волатильно\n☁️ EURUSD — боковик\n\n_🐺 Ждём._\n\n#whitewolf",
    }
    return fb.get(post_type, "🐺 White Wolf наблюдает.")
