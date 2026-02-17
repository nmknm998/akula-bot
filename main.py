import os
import base64
import asyncio
from typing import Optional, List, Dict, Any

import httpx
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery, BufferedInputFile
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder


# =========================
# Config
# =========================
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
API_BASE_URL = os.getenv("API_BASE_URL", "https://voiceapi.csv666.ru").strip()
API_KEY = os.getenv("API_KEY", "").strip()
API_TIMEOUT_SEC = float(os.getenv("API_TIMEOUT_SEC", "120"))

if not BOT_TOKEN:
    raise RuntimeError("Не найден BOT_TOKEN. Добавь его в .env")

AKULA_NAME = "Akula Bot"
RATIOS: List[str] = ["16:9", "9:16", "3:2", "2:3", "4:3", "3:4", "1:1"]

def neon_title(text: str) -> str:
    return f"🦈🌌 *{text}*"

def escape_md(text: str) -> str:
    return text

# =========================
# Keyboards
# =========================
def kb_main_menu():
    b = ReplyKeyboardBuilder()
    b.button(text="✨ Создать")
    b.button(text="🪄 Редактировать")
    b.adjust(2)
    return b.as_markup(resize_keyboard=True)

def kb_count(prefix: str):
    b = InlineKeyboardBuilder()
    for i in range(1, 7):
        b.button(text=str(i), callback_data=f"{prefix}:{i}")
    b.adjust(6)
    return b.as_markup()

def kb_ratios():
    b = InlineKeyboardBuilder()
    for r in RATIOS:
        b.button(text=r, callback_data=f"create_ratio:{r}")
    b.adjust(3, 2, 2)
    b.row()
    b.button(text="✅ Продолжить", callback_data="create_ratio_done")
    return b.as_markup()

def kb_confirm(prefix: str):
    b = InlineKeyboardBuilder()
    b.button(text="✅ Подтвердить", callback_data=f"{prefix}_confirm:yes")
    b.button(text="⬅️ Назад", callback_data=f"{prefix}_confirm:back")
    b.adjust(2)
    return b.as_markup()

def kb_after_result(mode: str):
    b = InlineKeyboardBuilder()
    b.button(text="🔁 Перегенерировать", callback_data=f"{mode}_after:regen")
    b.button(text="✨ Новая генерация", callback_data="go:new")
    b.button(text="🛠 Редактировать результат", callback_data="go:edit_last")
    b.button(text="🏠 В меню", callback_data="go:menu")
    b.adjust(1)
    return b.as_markup()

class CreateFlow(StatesGroup):
    prompt = State()
    count = State()
    ratio = State()
    confirm = State()

class EditFlow(StatesGroup):
    photo = State()
    prompt = State()
    count = State()
    confirm = State()

class ImageAPIError(Exception):
    pass

async def _api_headers() -> Dict[str, str]:
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if API_KEY:
        headers["x-API-Key"] = API_KEY
    return headers

def _parse_single_image(data: Any) -> bytes:
    if not isinstance(data, dict) or "image_b64" not in data:
        raise ImageAPIError(f"Неожиданный ответ API: {data}")
    b64 = data["image_b64"]
    try:
        return base64.b64decode(b64)
    except Exception as e:
        raise ImageAPIError(f"Не удалось декодировать base64: {e}")

async def api_image_generate(prompt: str, ratio: str, n: int) -> List[bytes]:
    url = f"{API_BASE_URL.rstrip('/')}/api/v1/image/create"
    headers = await _api_headers()
    images: List[bytes] = []
    async with httpx.AsyncClient(timeout=API_TIMEOUT_SEC) as client:
        for _ in range(n):
            payload = {"prompt": prompt, "aspect_ratio": ratio}
            r = await client.post(url, json=payload, headers=headers)
            if r.status_code >= 400:
                raise ImageAPIError(f"API ошибка {r.status_code}: {r.text}")
            data = r.json()
            images.append(_parse_single_image(data))
    return images

async def api_edit_images(init_image_bytes: bytes, prompt: str, n: int) -> List[bytes]:
    url = f"{API_BASE_URL.rstrip('/')}/api/v1/image/edit"
    headers = await _api_headers()
    images: List[bytes] = []
    ref_b64 = base64.b64encode(init_image_bytes).decode("utf-8")
    async with httpx.AsyncClient(timeout=API_TIMEOUT_SEC) as client:
        for _ in range(n):
            payload = {"reference_image_b64": ref_b64, "edit_instruction": prompt}
            r = await client.post(url, json=payload, headers=headers)
            if r.status_code >= 400:
                raise ImageAPIError(f"API ошибка {r.status_code}: {r.text}")
            data = r.json()
            images.append(_parse_single_image(data))
    return images

router = Router()

async def send_progress(message: Message, text: str) -> Message:
    return await message.answer(text, parse_mode="Markdown")

async def update_progress(bot: Bot, chat_id: int, msg_id: int, text: str):
    try:
        await bot.edit_message_text(text, chat_id=chat_id, message_id=msg_id, parse_mode="Markdown")
    except Exception:
        pass

def build_create_summary(prompt: str, ratio: str, n: int) -> str:
    title = neon_title('Проверим параметры')
    return (
        f"{title}\n\n"
        f"• 📝 *Промпт:* {escape_md(prompt)}\n"
        f"• 📐 *Соотношение сторон:* *{ratio}*\n"
        f"• 🔢 *Вариантов:* *{n}*\n\n"
        f"Запускаем генерацию? ⚡️"
    )

def build_edit_summary(prompt: str, n: int) -> str:
    title = neon_title('Проверим параметры')
    return (
        f"{title}\n\n"
        f"• 📝 *Промпт:* {escape_md(prompt)}\n"
        f"• 🖼 *Исходное изображение:* загружено ✅\n"
        f"• 🔢 *Вариантов:* *{n}*\n\n"
        f"Запускаем редактирование? ⚡️"
    )

@router.message(CommandStart())
async def start(m: Message, state: FSMContext):
    await state.clear()
    title = neon_title(AKULA_NAME)
    await m.answer(
        f"{title}\n\n"
        "Выберите режим работы ниже 👇\n"
        "⚡️ *Создать* — генерация по тексту\n"
        "🪄 *Редактировать* — изменить ваше фото по описанию",
        reply_markup=kb_main_menu(),
        parse_mode="Markdown",
    )

@router.message(F.text == "🏠 Главное меню")
async def go_menu_text(m: Message, state: FSMContext):
    await state.clear()
    await m.answer("🏠 Главное меню", reply_markup=kb_main_menu())

@router.message(F.text == "✨ Создать")
async def create_entry(m: Message, state: FSMContext):
    await state.clear()
    await state.set_state(CreateFlow.prompt)
    title = neon_title('Опишите, что нужно сгенерировать')
    await m.answer(
        f"{title}\n\n"
        "Отправьте текст *одним сообщением* 💬",
        parse_mode="Markdown",
        reply_markup=kb_main_menu(),
    )

@router.message(CreateFlow.prompt, F.text)
async def create_got_prompt(m: Message, state: FSMContext):
    prompt = m.text.strip()
    await state.update_data(create_prompt=prompt)
    await state.set_state(CreateFlow.count)
    title = neon_title('Сколько вариантов сгенерировать?')
    await m.answer(
        f"{title}\n\n"
        "Выберите число ниже 👇",
        parse_mode="Markdown",
        reply_markup=kb_count("create_cnt"),
    )

@router.callback_query(F.data.startswith("create_cnt:"))
async def create_got_count(c: CallbackQuery, state: FSMContext):
    n = int(c.data.split(":")[1])
    await state.update_data(create_n=n)
    await state.set_state(CreateFlow.ratio)
    title = neon_title('Соотношение сторон')
    await c.message.answer(
        f"{title}\n\n"
        "Выберите формат кадра 📐",
        parse_mode="Markdown",
        reply_markup=kb_ratios(),
    )
    await c.answer()

@router.callback_query(CreateFlow.ratio, F.data.startswith("create_ratio:"))
async def create_select_ratio(c: CallbackQuery, state: FSMContext):
    ratio = c.data.split(":")[1]
    await state.update_data(create_ratio=ratio)
    await c.answer(f"Выбрано: {ratio}")

@router.callback_query(CreateFlow.ratio, F.data == "create_ratio_done")
async def create_ratio_done(c: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    prompt = data.get("create_prompt")
    ratio = data.get("create_ratio")
    n = data.get("create_n")
    if not ratio:
        await c.answer("Сначала выберите соотношение сторон.", show_alert=True)
        return
    await state.set_state(CreateFlow.confirm)
    await c.message.answer(
        build_create_summary(prompt, ratio, n),
        parse_mode="Markdown",
        reply_markup=kb_confirm("create"),
    )
    await c.answer()

@router.callback_query(CreateFlow.confirm, F.data.startswith("create_confirm:"))
async def create_confirm(c: CallbackQuery, state: FSMContext, bot: Bot):
    action = c.data.split(":")[1]
    data = await state.get_data()
    if action == "back":
        await state.set_state(CreateFlow.ratio)
        title = neon_title('Соотношение сторон')
        await c.message.answer(
            f"{title}\n\nВыберите формат кадра 📐",
            parse_mode="Markdown",
            reply_markup=kb_ratios(),
        )
        await c.answer()
        return
    prompt = data["create_prompt"]
    ratio = data["create_ratio"]
    n = data["create_n"]
    progress_msg = await send_progress(c.message, "⚡️ *Генерация*\n\nПрогресс: *0/3*")
    await c.answer()
    try:
        await update_progress(bot, progress_msg.chat.id, progress_msg.message_id, "⚡️ *Генерация*\n\nПрогресс: *1/3*")
        images = await api_image_generate(prompt=prompt, ratio=ratio, n=n)
        await update_progress(bot, progress_msg.chat.id, progress_msg.message_id, "⚡️ *Генерация*\n\nПрогресс: *2/3*")
        last_sent_file_id: Optional[str] = None
        for idx, img_bytes in enumerate(images, start=1):
            file = BufferedInputFile(img_bytes, filename=f"akula_{idx}.jpg")
            sent = await c.message.answer_photo(file)
            last_sent_file_id = sent.photo[-1].file_id if sent.photo else last_sent_file_id
        await update_progress(bot, progress_msg.chat.id, progress_msg.message_id, "⚡️ *Генерация*\n\nПрогресс: *3/3* ✅")
        await state.update_data(last_image_file_id=last_sent_file_id, last_mode="create", last_prompt=prompt, last_ratio=ratio, last_n=n)
        await c.message.answer(
            f"⭐️ *Изображение успешно создано*\n\n"
            f"• 📝 *Промпт:* {escape_md(prompt)}\n"
            f"• 📐 *Соотношение сторон:* *{ratio}*\n\n"
            f"💡 *Что дальше?*\nВыберите действие кнопками ниже.",
            parse_mode="Markdown",
            reply_markup=kb_after_result("create"),
        )
        await state.clear()
    except Exception as e:
        await c.message.answer(f"❌ Ошибка генерации: `{e}`", parse_mode="Markdown")
        await state.clear()

@router.message(F.text == "🪄 Редактировать")
async def edit_entry(m: Message, state: FSMContext):
    await state.clear()
    await state.set_state(EditFlow.photo)
    title = neon_title('Отправьте изображение')
    await m.answer(
        f"{title}\n\n"
        "Пришлите фото, которое хотите отредактировать 🖼",
        parse_mode="Markdown",
        reply_markup=kb_main_menu(),
    )

@router.message(EditFlow.photo, F.photo)
async def edit_got_photo(m: Message, state: FSMContext, bot: Bot):
    photo = m.photo[-1]
    file = await bot.get_file(photo.file_id)
    buf = await bot.download_file(file.file_path)
    img_bytes = buf.read()
    await state.update_data(edit_image_bytes=img_bytes, edit_image_file_id=photo.file_id)
    await state.set_state(EditFlow.prompt)
    title = neon_title('Описание изменений')
    await m.answer(
        f"{title}\n\n"
        "Коротко сформулируйте правки ✍️\n\n"
        "*Пример:*\n"
        "Добавьте космический фон и летающих дельфинов 🌌🐬",
        parse_mode="Markdown",
    )

@router.message(EditFlow.prompt, F.text)
async def edit_got_prompt(m: Message, state: FSMContext):
    prompt = m.text.strip()
    await state.update_data(edit_prompt=prompt)
    await state.set_state(EditFlow.count)
    title = neon_title('Сколько вариантов отредактировать за раз?')
    await m.answer(
        f"{title}\n\n"
        "Выберите число ниже 👇",
        parse_mode="Markdown",
        reply_markup=kb_count("edit_cnt"),
    )

@router.callback_query(F.data.startswith("edit_cnt:"))
async def edit_got_count(c: CallbackQuery, state: FSMContext):
    n = int(c.data.split(":")[1])
    await state.update_data(edit_n=n)
    data = await state.get_data()
    prompt = data.get("edit_prompt")
    await state.set_state(EditFlow.confirm)
    await c.message.answer(
        build_edit_summary(prompt, n),
        parse_mode="Markdown",
        reply_markup=kb_confirm("edit"),
    )
    await c.answer()

@router.callback_query(EditFlow.confirm, F.data.startswith("edit_confirm:"))
async def edit_confirm(c: CallbackQuery, state: FSMContext, bot: Bot):
    action = c.data.split(":")[1]
    data = await state.get_data()
    if action == "back":
        await state.set_state(EditFlow.count)
        title = neon_title('Сколько вариантов отредактировать за раз?')
        await c.message.answer(
            f"{title}\n\nВыберите число ниже 👇",
            parse_mode="Markdown",
            reply_markup=kb_count("edit_cnt"),
        )
        await c.answer()
        return
    img_bytes = data["edit_image_bytes"]
    prompt = data["edit_prompt"]
    n = data["edit_n"]
    progress_msg = await send_progress(c.message, "⚡️ *Генерация*\n\nПрогресс: *0/3*")
    await c.answer()
    try:
        await update_progress(bot, progress_msg.chat.id, progress_msg.message_id, "⚡️ *Генерация*\n\nПрогресс: *1/3*")
        images = await api_edit_images(init_image_bytes=img_bytes, prompt=prompt, n=n)
        await update_progress(bot, progress_msg.chat.id, progress_msg.message_id, "⚡️ *Генерация*\n\nПрогресс: *2/3*")
        last_sent_file_id: Optional[str] = None
        for idx, out_bytes in enumerate(images, start=1):
            file = BufferedInputFile(out_bytes, filename=f"akula_edit_{idx}.jpg")
            sent = await c.message.answer_photo(file)
            last_sent_file_id = sent.photo[-1].file_id if sent.photo else last_sent_file_id
        await update_progress(bot, progress_msg.chat.id, progress_msg.message_id, "⚡️ *Генерация*\n\nПрогресс: *3/3* ✅")
        await state.update_data(last_image_file_id=last_sent_file_id, last_mode="edit", last_edit_bytes=img_bytes, last_prompt=prompt, last_n=n)
        await c.message.answer(
            f"🛠 *Изображение отредактировано*\n\n"
            f"• 📝 *Промпт:* {escape_md(prompt)}\n\n"
            f"💡 *Что дальше?*\nВыберите действие кнопками ниже.",
            parse_mode="Markdown",
            reply_markup=kb_after_result("edit"),
        )
        await state.clear()
    except Exception as e:
        await c.message.answer(f"❌ Ошибка редактирования: `{e}`", parse_mode="Markdown")
        await state.clear()

@router.callback_query(F.data == "go:menu")
async def go_menu(c: CallbackQuery, state: FSMContext):
    await state.clear()
    await c.message.answer("🏠 Главное меню", reply_markup=kb_main_menu())
    await c.answer()

@router.callback_query(F.data == "go:new")
async def go_new(c: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(CreateFlow.prompt)
    title = neon_title('Опишите, что нужно сгенерировать')
    await c.message.answer(
        f"{title}\n\nОтправьте текст одним сообщением 💬",
        parse_mode="Markdown",
        reply_markup=kb_main_menu(),
    )
    await c.answer()

@router.callback_query(F.data == "go:edit_last")
async def go_edit_last(c: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    file_id = data.get("last_image_file_id")
    if not file_id:
        await c.answer("Нет последнего изображения для редактирования.", show_alert=True)
        return
    file = await bot.get_file(file_id)
    buf = await bot.download_file(file.file_path)
    img_bytes = buf.read()
    await state.clear()
    await state.set_state(EditFlow.prompt)
    await state.update_data(edit_image_bytes=img_bytes, edit_image_file_id=file_id)
    title = neon_title('Описание изменений')
    await c.message.answer(
        f"{title}\n\n"
        "Коротко сформулируйте правки ✍️\n\n"
        "*Пример:*\n"
        "Добавьте космический фон и летающих дельфинов 🌌🐬",
        parse_mode="Markdown",
    )
    await c.answer()

@router.callback_query(F.data == "create_after:regen")
async def create_regen(c: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    prompt = data.get("last_prompt")
    ratio = data.get("last_ratio")
    n = data.get("last_n")
    if not all([prompt, ratio, n]):
        await c.answer("Данные для перегенерации не найдены.", show_alert=True)
        return
    progress_msg = await send_progress(c.message, "⚡️ *Перегенерация*\n\nПрогресс: *0/3*")
    await c.answer()
    try:
        await update_progress(bot, progress_msg.chat.id, progress_msg.message_id, "⚡️ *Перегенерация*\n\nПрогресс: *1/3*")
        images = await api_image_generate(prompt=prompt, ratio=ratio, n=n)
        await update_progress(bot, progress_msg.chat.id, progress_msg.message_id, "⚡️ *Перегенерация*\n\nПрогресс: *2/3*")
        for idx, img_bytes in enumerate(images, start=1):
            file = BufferedInputFile(img_bytes, filename=f"akula_regen_{idx}.jpg")
            await c.message.answer_photo(file)
        await update_progress(bot, progress_msg.chat.id, progress_msg.message_id, "⚡️ *Перегенерация*\n\nПрогресс: *3/3* ✅")
        await c.message.answer(f"🔁 *Перегенерация завершена*\n\n💡 *Что дальше?*", parse_mode="Markdown", reply_markup=kb_after_result("create"))
    except Exception as e:
        await c.message.answer(f"❌ Ошибка: `{e}`", parse_mode="Markdown")

@router.callback_query(F.data == "edit_after:regen")
async def edit_regen(c: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    img_bytes = data.get("last_edit_bytes")
    prompt = data.get("last_prompt")
    n = data.get("last_n")
    if not all([img_bytes, prompt, n]):
        await c.answer("Данные для перегенерации не найдены.", show_alert=True)
        return
    progress_msg = await send_progress(c.message, "⚡️ *Перегенерация*\n\nПрогресс: *0/3*")
    await c.answer()
    try:
        await update_progress(bot, progress_msg.chat.id, progress_msg.message_id, "⚡️ *Перегенерация*\n\nПрогресс: *1/3*")
        images = await api_edit_images(init_image_bytes=img_bytes, prompt=prompt, n=n)
        await update_progress(bot, progress_msg.chat.id, progress_msg.message_id, "⚡️ *Перегенерация*\n\nПрогресс: *2/3*")
        for idx, out_bytes in enumerate(images, start=1):
            file = BufferedInputFile(out_bytes, filename=f"akula_regen_edit_{idx}.jpg")
            await c.message.answer_photo(file)
        await update_progress(bot, progress_msg.chat.id, progress_msg.message_id, "⚡️ *Перегенерация*\n\nПрогресс: *3/3* ✅")
        await c.message.answer(f"🔁 *Перегенерация завершена*\n\n💡 *Что дальше?*", parse_mode="Markdown", reply_markup=kb_after_result("edit"))
    except Exception as e:
        await c.message.answer(f"❌ Ошибка: `{e}`", parse_mode="Markdown")

async def main():
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())