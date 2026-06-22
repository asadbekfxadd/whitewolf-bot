
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from config import config
import httpx
import logging

logger = logging.getLogger(__name__)
router = Router()


class SignalForm(StatesGroup):
    choosing_symbol    = State()
    choosing_direction = State()
    entering_entry     = State()
    entering_sl        = State()
    entering_tp        = State()
    entering_tp2       = State()
    confirming         = State()


def kb_symbols():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🥇 XAUUSD", callback_data="sym_XAUUSD"),
            InlineKeyboardButton(text="💶 EURUSD", callback_data="sym_EURUSD"),
        ],
        [
            InlineKeyboardButton(text="💷 GBPUSD", callback_data="sym_GBPUSD"),
            InlineKeyboardButton(text="💴 USDJPY", callback_data="sym_USDJPY"),
        ],
        [
            InlineKeyboardButton(text="🇨🇭 USDCHF", callback_data="sym_USDCHF"),
            InlineKeyboardButton(text="🪙 BTCUSD",  callback_data="sym_BTCUSD"),
        ],
        [InlineKeyboardButton(text="✏️ Другой инструмент", callback_data="sym_OTHER")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")],
    ])


def kb_direction():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🟢 BUY (Покупка)",  callback_data="dir_BUY"),
            InlineKeyboardButton(text="🔴 SELL (Продажа)", callback_data="dir_SELL"),
        ],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")],
    ])


def kb_skip_tp2():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➡️ Пропустить TP2", callback_data="skip_tp2")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")],
    ])


def kb_confirm(post_text: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Опубликовать", callback_data="pub_confirm"),
            InlineKeyboardButton(text="❌ Отмена",       callback_data="cancel"),
        ],
    ])


@router.message(Command("signal"))
async def cmd_signal(message: Message, state: FSMContext):
    if message.from_user.id != config.ADMIN_ID:
        return
    await state.clear()
    await message.answer("🎯 *Выбери инструмент:*", parse_mode="Markdown", reply_markup=kb_symbols())
    await state.set_state(SignalForm.choosing_symbol)


@router.callback_query(SignalForm.choosing_symbol, F.data.startswith("sym_"))
async def cb_symbol(call: CallbackQuery, state: FSMContext):
    symbol = call.data.replace("sym_", "")
    if symbol == "OTHER":
        await call.message.edit_text("✏️ Введи название инструмента (например AUDUSD):")
        await state.update_data(waiting_custom=True)
    else:
        await state.update_data(symbol=symbol)
        await call.message.edit_text(
            f"📍 Инструмент: *{symbol}*\n\nВыбери направление:",
            parse_mode="Markdown",
            reply_markup=kb_direction()
        )
        await state.set_state(SignalForm.choosing_direction)
    await call.answer()


@router.message(SignalForm.choosing_symbol)
async def msg_custom_symbol(message: Message, state: FSMContext):
    data = await state.get_data()
    if data.get("waiting_custom"):
        symbol = message.text.upper().strip()
        await state.update_data(symbol=symbol, waiting_custom=False)
        await message.answer(
            f"📍 Инструмент: *{symbol}*\n\nВыбери направление:",
            parse_mode="Markdown",
            reply_markup=kb_direction()
        )
        await state.set_state(SignalForm.choosing_direction)


@router.callback_query(SignalForm.choosing_direction, F.data.startswith("dir_"))
async def cb_direction(call: CallbackQuery, state: FSMContext):
    direction = call.data.replace("dir_", "")
    data = await state.get_data()
    await state.update_data(direction=direction)
    emoji = "🟢" if direction == "BUY" else "🔴"
    await call.message.edit_text(
        f"📍 *{data['symbol']}* — {emoji} {direction}\n\n💰 Введи цену *входа*:",
        parse_mode="Markdown"
    )
    await state.set_state(SignalForm.entering_entry)
    await call.answer()


@router.message(SignalForm.entering_entry)
async def msg_entry(message: Message, state: FSMContext):
    try:
        entry = float(message.text.replace(",", "."))
        await state.update_data(entry=entry)
        await message.answer(f"📍 Вход: *{entry}*\n\n🛑 Введи *Stop Loss*:", parse_mode="Markdown")
        await state.set_state(SignalForm.entering_sl)
    except ValueError:
        await message.answer("❌ Введи число. Например: `2341.50`", parse_mode="Markdown")


@router.message(SignalForm.entering_sl)
async def msg_sl(message: Message, state: FSMContext):
    try:
        sl = float(message.text.replace(",", "."))
        await state.update_data(sl=sl)
        await message.answer(f"🛑 Stop Loss: *{sl}*\n\n✅ Введи *Take Profit 1*:", parse_mode="Markdown")
        await state.set_state(SignalForm.entering_tp)
    except ValueError:
        await message.answer("❌ Введи число. Например: `2325`", parse_mode="Markdown")


@router.message(SignalForm.entering_tp)
async def msg_tp(message: Message, state: FSMContext):
    try:
        tp = float(message.text.replace(",", "."))
        await state.update_data(tp=tp)
        await message.answer(
            f"✅ TP1: *{tp}*\n\n✅ Введи *Take Profit 2* (необязательно):",
            parse_mode="Markdown",
            reply_markup=kb_skip_tp2()
        )
        await state.set_state(SignalForm.entering_tp2)
    except ValueError:
        await message.answer("❌ Введи число. Например: `2380`", parse_mode="Markdown")


@router.callback_query(SignalForm.entering_tp2, F.data == "skip_tp2")
async def cb_skip_tp2(call: CallbackQuery, state: FSMContext):
    await state.update_data(tp2=None)
    await _show_preview(call.message, state, edit=True)
    await call.answer()


@router.message(SignalForm.entering_tp2)
async def msg_tp2(message: Message, state: FSMContext):
    try:
        tp2 = float(message.text.replace(",", "."))
        await state.update_data(tp2=tp2)
        await _show_preview(message, state, edit=False)
    except ValueError:
        await message.answer("❌ Введи число или нажми 'Пропустить'", parse_mode="Markdown")


async def _show_preview(message: Message, state: FSMContext, edit: bool = False):
    data = await state.get_data()
    post = _format_post(data)
    await state.update_data(post=post)
    await state.set_state(SignalForm.confirming)
    text = f"👁 *ПРЕВЬЮ СИГНАЛА:*\n\n{post}"
    if edit:
        await message.edit_text(text, parse_mode="Markdown", reply_markup=kb_confirm(post))
    else:
        await message.answer(text, parse_mode="Markdown", reply_markup=kb_confirm(post))


@router.callback_query(SignalForm.confirming, F.data == "pub_confirm")
async def cb_publish(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    post = data.get("post", "")
    ai = await _ai_comment(data)
    if ai:
        post = post + f"\n\n💬 _{ai}_"
    await call.message.bot.send_message(chat_id=config.CHANNEL_ID, text=post, parse_mode="Markdown")
    await call.message.edit_text("✅ Сигнал опубликован в канале!")
    await state.clear()
    await call.answer()


@router.callback_query(F.data == "cancel")
async def cb_cancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("❌ Отменено.")
    await call.answer()


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    if message.from_user.id != config.ADMIN_ID:
        return
    await state.clear()
    await message.answer("❌ Отменено.")


@router.message(Command("calendar"))
async def cmd_calendar(message: Message):
    if message.from_user.id != config.ADMIN_ID:
        return
    await message.answer("📅 Загружаю календарь...")
    from calendar_parser import fetch_forex_factory_calendar, format_calendar_post
    events = await fetch_forex_factory_calendar(days_ahead=0)
    text = await format_calendar_post(events)
    await message.answer(text, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="📢 Опубликовать", callback_data="cal_pub"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"),
        ]])
    )


@router.callback_query(F.data == "cal_pub")
async def cb_cal_pub(call: CallbackQuery):
    from calendar_parser import fetch_forex_factory_calendar, format_calendar_post
    events = await fetch_forex_factory_calendar(days_ahead=0)
    text = await format_calendar_post(events)
    await call.message.bot.send_message(chat_id=config.CHANNEL_ID, text=text, parse_mode="Markdown")
    await call.message.edit_text("✅ Календарь опубликован!")
    await call.answer()


@router.message(Command("help"))
async def cmd_help(message: Message):
    if message.from_user.id != config.ADMIN_ID:
        return
    await message.answer(
        "🐺 *White Wolf Bot — команды:*\n\n"
        "`/signal` — создать сигнал (с кнопками)\n"
        "`/calendar` — календарь событий\n"
        "`/cancel` — отменить действие\n",
        parse_mode="Markdown"
    )


def _format_post(data: dict) -> str:
    symbol    = data.get("symbol", "")
    direction = data.get("direction", "")
    entry     = data.get("entry")
    sl        = data.get("sl")
    tp        = data.get("tp")
    tp2       = data.get("tp2")
    dir_emoji = "🟢 ПОКУПКА" if direction == "BUY" else "🔴 ПРОДАЖА"

    def fmt(v):
        if v is None: return "—"
        return f"{v:,.5g}"

    rr = "—"
    if sl and tp:
        try:
            risk = abs(entry - sl)
            reward = abs(tp - entry)
            rr = f"1:{round(reward/risk, 1)}" if risk else "—"
        except Exception:
            pass

    pips = ""
    if sl:
        if "XAU" in symbol or "GOLD" in symbol:
            pips = f"${round(abs(entry - sl), 2)}"
        else:
            pips = f"{round(abs(entry - sl) * 10000)} pip"

    post  = f"⚡️ *СИГНАЛ WHITE WOLF*\n\n"
    post += f"🎯 *{symbol}* — {dir_emoji}\n\n"
    post += f"━━━━━━━━━━━━━━━\n"
    post += f"📍 Вход:  `{fmt(entry)}`\n"
    if sl:  post += f"🛑 Стоп:  `{fmt(sl)}`\n"
    if tp:  post += f"✅ Цель 1: `{fmt(tp)}`\n"
    if tp2: post += f"✅ Цель 2: `{fmt(tp2)}`\n"
    post += f"━━━━━━━━━━━━━━━\n"
    if rr != "—": post += f"⚖️ Риск/Прибыль: *{rr}*\n"
    if pips:      post += f"📏 Риск: *{pips}*\n"
    post += f"⚠️ Риск на сделку: *не более 1-2% депозита*\n\n"
    post += f"🐺 _White Wolf_\n"
    post += f"#whitewolf #signal #{symbol.lower()}"
    return post


async def _ai_comment(data: dict) -> str:
    try:
        prompt = (
            f"Напиши КОРОТКИЙ комментарий (2 предложения) к сигналу в стиле White Wolf.\n"
            f"Сигнал: {data.get('symbol')} {data.get('direction')} от {data.get('entry')}, "
            f"стоп {data.get('sl')}, цель {data.get('tp')}.\n"
            f"Уверенно, без воды. Заканчивай на 🐺"
        )
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
                    "max_tokens": 120,
                    "messages": [{"role": "user", "content": prompt}]
                }
            )
            return resp.json()["content"][0]["text"]
    except Exception as e:
        logger.warning(f"AI: {e}")
        return ""
