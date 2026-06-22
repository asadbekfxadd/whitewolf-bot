import httpx
import logging
from datetime import datetime, timedelta
from config import config

logger = logging.getLogger(__name__)

TRACKED_CURRENCIES = ["USD", "EUR", "GBP", "JPY", "CHF", "AUD", "CAD"]

FLAGS = {
    "USD": "🇺🇸", "EUR": "🇪🇺", "GBP": "🇬🇧",
    "JPY": "🇯🇵", "CHF": "🇨🇭", "AUD": "🇦🇺",
    "CAD": "🇨🇦", "NZD": "🇳🇿", "CNY": "🇨🇳",
}

IMPACT = {
    "high":   "🔴",
    "medium": "🟡",
    "low":    "⚪",
}


async def fetch_forex_factory_calendar(days_ahead: int = 0) -> list[dict]:
    events = []
    try:
        url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, headers={
                "User-Agent": "Mozilla/5.0 (compatible; WhiteWolfBot/1.0)",
                "Referer": "https://www.forexfactory.com/"
            })
            if resp.status_code == 200:
                data = resp.json()
                today = datetime.now().date()
                target_dates = [today + timedelta(days=i) for i in range(days_ahead + 1)]

                for item in data:
                    try:
                        date_str = item.get("date", "")
                        if not date_str:
                            continue
                        event_date = datetime.strptime(date_str, "%m-%d-%Y").date()
                        if event_date not in target_dates:
                            continue
                        currency = item.get("currency", "").upper()
                        if currency not in TRACKED_CURRENCIES:
                            continue
                        impact = item.get("impact", "low").lower()
                        if impact == "low":
                            continue
                        events.append({
                            "date":     event_date.strftime("%d.%m.%Y"),
                            "time":     item.get("time", "All Day"),
                            "currency": currency,
                            "flag":     FLAGS.get(currency, "🌍"),
                            "impact":   impact,
                            "emoji":    IMPACT.get(impact, "⚪"),
                            "title":    item.get("title", ""),
                            "forecast": item.get("forecast", ""),
                            "previous": item.get("previous", ""),
                            "actual":   item.get("actual", ""),
                        })
                    except Exception as e:
                        logger.warning(f"Ошибка события: {e}")

        logger.info(f"Календарь: {len(events)} событий")
    except Exception as e:
        logger.warning(f"Forex Factory: {e}")

    events.sort(key=lambda x: (0 if x["impact"] == "high" else 1, x["time"]))
    return events


async def generate_ai_forecast(events: list[dict]) -> str:
    """Claude анализирует события и даёт прогноз куда пойдёт рынок"""
    if not events:
        return ""

    # Берём только важные события для анализа
    high_events = [e for e in events if e["impact"] == "high"]
    if not high_events:
        high_events = events[:3]

    events_text = "\n".join([
        f"- {e['time']} {e['flag']} {e['currency']} | {e['title']} | "
        f"прогноз: {e['forecast'] or 'нет'} | предыдущее: {e['previous'] or 'нет'}"
        for e in high_events
    ])

    prompt = f"""Ты — опытный форекс аналитик White Wolf.

Сегодня выходят эти экономические данные:
{events_text}

Напиши короткий прогноз (3-4 предложения) для Telegram канала:
1. Что ожидать от рынка если данные выйдут ЛУЧШЕ прогноза
2. Что ожидать если ХУЖЕ прогноза
3. На какие инструменты обратить внимание (XAUUSD, EURUSD, GBPUSD)

Стиль: уверенный, конкретный, как White Wolf. Без воды. В конце 🐺"""

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": config.ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-sonnet-4-6",
                    "max_tokens": 300,
                    "messages": [{"role": "user", "content": prompt}]
                }
            )
            return resp.json()["content"][0]["text"]
    except Exception as e:
        logger.warning(f"AI прогноз: {e}")
        return ""


async def format_calendar_post(events: list[dict]) -> str:
    """Форматирует пост с календарём + AI прогноз"""
    today = datetime.now().strftime("%d.%m.%Y")

    if not events:
        return (
            f"**📅 ЭКОНОМИЧЕСКИЙ КАЛЕНДАРЬ | {today}**\n\n"
            f"Важных событий сегодня нет.\n\n"
            f"_🐺 Тихий день — хорошее время для анализа структуры._\n\n"
            f"#whitewolf #forex #календарь"
        )

    high   = [e for e in events if e["impact"] == "high"]
    medium = [e for e in events if e["impact"] == "medium"]

    post = f"**📅 ЭКОНОМИЧЕСКИЙ КАЛЕНДАРЬ | {today}**\n"
    post += "━━━━━━━━━━━━━━━\n"

    if high:
        post += "\n🔴 *ВЫСОКАЯ ВАЖНОСТЬ:*\n"
        for e in high:
            time_str = e['time'] if e['time'] != 'All Day' else 'Весь день'
            line = f"• `{time_str}` {e['flag']} — **{e['title']}**"
            if e['forecast']:
                line += f"\n  📊 Прогноз: `{e['forecast']}`"
            if e['previous']:
                line += f" | Пред: `{e['previous']}`"
            if e['actual']:
                line += f" | ✅ Факт: `{e['actual']}`"
            post += line + "\n"

    if medium:
        post += "\n🟡 *СРЕДНЯЯ ВАЖНОСТЬ:*\n"
        for e in medium:
            time_str = e['time'] if e['time'] != 'All Day' else 'Весь день'
            line = f"• `{time_str}` {e['flag']} — {e['title']}"
            if e['forecast']:
                line += f" | прогноз: `{e['forecast']}`"
            post += line + "\n"

    # AI прогноз
    ai_forecast = await generate_ai_forecast(events)
    if ai_forecast:
        post += "\n━━━━━━━━━━━━━━━\n"
        post += f"**👁 ОЖИДАНИЕ ВОЛКА:**\n{ai_forecast}\n"
    else:
        post += "\n━━━━━━━━━━━━━━━\n"
        if high:
            post += f"_🐺 Главное сегодня — {high[0]['title']} в {high[0]['time']}. Готовься к волатильности._\n"
        else:
            post += "_🐺 День средней активности. Волк наблюдает._\n"

    post += "\n#whitewolf #forex #календарь #forexfactory"
    return post
