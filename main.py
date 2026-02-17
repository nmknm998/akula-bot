import os, asyncio, base64, re, httpx
from io import BytesIO
from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, BufferedInputFile

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
API_BASE_URL = os.getenv("API_BASE_URL", "https://voiceapi.csv666.ru")
API_KEY = os.getenv("API_KEY", "")
API_TIMEOUT_SEC = 300  # Увеличили время ожидания до 5 минут для редактора

class CreateFlow(StatesGroup):
    main_menu = State(); input_prompt = State(); select_quantity = State(); select_aspect_ratio = State(); confirm = State()
class EditFlow(StatesGroup):
    input_image = State(); input_prompt = State(); select_quantity = State(); confirm = State()

ASPECT_RATIOS = ["16:9", "9:16", "3:2", "2:3", "4:3", "3:4", "1:1"]
BTN_CREATE = KeyboardButton(text="✨ Создать"); BTN_EDIT = KeyboardButton(text="🎨 Редактировать")
BTN_BACK = KeyboardButton(text="⬅️ Назад"); BTN_CONFIRM = KeyboardButton(text="✅ Подтвердить")

def _api_headers(): return {"x-API-Key": API_KEY, "Content-Type": "application/json"}

def decode_b64_image(b64_str):
    if not b64_str or not isinstance(b64_str, str): return None
    clean_str = re.sub(r'^data:image/.+;base64,', '', b64_str.strip())
    missing_padding = len(clean_str) % 4
    if missing_padding: clean_str += '=' * (4 - missing_padding)
    try: return base64.b64decode(clean_str)
    except: return None

async def api_call(endpoint, payload):
    async with httpx.AsyncClient(timeout=API_TIMEOUT_SEC) as client:
        resp = await client.post(f"{API_BASE_URL}{endpoint}", json=payload, headers=_api_headers())
        resp.raise_for_status()
        return resp.json()

router = Router()

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    kb = ReplyKeyboardMarkup(keyboard=[[BTN_CREATE, BTN_EDIT]], resize_keyboard=True)
    await message.answer("🦈 <b>Akula Bot готов!</b>\n\nВыбери действие:", parse_mode="HTML", reply_markup=kb)
    await state.set_state(CreateFlow.main_menu)

@router.message(F.text == "⬅️ Назад")
async def back_btn(message: Message, state: FSMContext): await cmd_start(message, state)

# --- БЛОК СОЗДАНИЯ ---
@router.message(CreateFlow.main_menu, F.text == "✨ Создать")
async def start_create(message: Message, state: FSMContext):
    await message.answer("📝 Опиши картинку:", reply_markup=ReplyKeyboardMarkup(keyboard=[[BTN_BACK]], resize_keyboard=True))
    await state.set_state(CreateFlow.input_prompt)

@router.message(CreateFlow.input_prompt)
async def got_prompt(message: Message, state: FSMContext):
    await state.update_data(prompt=message.text)
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="1"), KeyboardButton(text="2")], [BTN_BACK]], resize_keyboard=True)
    await message.answer("🔢 Сколько вариантов?", reply_markup=kb)
    await state.set_state(CreateFlow.select_quantity)

@router.message(CreateFlow.select_quantity, F.text.isdigit())
async def got_qty(message: Message, state: FSMContext):
    await state.update_data(quantity=int(message.text))
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="16:9"), KeyboardButton(text="1:1")], [BTN_BACK]], resize_keyboard=True)
    await message.answer("📐 Формат:", reply_markup=kb)
    await state.set_state(CreateFlow.select_aspect_ratio)

@router.message(CreateFlow.select_aspect_ratio, F.text.in_(ASPECT_RATIOS))
async def got_aspect(message: Message, state: FSMContext):
    await state.update_data(aspect_ratio=message.text)
    data = await state.get_data()
    kb = ReplyKeyboardMarkup(keyboard=[[BTN_CONFIRM, BTN_BACK]], resize_keyboard=True)
    await message.answer(f"🔍 <b>Параметры:</b>\n{data['prompt']}\nФормат: {data['aspect_ratio']}\nКол-во: {data['quantity']}", parse_mode="HTML", reply_markup=kb)
    await state.set_state(CreateFlow.confirm)

@router.message(CreateFlow.confirm, F.text == "✅ Подтвердить")
async def create_confirmed(message: Message, state: FSMContext):
    data = await state.get_data()
    await message.answer("⚡ Генерирую...", reply_markup=ReplyKeyboardRemove())
    try:
        res = await api_call("/api/v1/image/create", {"prompt": data["prompt"], "aspect_ratio": data["aspect_ratio"], "n": data["quantity"]})
        imgs = res.get("image_b64", [])
        if isinstance(imgs, str): imgs = [imgs]
        for idx, img in enumerate(imgs, 1):
            b = decode_b64_image(img)
            if b: await message.answer_photo(BufferedInputFile(b, filename=f"c_{idx}.png"))
        await message.answer("✅ Готово!", reply_markup=kb_main_kb())
    except Exception as e: await message.answer(f"❌ Ошибка: {str(e)}", reply_markup=kb_main_kb())
    await state.set_state(CreateFlow.main_menu)

# --- БЛОК РЕДАКТИРОВАНИЯ ---
@router.message(CreateFlow.main_menu, F.text == "🎨 Редактировать")
async def start_edit(message: Message, state: FSMContext):
    await message.answer("📷 Отправь фото для изменения:", reply_markup=ReplyKeyboardMarkup(keyboard=[[BTN_BACK]], resize_keyboard=True))
    await state.set_state(EditFlow.input_image)

@router.message(EditFlow.input_image, F.photo)
async def edit_got_photo(message: Message, state: FSMContext, bot: Bot):
    file = await bot.get_file(message.photo[-1].file_id)
    bio = BytesIO()
    await bot.download_file(file.file_path, bio)
    b64 = base64.b64encode(bio.getvalue()).decode("utf-8")
    await state.update_data(image_b64=b64)
    await message.answer("📝 Что нужно изменить на фото?", reply_markup=ReplyKeyboardMarkup(keyboard=[[BTN_BACK]], resize_keyboard=True))
    await state.set_state(EditFlow.input_prompt)

@router.message(EditFlow.input_prompt)
async def edit_got_prompt(message: Message, state: FSMContext):
    await state.update_data(prompt=message.text)
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="1"), KeyboardButton(text="2")], [BTN_BACK]], resize_keyboard=True)
    await message.answer("🔢 Сколько вариантов?", reply_markup=kb)
    await state.set_state(EditFlow.select_quantity)

@router.message(EditFlow.select_quantity, F.text.isdigit())
async def edit_got_qty(message: Message, state: FSMContext):
    await state.update_data(quantity=int(message.text))
    data = await state.get_data()
    kb = ReplyKeyboardMarkup(keyboard=[[BTN_CONFIRM, BTN_BACK]], resize_keyboard=True)
    await message.answer(f"🔍 <b>Редактирование:</b>\n{data['prompt']}\nКол-во: {data['quantity']}", parse_mode="HTML", reply_markup=kb)
    await state.set_state(EditFlow.confirm)

@router.message(EditFlow.confirm, F.text == "✅ Подтвердить")
async def edit_confirmed(message: Message, state: FSMContext):
    data = await state.get_data()
    await message.answer("⚡ Обрабатываю фото (это может занять до 1 минуты)...", reply_markup=ReplyKeyboardRemove())
    try:
        res = await api_call("/api/v1/image/edit", {
            "image": data["image_b64"],
            "prompt": data["prompt"],
            "aspect_ratio": "1:1",
            "n": data["quantity"]
        })
        imgs = res.get("image_b64", [])
        if isinstance(imgs, str): imgs = [imgs]
        for idx, img in enumerate(imgs, 1):
            b = decode_b64_image(img)
            if b: await message.answer_photo(BufferedInputFile(b, filename=f"e_{idx}.png"))
        await message.answer("✅ Готово!", reply_markup=kb_main_kb())
    except Exception as e: await message.answer(f"❌ Ошибка: {str(e)}", reply_markup=kb_main_kb())
    await state.set_state(CreateFlow.main_menu)

def kb_main_kb(): return ReplyKeyboardMarkup(keyboard=[[BTN_CREATE, BTN_EDIT]], resize_keyboard=True)

async def main():
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage()); dp.include_router(router)
    await dp.start_polling(bot)

if __name__ == "__main__": asyncio.run(main())
