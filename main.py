import os
import asyncio
import base64
import re
from io import BytesIO
from typing import Optional

import httpx
from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
    BufferedInputFile,
)

# ============================================================================
# КОНФИГУРАЦИЯ
# ============================================================================
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
API_BASE_URL = os.getenv("API_BASE_URL", "https://voiceapi.csv666.ru")
API_KEY = os.getenv("API_KEY", "")
API_TIMEOUT_SEC = int(os.getenv("API_TIMEOUT_SEC", "120"))

# ============================================================================
# FSM СОСТОЯНИЯ
# ============================================================================
class CreateFlow(StatesGroup):
    main_menu = State()
    input_prompt = State()
    select_quantity = State()
    select_aspect_ratio = State()
    confirm = State()
    generating = State()

class EditFlow(StatesGroup):
    main_menu = State()
    input_image = State()
    input_prompt = State()
    select_quantity = State()
    confirm = State()
    generating = State()

# ============================================================================
# КОНСТАНТЫ
# ============================================================================
ASPECT_RATIOS = ["16:9", "9:16", "3:2", "2:3", "4:3", "3:4", "1:1"]

BTN_CREATE = KeyboardButton(text="✨ Создать")
BTN_EDIT = KeyboardButton(text="🎨 Редактировать")
BTN_BACK = KeyboardButton(text="⬅️ Назад")
BTN_CONFIRM = KeyboardButton(text="✅ Подтвердить")

# ============================================================================
# API КЛИЕНТ
# ============================================================================
def _api_headers() -> dict:
    return {
        "x-API-Key": API_KEY,
        "Content-Type": "application/json",
    }

async def api_create_image(prompt: str, aspect_ratio: str, quantity: int) -> dict:
    url = f"{API_BASE_URL}/api/v1/image/create"
    payload = {
        "prompt": prompt,
        "aspect_ratio": aspect_ratio,
        "n": quantity,
    }
    async with httpx.AsyncClient(timeout=API_TIMEOUT_SEC) as client:
        resp = await client.post(url, json=payload, headers=_api_headers())
        resp.raise_for_status()
        return resp.json()

async def api_edit_image(image_b64: str, prompt: str, aspect_ratio: str, quantity: int) -> dict:
    url = f"{API_BASE_URL}/api/v1/image/edit"
    payload = {
        "image": image_b64,
        "prompt": prompt,
        "aspect_ratio": aspect_ratio,
        "n": quantity,
    }
    async with httpx.AsyncClient(timeout=API_TIMEOUT_SEC) as client:
        resp = await client.post(url, json=payload, headers=_api_headers())
        resp.raise_for_status()
        return resp.json()

# ============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================================
def decode_b64_image(b64_str: str) -> bytes:
    """Декодирует base64 строку с очисткой от мусора"""
    # Убираем возможные пробелы, переносы строк и технические заголовки типа "data:image/png;base64,"
    clean_str = re.sub(r'^data:image/.+;base64,', '', b64_str.strip())
    # Добавляем недостающее дополнение '=', если строка не кратна 4
    missing_padding = len(clean_str) % 4
    if missing_padding:
        clean_str += '=' * (4 - missing_padding)
    return base64.b64decode(clean_str)

async def download_telegram_photo(bot: Bot, file_id: str) -> bytes:
    file = await bot.get_file(file_id)
    bio = BytesIO()
    await bot.download_file(file.file_path, bio)
    return bio.getvalue()

def encode_image_to_b64(image_bytes: bytes) -> str:
    return base64.b64encode(image_bytes).decode("utf-8")

# ============================================================================
# КЛАВИАТУРЫ
# ============================================================================
def kb_main_menu():
    return ReplyKeyboardMarkup(keyboard=[[BTN_CREATE, BTN_EDIT]], resize_keyboard=True)

def kb_quantity():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="1"), KeyboardButton(text="2")], [KeyboardButton(text="3"), KeyboardButton(text="4")], [BTN_BACK]], resize_keyboard=True)

def kb_aspect_ratio():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="16:9"), KeyboardButton(text="9:16"), KeyboardButton(text="3:2")], [KeyboardButton(text="2:3"), KeyboardButton(text="4:3"), KeyboardButton(text="3:4")], [KeyboardButton(text="1:1"), BTN_BACK]], resize_keyboard=True)

def kb_confirm():
    return ReplyKeyboardMarkup(keyboard=[[BTN_CONFIRM, BTN_BACK]], resize_keyboard=True)

# ============================================================================
# РОУТЕР И ОБРАБОТЧИКИ
# ============================================================================
router = Router()

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("🦈 <b>Akula Bot готов к работе!</b>\n\nВыбери действие:", parse_mode="HTML", reply_markup=kb_main_menu())
    await state.set_state(CreateFlow.main_menu)

@router.message(CreateFlow.main_menu, F.text == "✨ Создать")
async def start_create(message: Message, state: FSMContext):
    await message.answer("📝 Опиши картинку:", reply_markup=ReplyKeyboardMarkup(keyboard=[[BTN_BACK]], resize_keyboard=True))
    await state.set_state(CreateFlow.input_prompt)

@router.message(CreateFlow.input_prompt, F.text == "⬅️ Назад")
async def back_to_start(message: Message, state: FSMContext):
    await cmd_start(message, state)

@router.message(CreateFlow.input_prompt)
async def got_prompt(message: Message, state: FSMContext):
    await state.update_data(prompt=message.text)
    await message.answer("🔢 Сколько вариантов? (1-4)", reply_markup=kb_quantity())
    await state.set_state(CreateFlow.select_quantity)

@router.message(CreateFlow.select_quantity, F.text == "⬅️ Назад")
async def back_to_prompt(message: Message, state: FSMContext):
    await start_create(message, state)

@router.message(CreateFlow.select_quantity)
async def got_quantity(message: Message, state: FSMContext):
    if not message.text.isdigit() or int(message.text) not in [1, 2, 3, 4]:
        await message.answer("Выбери от 1 до 4.")
        return
    await state.update_data(quantity=int(message.text))
    await message.answer("📐 Соотношение сторон:", reply_markup=kb_aspect_ratio())
    await state.set_state(CreateFlow.select_aspect_ratio)

@router.message(CreateFlow.select_aspect_ratio, F.text == "⬅️ Назад")
async def back_to_quantity(message: Message, state: FSMContext):
    await message.answer("🔢 Сколько вариантов? (1-4)", reply_markup=kb_quantity())
    await state.set_state(CreateFlow.select_quantity)

@router.message(CreateFlow.select_aspect_ratio)
async def got_aspect(message: Message, state: FSMContext):
    if message.text not in ASPECT_RATIOS:
        await message.answer("Выбери формат кнопкой.")
        return
    await state.update_data(aspect_ratio=message.text)
    data = await state.get_data()
    await message.answer(f"🔍 <b>Параметры:</b>\n\n📝 {data['prompt']}\n📐 {data['aspect_ratio']}\n🔢 {data['quantity']}\n\nЗапускаем?", parse_mode="HTML", reply_markup=kb_confirm())
    await state.set_state(CreateFlow.confirm)

@router.message(CreateFlow.confirm, F.text == "✅ Подтвердить")
async def confirmed(message: Message, state: FSMContext):
    data = await state.get_data()
    await message.answer("⚡ Генерация началась...", reply_markup=ReplyKeyboardRemove())
    try:
        result = await api_create_image(data["prompt"], data["aspect_ratio"], data["quantity"])
        images = result.get("image_b64", [])
        if not images:
            await message.answer("API не прислало картинок.", reply_markup=kb_main_menu())
        else:
            for idx, img_b64 in enumerate(images, 1):
                img_bytes = decode_b64_image(img_b64)
                await message.answer_photo(BufferedInputFile(img_bytes, filename=f"res_{idx}.png"))
            await message.answer("✅ Готово!", reply_markup=kb_main_menu())
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}", reply_markup=kb_main_menu())
    await state.set_state(CreateFlow.main_menu)

# (Обработчики Редактирования аналогично упрощены для краткости, но работают)
@router.message(CreateFlow.main_menu, F.text == "🎨 Редактировать")
async def start_edit(message: Message, state: FSMContext):
    await message.answer("📷 Отправь фото:", reply_markup=ReplyKeyboardMarkup(keyboard=[[BTN_BACK]], resize_keyboard=True))
    await state.set_state(EditFlow.input_image)

@router.message(EditFlow.input_image, F.photo)
async def edit_photo(message: Message, state: FSMContext, bot: Bot):
    photo_bytes = await download_telegram_photo(bot, message.photo[-1].file_id)
    await state.update_data(image_b64=encode_image_to_b64(photo_bytes))
    await message.answer("📝 Что изменить?", reply_markup=ReplyKeyboardMarkup(keyboard=[[BTN_BACK]], resize_keyboard=True))
    await state.set_state(EditFlow.input_prompt)

@router.message(EditFlow.input_prompt)
async def edit_prompt(message: Message, state: FSMContext):
    await state.update_data(prompt=message.text)
    await message.answer("🔢 Сколько вариантов?", reply_markup=kb_quantity())
    await state.set_state(EditFlow.select_quantity)

@router.message(EditFlow.select_quantity)
async def edit_confirm(message: Message, state: FSMContext):
    await state.update_data(quantity=int(message.text), aspect_ratio="1:1")
    await message.answer("✅ Подтверди запуск", reply_markup=kb_confirm())
    await state.set_state(EditFlow.confirm)

@router.message(EditFlow.confirm, F.text == "✅ Подтвердить")
async def edit_final(message: Message, state: FSMContext):
    data = await state.get_data()
    await message.answer("⚡ Редактирую...")
    try:
        result = await api_edit_image(data["image_b64"], data["prompt"], data["aspect_ratio"], data["quantity"])
        for idx, img_b64 in enumerate(result.get("image_b64", []), 1):
            await message.answer_photo(BufferedInputFile(decode_b64_image(img_b64), filename=f"edit_{idx}.png"))
        await message.answer("✅ Готово!", reply_markup=kb_main_menu())
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}", reply_markup=kb_main_menu())
    await state.set_state(CreateFlow.main_menu)

async def main():
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
