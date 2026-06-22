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

# Хранилище активных сигналов и ожиданий
active_signals = {}
pending_tp = {}  # {admin_chat_id: {type, signal_id, text}}


class SignalForm(StatesGroup):
    choosing_symbol    = State()
    choosing_direction = State()
    entering_entry     = State()
    entering_sl        = State()
    entering_tp        = State()
    entering_tp2       = State()
    confirming         = State()


class PhotoCaption(StatesGroup):
    waiting    = State()  # ждём текст для кастомного фото
    waiting_tp = State()  # ждём скриншот для TP


# ── Клавиатуры ───────────────────────────────────────────────────────────────

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


def kb_confirm():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Опубликовать", callback_data="pub_confirm"),
            InlineKeyboardButton(text="❌ Отмена",       callback_data="cancel"),
        ],
    ])


def kb_signal_actions(signal_id: str, tp1_hit: bool = False, tp2_hit: bool = False):
    buttons = []
    tp_row = []
    if not tp1_hit:
        tp_row.append(InlineKeyboardButton(text="✅ TP1 Hit", callback_data=f"tp1_{signal_id}"))
    else:
        tp_row.append(InlineKeyboardButton(text="✅ TP1 ✓", callback_data="noop"))
    if not tp2_hit:
        tp_row.append(InlineKeyboardButton(text="✅ TP2 Hit", callback_data=f"tp2_{signal_id}"))
    else:
        tp_row.append(InlineKeyboardButton(text="✅ TP2 ✓", callback_data="noop"))
    buttons.append(tp_row)
    buttons.append([InlineKeyboardButton(text="🔒 Безубыток", callback_data=f"be_{signal_id}")])
    buttons.append([InlineKeyboardButton(text="🏁 Охота завершена (закрыть)", callback_data=f"close_{signal_id}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def kb_tp_screenshot(tp_type: str, signal_id: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📸 Добавить скриншот", callback_data=f"addscr_{tp_type}_{signal_id}")],
        [InlineKeyboardButton(text="➡️ Без скриншота",     callback_data=f"noscr_{tp_type}_{signal_id}")],
    ])


def kb_screenshot_caption():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📈 Открываю сделку", callback_data="scr_open"),
            InlineKeyboardButton(text="✅ Закрыл в плюс",   callback_data="scr_win"),
        ],
        [
            InlineKeyboardButton(text="📊 Анализ рынка",    callback_data="scr_analysis"),
            InlineKeyboardButton(text="✍️ Свой текст",       callback_data="scr_custom"),
        ],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")],
    ])


# ── /signal ───────────────────────────────────────────────────────────────────

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
        await call.message.edit_text("✏️ Введи название инструмента:")
        await state.update_data(waiting_custom=True)
    else:
        await state.update_data(symbol=symbol)
        await call.message.edit_text(
            f"📍 Инструмент: *{symbol}*\n\nВыбери направление:",
            parse_mode="Markdown", reply_markup=kb_direction()
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
            f"📍 *{symbol}*\n\nВыбери направление:",
            parse_mode="Markdown", reply_markup=kb_direction()
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
        await message.answer(f"🛑 SL: *{sl}*\n\n✅ Введи *Take Profit 1*:", parse_mode="Markdown")
        await state.set_state(SignalForm.entering_tp)
    except ValueError:
        await message.answer("❌ Введи число.", parse_mode="Markdown")


@router.message(SignalForm.entering_tp)
async def msg_tp(message: Message, state: FSMContext):
    try:
        tp = float(message.text.replace(",", "."))
        await state.update_data(tp=tp)
        await message.answer(
            f"✅ TP1: *{tp}*\n\n✅ Введи *Take Profit 2* (необязательно):",
            parse_mode="Markdown", reply_markup=kb_skip_tp2()
        )
        await state.set_state(SignalForm.entering_tp2)
    except ValueError:
        await message.answer("❌ Введи число.", parse_mode="Markdown")


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
    text = f"👁 *ПРЕВЬЮ:*\n\n{post}"
    if edit:
        await message.edit_text(text, parse_mode="Markdown", reply_markup=kb_confirm())
    else:
        await message.answer(text, parse_mode="Markdown", reply_markup=kb_confirm())


@router.callback_query(SignalForm.confirming, F.data == "pub_confirm")
async def cb_publish(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    post = data.get("post", "")
    ai = await _ai_comment(data)
    if ai:
        post = post + f"\n\n💬 _{ai}_"

    import time
    signal_id = str(int(time.time()))

    sent = await call.message.bot.send_message(
        chat_id=config.CHANNEL_ID,
        text=post,
        parse_mode="Markdown",
        reply_markup=kb_signal_actions(signal_id)
    )

    active_signals[signal_id] = {
        "message_id": sent.message_id,
        "post": post,
        "data": data,
        "tp1_hit": False,
        "tp2_hit": False,
    }

    await call.message.edit_text("✅ Сигнал опубликован! Управляй через кнопки в канале 👇")
    await state.clear()
    await call.answer()


# ── TP1 ───────────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("tp1_"))
async def cb_tp1(call: CallbackQuery, state: FSMContext):
    signal_id = call.data.replace("tp1_", "")
    sig = active_signals.get(signal_id)
    if not sig:
        await call.answer("Сигнал не найден")
        return
    sig["tp1_hit"] = True
    data = sig["data"]
    tp1 = data.get("tp")

    # Обновляем пост
    await call.message.bot.edit_message_reply_markup(
        chat_id=config.CHANNEL_ID,
        message_id=sig["message_id"],
        reply_markup=kb_signal_actions(signal_id, tp1_hit=True, tp2_hit=sig["tp2_hit"])
    )

    # Спрашиваем скриншот
    tp1_text = (
        f"✅ *TP1 ВЗЯТ!*\n\n"
        f"🎯 {data.get('symbol')} — цель `{tp1}` достигнута\n"
        f"💰 Фиксируем часть прибыли\n"
        f"🔒 Стоп переносим в безубыток\n\n"
        f"🐺 _White Wolf_\n#whitewolf #tp1 #{data.get('symbol','').lower()}"
    )
    pending_tp[call.from_user.id] = {
        "type": "tp1",
        "signal_id": signal_id,
        "text": tp1_text
    }

    await call.message.answer(
        f"✅ TP1 отмечен!\n\nДобавить скриншот к публикации?",
        reply_markup=kb_tp_screenshot("tp1", signal_id)
    )
    await call.answer()


# ── TP2 ───────────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("tp2_"))
async def cb_tp2(call: CallbackQuery, state: FSMContext):
    signal_id = call.data.replace("tp2_", "")
    sig = active_signals.get(signal_id)
    if not sig:
        await call.answer("Сигнал не найден")
        return
    sig["tp2_hit"] = True
    data = sig["data"]
    tp2 = data.get("tp2") or data.get("tp")

    await call.message.bot.edit_message_reply_markup(
        chat_id=config.CHANNEL_ID,
        message_id=sig["message_id"],
        reply_markup=kb_signal_actions(signal_id, tp1_hit=sig["tp1_hit"], tp2_hit=True)
    )

    tp2_text = (
        f"🏆 *TP2 ВЗЯТ!*\n\n"
        f"🎯 {data.get('symbol')} — цель `{tp2}` достигнута\n"
        f"💰 Фиксируем прибыль по второй цели\n\n"
        f"🐺 _White Wolf_\n#whitewolf #tp2 #{data.get('symbol','').lower()}"
    )
    pending_tp[call.from_user.id] = {
        "type": "tp2",
        "signal_id": signal_id,
        "text": tp2_text
    }

    await call.message.answer(
        f"🏆 TP2 отмечен!\n\nДобавить скриншот к публикации?",
        reply_markup=kb_tp_screenshot("tp2", signal_id)
    )
    await call.answer()


# ── Скриншот для TP ───────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("addscr_"))
async def cb_add_screenshot(call: CallbackQuery, state: FSMContext):
    parts = call.data.split("_")
    tp_type = parts[1]
    signal_id = parts[2]
    await state.update_data(tp_type=tp_type, signal_id=signal_id)
    await state.set_state(PhotoCaption.waiting_tp)
    await call.message.edit_text("📸 Отправь скриншот:")
    await call.answer()


@router.callback_query(F.data.startswith("noscr_"))
async def cb_no_screenshot(call: CallbackQuery):
    parts = call.data.split("_")
    tp_type = parts[1]
    signal_id = parts[2]

    tp_data = pending_tp.get(call.from_user.id)
    if tp_data:
        await call.message.bot.send_message(
            chat_id=config.CHANNEL_ID,
            text=tp_data["text"],
            parse_mode="Markdown"
        )
        pending_tp.pop(call.from_user.id, None)

    await call.message.edit_text("✅ Опубликовано без скриншота!")
    await call.answer()


@router.message(PhotoCaption.waiting_tp, F.photo, F.from_user.id == config.ADMIN_ID)
async def handle_tp_screenshot(message: Message, state: FSMContext):
    data = await state.get_data()
    tp_data = pending_tp.get(message.from_user.id)

    if not tp_data:
        await message.answer("❌ Данные TP не найдены, попробуй снова")
        await state.clear()
        return

    file_id = message.photo[-1].file_id
    caption = tp_data["text"]

    await message.bot.send_photo(
        chat_id=config.CHANNEL_ID,
        photo=file_id,
        caption=caption,
        parse_mode="Markdown"
    )
    pending_tp.pop(message.from_user.id, None)
    await state.clear()
    await message.answer("✅ Скриншот + результат опубликованы в канале!")


# ── Безубыток ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("be_"))
async def cb_breakeven(call: CallbackQuery):
    signal_id = call.data.replace("be_", "")
    sig = active_signals.get(signal_id)
    if not sig:
        await call.answer("Сигнал не найден")
        return
    data = sig["data"]
    await call.message.bot.send_message(
        chat_id=config.CHANNEL_ID,
        text=(
            f"🔒 *СТОП В БЕЗУБЫТОК*\n\n"
            f"🎯 {data.get('symbol')}\n"
            f"📍 Стоп перенесён на вход: `{data.get('entry')}`\n"
            f"⚠️ Риск = 0. Сделка защищена.\n\n"
            f"🐺 _White Wolf_\n#whitewolf #{data.get('symbol','').lower()}"
        ),
        parse_mode="Markdown"
    )
    await call.answer("🔒 Безубыток объявлен!")


# ── Закрытие сделки ───────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("close_"))
async def cb_close(call: CallbackQuery):
    signal_id = call.data.replace("close_", "")
    sig = active_signals.get(signal_id)
    if not sig:
        await call.answer("Сигнал не найден")
        return
    data = sig["data"]

    await call.message.bot.edit_message_reply_markup(
        chat_id=config.CHANNEL_ID,
        message_id=sig["message_id"],
        reply_markup=None
    )
    await call.message.bot.send_message(
        chat_id=config.CHANNEL_ID,
        text=(
            f"🏁 *ОХОТА ЗАВЕРШЕНА*\n\n"
            f"🎯 {data.get('symbol')} — сделка закрыта\n"
            f"📍 Вход был: `{data.get('entry')}`\n\n"
            f"🐺 _Следим за следующей возможностью._\n\n"
            f"#whitewolf #{data.get('symbol','').lower()}"
        ),
        parse_mode="Markdown"
    )
    active_signals.pop(signal_id, None)
    await call.answer("Сделка закрыта")


# ── Скриншот без сигнала ──────────────────────────────────────────────────────

@router.message(F.photo, F.from_user.id == config.ADMIN_ID)
async def handle_screenshot(message: Message, state: FSMContext):
    current = await state.get_state()
    if current == PhotoCaption.waiting_tp:
        return  # обрабатывается выше

    photo_file_id = message.photo[-1].file_id
    active_signals[f"photo_{message.message_id}"] = {"file_id": photo_file_id}

    await message.answer(
        "📸 Скриншот получен! Что написать?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="📈 Открываю сделку", callback_data=f"scr_open_{message.message_id}"),
                InlineKeyboardButton(text="✅ Закрыл в плюс",   callback_data=f"scr_win_{message.message_id}"),
            ],
            [
                InlineKeyboardButton(text="📊 Анализ рынка",    callback_data=f"scr_analysis_{message.message_id}"),
                InlineKeyboardButton(text="✍️ Свой текст",       callback_data=f"scr_custom_{message.message_id}"),
            ],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")],
        ])
    )


@router.callback_query(F.data.startswith("scr_"))
async def cb_screenshot(call: CallbackQuery, state: FSMContext):
    parts = call.data.split("_")
    action = parts[1]
    msg_id = parts[2] if len(parts) > 2 else ""

    photo_data = active_signals.get(f"photo_{msg_id}")
    if not photo_data:
        await call.answer("Фото не найдено, отправь снова")
        return

    file_id = photo_data["file_id"]

    if action == "custom":
        await state.update_data(pending_photo=file_id, pending_msg_id=msg_id)
        await state.set_state(PhotoCaption.waiting)
        await call.message.edit_text("✍️ Введи текст для публикации:")
        await call.answer()
        return

    captions = {
        "open": (
            "👁 *ВХОЖУ В СДЕЛКУ*\n\n"
            "Структура сформирована. Момент пришёл.\n"
            "VIP уже внутри с точными данными.\n\n"
            "🐺 _White Wolf_\n#whitewolf #сделка"
        ),
        "win": (
            "✅ *ЗАКРЫТО В ПЛЮС*\n\n"
            "Терпение и дисциплина.\n"
            "Волк берёт только то что запланировал.\n\n"
            "🐺 _White Wolf_\n#whitewolf #результат"
        ),
        "analysis": (
            "📊 *АНАЛИЗ РЫНКА*\n\n"
            "Разбираю текущую структуру.\n"
            "Слежу за реакцией на ключевых уровнях.\n\n"
            "🐺 _White Wolf_\n#whitewolf #аналитика"
        ),
    }

    caption = captions.get(action, "🐺 White Wolf")
    await call.message.bot.send_photo(
        chat_id=config.CHANNEL_ID,
        photo=file_id,
        caption=caption,
        parse_mode="Markdown"
    )
    active_signals.pop(f"photo_{msg_id}", None)
    await call.message.edit_text("✅ Опубликовано!")
    await call.answer()


class PhotoCaption(StatesGroup):
    waiting    = State()
    waiting_tp = State()


@router.message(PhotoCaption.waiting, F.from_user.id == config.ADMIN_ID)
async def handle_custom_caption(message: Message, state: FSMContext):
    data = await state.get_data()
    file_id = data.get("pending_photo")
    msg_id  = data.get("pending_msg_id")

    if not file_id:
        await message.answer("❌ Фото не найдено")
        await state.clear()
        return

    caption = f"{message.text}\n\n🐺 _White Wolf_\n#whitewolf"
    await message.bot.send_photo(
        chat_id=config.CHANNEL_ID,
        photo=file_id,
        caption=caption,
        parse_mode="Markdown"
    )
    active_signals.pop(f"photo_{msg_id}", None)
    await state.clear()
    await message.answer("✅ Опубликовано!")


# ── Отмена ────────────────────────────────────────────────────────────────────

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


@router.callback_query(F.data == "noop")
async def cb_noop(call: CallbackQuery):
    await call.answer()


# ── Календарь ─────────────────────────────────────────────────────────────────

@router.message(Command("calendar"))
async def cmd_calendar(message: Message):
    if message.from_user.id != config.ADMIN_ID:
        return
    await message.answer("📅 Загружаю...")
    from calendar_parser import fetch_forex_factory_calendar, format_calendar_post
    events = await fetch_forex_factory_calendar(days_ahead=0)
    text = await format_calendar_post(events)
    await message.answer(text, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="📢 Опубликовать", callback_data="cal_pub"),
            InlineKeyboardButton(text="❌ Отмена",       callback_data="cancel"),
        ]])
    )


@router.callback_query(F.data == "cal_pub")
async def cb_cal_pub(call: CallbackQuery):
    from calendar_parser import fetch_forex_factory_calendar, format_calendar_post
    events = await fetch_forex_factory_calendar(days_ahead=0)
    text = await format_calendar_post(events)
    await call.message.bot.send_message(
        chat_id=config.CHANNEL_ID, text=text, parse_mode="Markdown"
    )
    await call.message.edit_text("✅ Календарь опубликован!")
    await call.answer()


# ── Help ──────────────────────────────────────────────────────────────────────

@router.message(Command("help"))
async def cmd_help(message: Message):
    if message.from_user.id != config.ADMIN_ID:
        return
    await message.answer(
        "🐺 *White Wolf Bot — команды:*\n\n"
        "`/signal` — создать сигнал с кнопками\n"
        "`/calendar` — календарь событий\n"
        "`/cancel` — отменить действие\n\n"
        "*Скриншоты:*\n"
        "Просто кинь фото боту — выбери подпись\n\n"
        "*Кнопки сигнала в канале:*\n"
        "✅ TP1/TP2 Hit — цель достигнута + скриншот\n"
        "🔒 Безубыток — стоп на вход\n"
        "🏁 Охота завершена — закрыть сделку\n",
        parse_mode="Markdown"
    )


# ── Форматирование ────────────────────────────────────────────────────────────

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

