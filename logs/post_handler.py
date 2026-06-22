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


class PostForm(StatesGroup):
    choosing_type  = State()  # выбор типа поста
    entering_text  = State()  # ввод текста
    adding_photo   = State()  # добавление фото
    previewing     = State()  # превью


# Типы постов
POST_TYPES = {
    "analysis":   ("📊 Анализ рынка",     "Детальный разбор текущей ситуации на рынке"),
    "result":     ("✅ Результат сделки",  "Итог закрытой сделки с деталями"),
    "insight":    ("💡 Инсайт",           "Наблюдение или мысль о рынке"),
    "education":  ("📚 Обучение",         "Образовательный контент для подписчиков"),
    "motivation": ("🐺 Философия волка",  "Мотивационный пост в стиле White Wolf"),
    "news":       ("⚡️ Новость",          "Разбор важного события на рынке"),
}


def kb_post_types():
    buttons = []
    items = list(POST_TYPES.items())
    for i in range(0, len(items), 2):
        row = []
        row.append(InlineKeyboardButton(
            text=items[i][1][0],
            callback_data=f"ptype_{items[i][0]}"
        ))
        if i + 1 < len(items):
            row.append(InlineKeyboardButton(
                text=items[i+1][1][0],
                callback_data=f"ptype_{items[i+1][0]}"
            ))
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="pcancel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def kb_add_photo():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📸 Добавить скриншот", callback_data="padd_photo")],
        [InlineKeyboardButton(text="➡️ Без фото",          callback_data="pno_photo")],
        [InlineKeyboardButton(text="❌ Отмена",             callback_data="pcancel")],
    ])


def kb_preview():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Опубликовать",  callback_data="ppublish"),
            InlineKeyboardButton(text="🔄 Переписать",    callback_data="prewrite"),
        ],
        [
            InlineKeyboardButton(text="📸 Добавить фото", callback_data="padd_photo"),
            InlineKeyboardButton(text="❌ Отмена",         callback_data="pcancel"),
        ],
    ])


def kb_preview_with_photo():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Опубликовать",  callback_data="ppublish"),
            InlineKeyboardButton(text="🔄 Переписать",    callback_data="prewrite"),
        ],
        [
            InlineKeyboardButton(text="🖼 Сменить фото",  callback_data="padd_photo"),
            InlineKeyboardButton(text="❌ Отмена",         callback_data="pcancel"),
        ],
    ])


# ── /post команда ─────────────────────────────────────────────────────────────

@router.message(Command("post"))
async def cmd_post(message: Message, state: FSMContext):
    if message.from_user.id != config.ADMIN_ID:
        return
    await state.clear()
    await message.answer(
        "✍️ *Выбери тип поста:*",
        parse_mode="Markdown",
        reply_markup=kb_post_types()
    )
    await state.set_state(PostForm.choosing_type)


# ── Выбор типа ────────────────────────────────────────────────────────────────

@router.callback_query(PostForm.choosing_type, F.data.startswith("ptype_"))
async def cb_post_type(call: CallbackQuery, state: FSMContext):
    post_type = call.data.replace("ptype_", "")
    type_info = POST_TYPES.get(post_type, ("Пост", ""))
    await state.update_data(post_type=post_type, type_name=type_info[0])
    await call.message.edit_text(
        f"*{type_info[0]}*\n\n"
        f"✍️ Напиши текст. Можешь писать кратко — AI сам оформит:\n\n"
        f"_Например: 'gold пробил 2350, жду откат к 2330 и продолжение'_",
        parse_mode="Markdown"
    )
    await state.set_state(PostForm.entering_text)
    await call.answer()


# ── Ввод текста ───────────────────────────────────────────────────────────────

@router.message(PostForm.entering_text, F.text, F.from_user.id == config.ADMIN_ID)
async def handle_post_text(message: Message, state: FSMContext):
    await state.update_data(raw_text=message.text)
    await message.answer(
        "📸 Добавить скриншот к посту?",
        reply_markup=kb_add_photo()
    )
    await state.set_state(PostForm.adding_photo)


# ── Добавление фото ───────────────────────────────────────────────────────────

@router.callback_query(F.data == "padd_photo")
async def cb_add_photo(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("📸 Отправь скриншот:")
    await state.set_state(PostForm.adding_photo)
    await call.answer()


@router.message(PostForm.adding_photo, F.photo, F.from_user.id == config.ADMIN_ID)
async def handle_post_photo(message: Message, state: FSMContext):
    file_id = message.photo[-1].file_id
    await state.update_data(photo_file_id=file_id)
    await message.answer("🤖 Генерирую пост...")
    await _generate_and_preview(message, state, has_photo=True)


@router.callback_query(F.data == "pno_photo")
async def cb_no_photo(call: CallbackQuery, state: FSMContext):
    await state.update_data(photo_file_id=None)
    await call.message.edit_text("🤖 Генерирую пост...")
    await _generate_and_preview(call.message, state, has_photo=False)
    await call.answer()


# ── Генерация и превью ────────────────────────────────────────────────────────

async def _generate_and_preview(message: Message, state: FSMContext, has_photo: bool):
    data = await state.get_data()
    raw_text  = data.get("raw_text", "")
    post_type = data.get("post_type", "insight")
    photo_id  = data.get("photo_file_id")

    formatted = await _ai_format_post(raw_text, post_type)
    await state.update_data(formatted_post=formatted)
    await state.set_state(PostForm.previewing)

    kb = kb_preview_with_photo() if photo_id else kb_preview()

    if photo_id:
        await message.answer_photo(
            photo=photo_id,
            caption=f"👁 *ПРЕВЬЮ:*\n\n{formatted}",
            parse_mode="Markdown",
            reply_markup=kb
        )
    else:
        await message.answer(
            f"👁 *ПРЕВЬЮ:*\n\n{formatted}",
            parse_mode="Markdown",
            reply_markup=kb
        )


# ── Публикация ────────────────────────────────────────────────────────────────

@router.callback_query(PostForm.previewing, F.data == "ppublish")
async def cb_publish_post(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    post    = data.get("formatted_post", "")
    photo   = data.get("photo_file_id")

    if photo:
        await call.message.bot.send_photo(
            chat_id=config.CHANNEL_ID,
            photo=photo,
            caption=post,
            parse_mode="Markdown"
        )
    else:
        await call.message.bot.send_message(
            chat_id=config.CHANNEL_ID,
            text=post,
            parse_mode="Markdown"
        )

    await call.message.edit_caption("✅ Пост опубликован!") if photo else await call.message.edit_text("✅ Пост опубликован!")
    await state.clear()
    await call.answer("✅ Опубликовано!")


# ── Переписать ────────────────────────────────────────────────────────────────

@router.callback_query(PostForm.previewing, F.data == "prewrite")
async def cb_rewrite_post(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    raw_text  = data.get("raw_text", "")
    post_type = data.get("post_type", "insight")
    photo_id  = data.get("photo_file_id")

    await call.answer("🔄 Переписываю...")
    formatted = await _ai_format_post(raw_text, post_type)
    await state.update_data(formatted_post=formatted)

    kb = kb_preview_with_photo() if photo_id else kb_preview()

    if photo_id:
        try:
            await call.message.edit_caption(
                f"👁 *ПРЕВЬЮ (новый вариант):*\n\n{formatted}",
                parse_mode="Markdown",
                reply_markup=kb
            )
        except Exception:
            await call.message.answer(
                f"👁 *ПРЕВЬЮ (новый вариант):*\n\n{formatted}",
                parse_mode="Markdown",
                reply_markup=kb
            )
    else:
        await call.message.edit_text(
            f"👁 *ПРЕВЬЮ (новый вариант):*\n\n{formatted}",
            parse_mode="Markdown",
            reply_markup=kb
        )


# ── Отмена ────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "pcancel")
async def cb_post_cancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await call.message.edit_text("❌ Пост отменён.")
    except Exception:
        await call.message.edit_caption("❌ Пост отменён.")
    await call.answer()


# ── AI форматирование ─────────────────────────────────────────────────────────

PROMPTS = {
    "analysis": (
        "Оформи как детальный анализ рынка от White Wolf.\n"
        "Структура: заголовок → что происходит → ключевые уровни → что ожидать.\n"
        "Используй: 📊 для данных, 🎯 для уровней, ⚠️ для рисков."
    ),
    "result": (
        "Оформи как результат закрытой сделки от White Wolf.\n"
        "Структура: инструмент и направление → вход/выход → результат в $ или пипсах → вывод.\n"
        "Используй: ✅ для прибыли, 🎯 для уровней, 📊 для статистики."
    ),
    "insight": (
        "Оформи как короткий инсайт или наблюдение от White Wolf.\n"
        "Стиль: уверенный, загадочный, 2-3 абзаца максимум.\n"
        "Без лишних слов — только суть."
    ),
    "education": (
        "Оформи как образовательный пост от White Wolf.\n"
        "Структура: проблема → объяснение → практический вывод.\n"
        "Используй нумерованные пункты или стрелки →."
    ),
    "motivation": (
        "Оформи как философский/мотивационный пост в стиле White Wolf.\n"
        "Метафора волка и охоты. Лаконично. Сильная финальная фраза.\n"
        "Без клише и банальностей."
    ),
    "news": (
        "Оформи как разбор рыночной новости от White Wolf.\n"
        "Структура: что случилось → почему важно → как влияет на рынок → что делать.\n"
        "Используй ⚡️ для срочности, 📊 для данных."
    ),
}


async def _ai_format_post(raw_text: str, post_type: str) -> str:
    type_info = POST_TYPES.get(post_type, ("Пост", ""))
    prompt_addition = PROMPTS.get(post_type, "")

    prompt = (
        f"Ты контент-менеджер анонимного форекс-трейдера White Wolf 🐺\n\n"
        f"Тип поста: {type_info[0]}\n"
        f"{prompt_addition}\n\n"
        f"Исходный текст от трейдера:\n{raw_text}\n\n"
        f"Общие правила:\n"
        f"- Сохрани все факты, цифры и уровни точно\n"
        f"- Стиль: уверенный, лаконичный, с характером\n"
        f"- Форматирование Telegram: **жирный**, _курсив_\n"
        f"- Уровни цен в обратных кавычках: `2341.50`\n"
        f"- В конце: 🐺 _White Wolf_ и хэштеги\n"
        f"- Максимум 250 слов\n"
        f"- Никакой воды и банальностей"
    )

    try:
        async with httpx.AsyncClient(timeout=25) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": config.ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-sonnet-4-6",
                    "max_tokens": 500,
                    "messages": [{"role": "user", "content": prompt}]
                }
            )
            return resp.json()["content"][0]["text"]
    except Exception as e:
        logger.warning(f"AI пост: {e}")
        return (
            f"*{type_info[0].upper()}*\n\n"
            f"{raw_text}\n\n"
            f"🐺 _White Wolf_\n#whitewolf"
        )

