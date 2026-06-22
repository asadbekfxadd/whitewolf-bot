from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from config import config
import httpx
import logging

logger = logging.getLogger(__name__)
router = Router()


class SignalForm(StatesGroup):
    waiting = State()


def parse_signal(text: str) -> dict | None:
    """
    Парсит команду: /signal XAUUSD BUY 2341 SL 2325 TP 2380
    Или:           /signal EURUSD SELL 1.0850 SL 1.0880 TP 1.0790
    """
    parts = text.strip().split()
    # Убираем /signal
    if parts[0].startswith("/"):
        parts = parts[1:]

    if len(parts) < 3:
        return None

    try:
        data = {
            "symbol":    parts[0].upper(),
            "direction": parts[1].upper(),
            "entry":     float(parts[2]),
            "sl":        None,
            "tp":        None,
            "tp2":       None,
            "comment":   None,
        }

        # Парсим SL, TP, TP2, комментарий
        i = 3
        while i < len(parts):
            tag = parts[i].upper()
            if tag == "SL" and i + 1 < len(parts):
                data["sl"] = float(parts[i + 1])
                i += 2
            elif tag == "TP" and i + 1 < len(parts):
                data["tp"] = float(parts[i + 1])
                i += 2
            elif tag == "TP2" and i + 1 < len(parts):
                data["tp2"] = float(parts[i + 1])
                i += 2
            elif tag == "#":
                data["comment"] = " ".join(parts[i + 1:])
                break
            else:
                i += 1

        return data
    except Exception:
        return None


def calc_rr(entry: float, sl: float, tp: float, direction: str) -> str:
    """Считает Risk/Reward ratio"""
    try:
        if direction == "BUY":
            risk   = abs(entry - sl)
            reward = abs(tp - entry)
        else:
            risk   = abs(sl - entry)
            reward = abs(entry - tp)
        if risk == 0:
            return "—"
        rr = round(reward / risk, 1)
        return f"1:{rr}"
    except Exception:
        return "—"


def format_signal_post(data: dict) -> str:
    """Форматирует красивый пост для канала"""
    direction = data["direction"]
    symbol    = data["symbol"]
    entry     = data["entry"]
    sl        = data["sl"]
    tp        = data["tp"]
    tp2       = data["tp2"]
    comment   = data["comment"]

    # Эмодзи направления
    if direction == "BUY":
        dir_emoji = "🟢 ПОКУПКА"
    elif direction == "SELL":
        dir_emoji = "🔴 ПРОДАЖА"
    else:
        dir_emoji = f"⚪ {direction}"

    # Форматируем цены
    def fmt(v):
        if v is None:
            return "—"
        return f"{v:,.5g}"

    # RR ratio
    rr = "—"
    if sl and tp:
        rr = calc_rr(entry, sl, tp, direction)

    # Пипсы риска
    pips_info = ""
    if sl:
        if "XAU" in symbol or "GOLD" in symbol:
            pips = round(abs(entry - sl), 2)
            pips_info = f"${pips}"
        else:
            pips = round(abs(entry - sl) * 10000)
            pips_info = f"{pips} pip"

    post = f"""⚡️ *СИГНАЛ WHITE WOLF*

🎯 *{symbol}* — {dir_emoji}

━━━━━━━━━━━━━━━
📍 Вход:  `{fmt(entry)}`"""

    if sl:
        post += f"\n🛑 Стоп:  `{fmt(sl)}`"
    if tp:
        post += f"\n✅ Цель 1: `{fmt(tp)}`"
    if tp2:
        post += f"\n✅ Цель 2: `{fmt(tp2)}`"

    post += f"\n━━━━━━━━━━━━━━━"

    if rr != "—":
        post += f"\n⚖️ Риск/Прибыль: *{rr}*"
    if pips_info:
        post += f"\n📏 Риск: *{pips_info}*"

    post += f"\n⚠️ Риск на сделку: *не более 1-2% депозита*"

    if comment:
        post += f"\n\n💬 _{comment}_"

    post += f"\n\n🐺 _White Wolf_\n#whitewolf #signal #{symbol.lower()}"

    return post


async def generate_ai_comment(data: dict) -> str:
    """Генерирует AI комментарий к сигналу через Claude"""
    try:
        symbol    = data["symbol"]
        direction = data["direction"]
        entry     = data["entry"]
        sl        = data.get("sl", "—")
        tp        = data.get("tp", "—")

        prompt = f"""Напиши КОРОТКИЙ комментарий (2-3 предложения) к форекс сигналу в стиле White Wolf.
Сигнал: {symbol} {direction} от {entry}, стоп {sl}, цель {tp}
Объясни кратко почему этот уровень интересен. Уверенно, без воды. Заканчивай на 🐺"""

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": config.ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-sonnet-4-6",
                    "max_tokens": 150,
                    "messages": [{"role": "user", "content": prompt}]
                }
            )
            return resp.json()["content"][0]["text"]
    except Exception as e:
        logger.warning(f"AI комментарий: {e}")
        return ""


@router.message(Command("signal"))
async def cmd_signal(message: Message):
    """Обрабатывает команду /signal от админа"""

    # Только админ может отправлять сигналы
    if message.from_user.id != config.ADMIN_ID:
        await message.answer("⛔ Только для администратора.")
        return

    text = message.text or ""
    data = parse_signal(text)

    if not data:
        await message.answer(
            "❌ Неверный формат.\n\n"
            "Используй:\n"
            "`/signal XAUUSD BUY 2341 SL 2325 TP 2380`\n"
            "`/signal EURUSD SELL 1.0850 SL 1.0880 TP 1.0790 TP2 1.0750`\n"
            "`/signal XAUUSD BUY 2341 SL 2325 TP 2380 # Отбой от поддержки`",
            parse_mode="Markdown"
        )
        return

    # Генерируем AI комментарий
    ai_comment = await generate_ai_comment(data)
    if ai_comment:
        data["comment"] = ai_comment

    post = format_signal_post(data)

    # Превью для админа
    await message.answer(
        f"👁 *Превью сигнала:*\n\n{post}\n\n"
        f"Отправить в канал? /confirm или /cancel",
        parse_mode="Markdown"
    )

    # Сохраняем пост во временное хранилище
    router.signal_preview = post


@router.message(Command("confirm"))
async def cmd_confirm(message: Message):
    if message.from_user.id != config.ADMIN_ID:
        return

    post = getattr(router, "signal_preview", None)
    if not post:
        await message.answer("❌ Нет сигнала для отправки. Сначала /signal")
        return

    bot = message.bot
    await bot.send_message(
        chat_id=config.CHANNEL_ID,
        text=post,
        parse_mode="Markdown"
    )
    router.signal_preview = None
    await message.answer("✅ Сигнал опубликован в канале!")
    logger.info("✅ Сигнал опубликован")


@router.message(Command("cancel"))
async def cmd_cancel(message: Message):
    if message.from_user.id != config.ADMIN_ID:
        return
    router.signal_preview = None
    await message.answer("❌ Отменено.")


@router.message(Command("help"))
async def cmd_help(message: Message):
    if message.from_user.id != config.ADMIN_ID:
        return
    await message.answer(
        "🐺 *White Wolf Bot — команды:*\n\n"
        "*Сигналы:*\n"
        "`/signal XAUUSD BUY 2341 SL 2325 TP 2380`\n"
        "`/signal EURUSD SELL 1.085 SL 1.088 TP 1.079 TP2 1.075`\n"
        "`/signal GBPUSD BUY 1.32 SL 1.315 TP 1.33 # комментарий`\n\n"
        "*Управление:*\n"
        "`/confirm` — опубликовать сигнал\n"
        "`/cancel` — отменить\n\n"
        "*Инструменты:*\n"
        "XAUUSD, EURUSD, GBPUSD, USDJPY, USDCHF, BTCUSD\n",
        parse_mode="Markdown"
    )
