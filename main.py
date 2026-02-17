import os
import asyncio
import base64
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
    """Вызов POST /api/v1/image/create"""
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

async def api_edit_image(
    image_b64: str, prompt: str, aspect_ratio: str, quantity: int
) -> dict:
    """Вызов POST /api/v1/image/edit"""
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
    """Декодирует base64 строку в байты изображения"""
    return base64.b64decode(b64_str)

async def download_telegram_photo(bot: Bot, file_id: str) -> bytes:
    """Скачивает фото из Telegram и возвращает байты"""
    file = await bot.get_file(file_id)
    bio = BytesIO()
    await bot.download_file(file.file_path, bio)
    return bio.getvalue()

def encode_image_to_b64(image_bytes: bytes) -> str:
    """Кодирует байты изображения в base64 строку"""
    return base64.b64encode(image_bytes).decode("utf-8")

# ============================================================================
# КЛАВИАТУРЫ
# ============================================================================
def kb_main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[BTN_CREATE, BTN_EDIT]],
        resize_keyboard=True,
    )

def kb_quantity() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="1"), KeyboardButton(text="2")],
            [KeyboardButton(text="3"), KeyboardButton(text="4")],
            [BTN_BACK],
        ],
        resize_keyboard=True,
    )

def kb_aspect_ratio() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="16:9"), KeyboardButton(text="9:16"), KeyboardButton(text="3:2")],
            [KeyboardButton(text="2:3"), KeyboardButton(text="4:3"), KeyboardButton(text="3:4")],
            [KeyboardButton(text="1:1"), BTN_BACK],
        ],
        resize_keyboard=True,
    )

def kb_confirm() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[BTN_CONFIRM, BTN_BACK]],
        resize_keyboard=True,
    )

# ============================================================================
# РОУТЕР
# ============================================================================
router = Router()

# ============================================================================
# КОМАНДА /start
# ============================================================================
@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "🦈 <b>Добро пожаловать в Akula Bot!</b>\n\n"
        "Я помогу тебе создавать и редактировать изображения с помощью ИИ.\n\n"
        "✨ <b>Создать</b> — генерация новой картинки по описанию\n"
        "🎨 <b>Редактировать</b> — изменение загруженного изображения\n\n"
        "Выбери действие:",
        parse_mode="HTML",
        reply_markup=kb_main_menu(),
    )
    await state.set_state(CreateFlow.main_menu)

# ============================================================================
# ГЛАВНОЕ МЕНЮ
# ============================================================================
@router.message(CreateFlow.main_menu, F.text == "✨ Создать")
async def start_create(message: Message, state: FSMContext):
    await message.answer(
        "📝 Опиши, что ты хочешь увидеть на картинке:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[BTN_BACK]],
            resize_keyboard=True,
        ),
    )
    await state.set_state(CreateFlow.input_prompt)

@router.message(CreateFlow.main_menu, F.text == "🎨 Редактировать")
async def start_edit(message: Message, state: FSMContext):
    await message.answer(
        "📷 Отправь мне изображение, которое хочешь отредактировать:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[BTN_BACK]],
            resize_keyboard=True,
        ),
    )
    await state.set_state(EditFlow.input_image)

# ============================================================================
# СОЗДАНИЕ (CREATE FLOW)
# ============================================================================
@router.message(CreateFlow.input_prompt, F.text == "⬅️ Назад")
async def create_back_to_menu(message: Message, state: FSMContext):
    await cmd_start(message, state)

@router.message(CreateFlow.input_prompt)
async def create_got_prompt(message: Message, state: FSMContext):
    await state.update_data(prompt=message.text)
    await message.answer(
        "🔢 Сколько вариантов сгенерировать? (1-4)",
        reply_markup=kb_quantity(),
    )
    await state.set_state(CreateFlow.select_quantity)

@router.message(CreateFlow.select_quantity, F.text == "⬅️ Назад")
async def create_quantity_back(message: Message, state: FSMContext):
    await message.answer(
        "📝 Опиши, что ты хочешь увидеть на картинке:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[BTN_BACK]],
            resize_keyboard=True,
        ),
    )
    await state.set_state(CreateFlow.input_prompt)

@router.message(CreateFlow.select_quantity)
async def create_got_quantity(message: Message, state: FSMContext):
    if not message.text.isdigit() or int(message.text) not in [1, 2, 3, 4]:
        await message.answer("Пожалуйста, выбери число от 1 до 4.")
        return
    await state.update_data(quantity=int(message.text))
    await message.answer(
        "📐 Выбери соотношение сторон:",
        reply_markup=kb_aspect_ratio(),
    )
    await state.set_state(CreateFlow.select_aspect_ratio)

@router.message(CreateFlow.select_aspect_ratio, F.text == "⬅️ Назад")
async def create_aspect_back(message: Message, state: FSMContext):
    await message.answer(
        "🔢 Сколько вариантов сгенерировать? (1-4)",
        reply_markup=kb_quantity(),
    )
    await state.set_state(CreateFlow.select_quantity)

@router.message(CreateFlow.select_aspect_ratio)
async def create_got_aspect(message: Message, state: FSMContext):
    if message.text not in ASPECT_RATIOS:
        await message.answer(
            "Пожалуйста, выбери соотношение сторон из предложенных кнопок."
        )
        return
    await state.update_data(aspect_ratio=message.text)
    
    data = await state.get_data()
    await message.answer(
        "🔍 <b>Проверим параметры</b>\n\n"
        f"📝 <b>Промпт:</b> {data['prompt']}\n"
        f"📐 <b>Соотношение сторон:</b> {data['aspect_ratio']}\n"
        f"🔢 <b>Вариантов:</b> {data['quantity']}\n\n"
        "Запускаем генерацию? ⚡",
        parse_mode="HTML",
        reply_markup=kb_confirm(),
    )
    await state.set_state(CreateFlow.confirm)

@router.message(CreateFlow.confirm, F.text == "⬅️ Назад")
async def create_confirm_back(message: Message, state: FSMContext):
    await message.answer(
        "📐 Выбери соотношение сторон:",
        reply_markup=kb_aspect_ratio(),
    )
    await state.set_state(CreateFlow.select_aspect_ratio)

@router.message(CreateFlow.confirm, F.text == "✅ Подтвердить")
async def create_confirmed(message: Message, state: FSMContext):
    data = await state.get_data()
    prompt = data["prompt"]
    aspect_ratio = data["aspect_ratio"]
    quantity = data["quantity"]
    
    await message.answer(
        f"⚡ <b>Генерация</b>\n\nПрогресс: 1/{quantity}",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardRemove(),
    )
    await state.set_state(CreateFlow.generating)
    
    try:
        result = await api_create_image(prompt, aspect_ratio, quantity)
        images_b64 = result.get("image_b64", [])
        
        if not images_b64:
            await message.answer(
                "❌ Ошибка: API не вернуло изображения.",
                reply_markup=kb_main_menu(),
            )
            await state.set_state(CreateFlow.main_menu)
            return
        
        for idx, img_b64 in enumerate(images_b64, start=1):
            img_bytes = decode_b64_image(img_b64)
            input_file = BufferedInputFile(img_bytes, filename=f"image_{idx}.png")
            await message.answer_photo(input_file)
            if idx < len(images_b64):
                await message.answer(f"Прогресс: {idx + 1}/{quantity}")
        
        await message.answer(
            "✅ Готово! Выбери следующее действие:",
            reply_markup=kb_main_menu(),
        )
        await state.set_state(CreateFlow.main_menu)
        
    except httpx.HTTPStatusError as e:
        error_text = e.response.text
        await message.answer(
            f"❌ Ошибка генерации: API ошибка {e.response.status_code}: {error_text}",
            reply_markup=kb_main_menu(),
        )
        await state.set_state(CreateFlow.main_menu)
    except Exception as e:
        await message.answer(
            f"❌ Ошибка генерации: {str(e)}",
            reply_markup=kb_main_menu(),
        )
        await state.set_state(CreateFlow.main_menu)

# ============================================================================
# РЕДАКТИРОВАНИЕ (EDIT FLOW)
# ============================================================================
@router.message(EditFlow.input_image, F.text == "⬅️ Назад")
async def edit_back_to_menu(message: Message, state: FSMContext):
    await cmd_start(message, state)

@router.message(EditFlow.input_image, F.photo)
async def edit_got_image(message: Message, state: FSMContext, bot: Bot):
    photo = message.photo[-1]
    image_bytes = await download_telegram_photo(bot, photo.file_id)
    image_b64 = encode_image_to_b64(image_bytes)
    await state.update_data(image_b64=image_b64)
    
    await message.answer(
        "📝 Опиши, как изменить изображение:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[BTN_BACK]],
            resize_keyboard=True,
        ),
    )
    await state.set_state(EditFlow.input_prompt)

@router.message(EditFlow.input_prompt, F.text == "⬅️ Назад")
async def edit_prompt_back(message: Message, state: FSMContext):
    await message.answer(
        "📷 Отправь мне изображение, которое хочешь отредактировать:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[BTN_BACK]],
            resize_keyboard=True,
        ),
    )
    await state.set_state(EditFlow.input_image)

@router.message(EditFlow.input_prompt)
async def edit_got_prompt(message: Message, state: FSMContext):
    await state.update_data(prompt=message.text)
    await message.answer(
        "🔢 Сколько вариантов сгенерировать? (1-4)",
        reply_markup=kb_quantity(),
    )
    await state.set_state(EditFlow.select_quantity)

@router.message(EditFlow.select_quantity, F.text == "⬅️ Назад")
async def edit_quantity_back(message: Message, state: FSMContext):
    await message.answer(
        "📝 Опиши, как изменить изображение:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[BTN_BACK]],
            resize_keyboard=True,
        ),
    )
    await state.set_state(EditFlow.input_prompt)

@router.message(EditFlow.select_quantity)
async def edit_got_quantity(message: Message, state: FSMContext):
    if not message.text.isdigit() or int(message.text) not in [1, 2, 3, 4]:
        await message.answer("Пожалуйста, выбери число от 1 до 4.")
        return
    await state.update_data(quantity=int(message.text))
    
    data = await state.get_data()
    # Для редактирования используем соотношение 1:1 по умолчанию
    aspect_ratio = "1:1"
    await state.update_data(aspect_ratio=aspect_ratio)
    
    await message.answer(
        "🔍 <b>Проверим параметры</b>\n\n"
        f"📝 <b>Промпт:</b> {data['prompt']}\n"
        f"🔢 <b>Вариантов:</b> {data['quantity']}\n\n"
        "Запускаем генерацию? ⚡",
        parse_mode="HTML",
        reply_markup=kb_confirm(),
    )
    await state.set_state(EditFlow.confirm)

@router.message(EditFlow.confirm, F.text == "⬅️ Назад")
async def edit_confirm_back(message: Message, state: FSMContext):
    await message.answer(
        "🔢 Сколько вариантов сгенерировать? (1-4)",
        reply_markup=kb_quantity(),
    )
    await state.set_state(EditFlow.select_quantity)

@router.message(EditFlow.confirm, F.text == "✅ Подтвердить")
async def edit_confirmed(message: Message, state: FSMContext):
    data = await state.get_data()
    image_b64 = data["image_b64"]
    prompt = data["prompt"]
    aspect_ratio = data["aspect_ratio"]
    quantity = data["quantity"]
    
    await message.answer(
        f"⚡ <b>Генерация</b>\n\nПрогресс: 1/{quantity}",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardRemove(),
    )
    await state.set_state(EditFlow.generating)
    
    try:
        result = await api_edit_image(image_b64, prompt, aspect_ratio, quantity)
        images_b64 = result.get("image_b64", [])
        
        if not images_b64:
            await message.answer(
                "❌ Ошибка: API не вернуло изображения.",
                reply_markup=kb_main_menu(),
            )
            await state.set_state(CreateFlow.main_menu)
            return
        
        for idx, img_b64 in enumerate(images_b64, start=1):
            img_bytes = decode_b64_image(img_b64)
            input_file = BufferedInputFile(img_bytes, filename=f"edited_{idx}.png")
            await message.answer_photo(input_file)
            if idx < len(images_b64):
                await message.answer(f"Прогресс: {idx + 1}/{quantity}")
        
        await message.answer(
            "✅ Готово! Выбери следующее действие:",
            reply_markup=kb_main_menu(),
        )
        await state.set_state(CreateFlow.main_menu)
        
    except httpx.HTTPStatusError as e:
        error_text = e.response.text
        await message.answer(
            f"❌ Ошибка генерации: API ошибка {e.response.status_code}: {error_text}",
            reply_markup=kb_main_menu(),
        )
        await state.set_state(CreateFlow.main_menu)
    except Exception as e:
        await message.answer(
            f"❌ Ошибка генерации: {str(e)}",
            reply_markup=kb_main_menu(),
        )
        await state.set_state(CreateFlow.main_menu)

# ============================================================================
# ЗАПУСК БОТА
# ============================================================================
async def main():
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    
    print("🦈 Akula Bot запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
