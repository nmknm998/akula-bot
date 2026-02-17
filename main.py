import asyncio, base64, re
from io import BytesIO
from PIL import Image
import httpx

from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message, ReplyKeyboardMarkup, KeyboardButton,
    ReplyKeyboardRemove, BufferedInputFile,
    InlineKeyboardMarkup, InlineKeyboardButton
)

# ================== НАСТРОЙКИ ==================
BOT_TOKEN = "8482353260:AAExJIgniNYVuGp9TxrpbSAQRmBIblsg3aU"
API_BASE_URL = "https://voiceapi.csv666.ru"
API_KEY = "421191035:56566a724c66694c5353612f4e3643506a56414853673d3d"
API_TIMEOUT_SEC = 300
CHANNEL_USERNAME = "@ai_akulaa"

# ================== FSM ==================
class CreateFlow(StatesGroup):
    prompt = State()
    quantity = State()
    aspect = State()
    confirm = State()

class EditFlow(StatesGroup):
    image = State()
    prompt = State()
    quantity = State()
    confirm = State()

# ================== UI ==================
BTN_CREATE = KeyboardButton(text="✨ Создать")
BTN_EDIT = KeyboardButton(text="🎨 Редактировать")
BTN_BACK = KeyboardButton(text="⬅️ Назад")
BTN_CONFIRM = KeyboardButton(text="✅ Подтвердить")

MAIN_KB = ReplyKeyboardMarkup(
    keyboard=[[BTN_CREATE, BTN_EDIT]],
    resize_keyboard=True
)

ASPECTS = ["1:1", "16:9", "9:16"]

# ================== HELPERS ==================
def api_headers():
    return {"x-API-Key": API_KEY, "Content-Type": "application/json"}

async def api_call(endpoint, payload):
    async with httpx.AsyncClient(timeout=API_TIMEOUT_SEC) as client:
        r = await client.post(API_BASE_URL + endpoint, json=payload, headers=api_headers())
        r.raise_for_status()
        return r.json()

def decode_b64(b64):
    clean = re.sub(r"^data:image/.+;base64,", "", b64)
    return base64.b64decode(clean)

def compress_image(image_bytes: bytes) -> str:
    img = Image.open(BytesIO(image_bytes)).convert("RGB")
    img.thumbnail((1024, 1024))
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode()

async def check_subscription(bot: Bot, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(CHANNEL_USERNAME, user_id)
        return member.status in ("member", "administrator", "creator")
    except:
        return False

def sub_kb():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📢 Подписаться", url="https://t.me/ai_akulaa")],
            [InlineKeyboardButton(text="✅ Я подписался", callback_data="check_sub")]
        ]
    )

# ================== ROUTER ==================
router = Router()

# ---------- START ----------
@router.message(Command("start"))
async def start(message: Message, state: FSMContext, bot: Bot):
    await state.clear()
    if not await check_subscription(bot, message.from_user.id):
        await message.answer("Подпишись на канал 👇", reply_markup=sub_kb())
        return
    await message.answer("🦈 Akula Bot готов!", reply_markup=MAIN_KB)

@router.callback_query(F.data == "check_sub")
async def check_sub(cb, bot: Bot):
    if await check_subscription(bot, cb.from_user.id):
        await cb.message.delete()
        await cb.message.answer("🦈 Akula Bot готов!", reply_markup=MAIN_KB)
    else:
        await cb.answer("❌ Ты ещё не подписан", show_alert=True)

# ---------- СОЗДАНИЕ ----------
@router.message(F.text == "✨ Создать")
async def create_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("📝 Опиши изображение:", reply_markup=ReplyKeyboardMarkup(
        keyboard=[[BTN_BACK]], resize_keyboard=True
    ))
    await state.set_state(CreateFlow.prompt)

@router.message(CreateFlow.prompt)
async def create_prompt(message: Message, state: FSMContext):
    await state.update_data(prompt=message.text)
    await message.answer(
        "🔢 Сколько вариантов?",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text=str(i)) for i in range(1,5)], [BTN_BACK]],
            resize_keyboard=True
        )
)
    await state.set_state(CreateFlow.quantity)

@router.message(CreateFlow.quantity, F.text.isdigit())
async def create_qty(message: Message, state: FSMContext):
    await state.update_data(quantity=int(message.text))
    await message.answer(
        "📐 Соотношение сторон:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text=a) for a in ASPECTS], [BTN_BACK]],
            resize_keyboard=True
        )
    )
    await state.set_state(CreateFlow.aspect)

@router.message(CreateFlow.aspect)
async def create_confirm(message: Message, state: FSMContext):
    await state.update_data(aspect=message.text)
    data = await state.get_data()
    await message.answer(
        f"📝 {data['prompt']}\n🔢 {data['quantity']}\n📐 {data['aspect']}",
        reply_markup=ReplyKeyboardMarkup([[BTN_CONFIRM, BTN_BACK]], resize_keyboard=True)
    )
    await state.set_state(CreateFlow.confirm)

@router.message(CreateFlow.confirm, F.text == "✅ Подтвердить")
async def create_generate(message: Message, state: FSMContext):
    data = await state.get_data()
    await message.answer("⚡ Генерирую...", reply_markup=ReplyKeyboardRemove())

    for i in range(data["quantity"]):
        res = await api_call("/api/v1/image/create", {
            "prompt": data["prompt"],
            "aspect_ratio": data["aspect"],
            "n": 1
        })
        b = decode_b64(res["image_b64"][0])
        await message.answer_photo(
            BufferedInputFile(b, f"img_{i+1}.png"),
            caption=f"🖼 Вариант {i+1}"
        )
        await asyncio.sleep(0.5)

    await state.clear()
    await message.answer("✅ Готово", reply_markup=MAIN_KB)

# ---------- РЕДАКТИРОВАНИЕ ----------
@router.message(F.text == "🎨 Редактировать")
async def edit_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("📷 Отправь фото", reply_markup=ReplyKeyboardMarkup(
        keyboard=[[BTN_BACK]], resize_keyboard=True
    ))
    await state.set_state(EditFlow.image)

@router.message(EditFlow.image, F.photo)
async def edit_photo(message: Message, state: FSMContext, bot: Bot):
    file = await bot.get_file(message.photo[-1].file_id)
    bio = BytesIO()
    await bot.download_file(file.file_path, bio)
    await state.update_data(image=compress_image(bio.getvalue()))
    await message.answer("📝 Что изменить?")
    await state.set_state(EditFlow.prompt)

@router.message(EditFlow.prompt)
async def edit_prompt(message: Message, state: FSMContext):
    await state.update_data(prompt=message.text)
    await message.answer(
        "🔢 Сколько вариантов?",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text=str(i)) for i in range(1,5)], [BTN_BACK]],
            resize_keyboard=True
        )
    )
    await state.set_state(EditFlow.quantity)

@router.message(EditFlow.quantity, F.text.isdigit())
async def edit_confirm(message: Message, state: FSMContext):
    await state.update_data(quantity=int(message.text))
    await message.answer("Запускаю?", reply_markup=ReplyKeyboardMarkup(
        keyboard=[[BTN_CONFIRM, BTN_BACK]], resize_keyboard=True
    ))
    await state.set_state(EditFlow.confirm)

@router.message(EditFlow.confirm, F.text == "✅ Подтвердить")
async def edit_generate(message: Message, state: FSMContext):
    data = await state.get_data()
    await message.answer("⚡ Редактирую...", reply_markup=ReplyKeyboardRemove())

    for i in range(data["quantity"]):
        res = await api_call("/api/v1/image/edit", {
            "reference_image_b64": data["image"],
            "prompt": data["prompt"],
            "aspect_ratio": "1:1",
            "n": 1
        })
        b = decode_b64(res["image_b64"][0])
        await message.answer_photo(
            BufferedInputFile(b, f"edit_{i+1}.png"),
            caption=f"🎨 Вариант {i+1}"
        )
        await asyncio.sleep(0.5)

    await state.clear()
    await message.answer("✅ Готово", reply_markup=MAIN_KB)

# ================== RUN ==================
async def main():
    bot = Bot(BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    await dp.start_polling(bot)

if name == "__main__":
    asyncio.run(main())


