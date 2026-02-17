import os, asyncio, base64, re, httpx
from io import BytesIO
from PIL import Image
from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton

# ТВОИ ДАННЫЕ (УЖЕ ВПИСАНЫ)
BOT_TOKEN = "8482353260:AAExJIgniNYVuGp9Tx0pbSAQRmBIblsg3aU"
API_BASE_URL = "https://voiceapi.csv666.ru"
API_KEY = "421191035:56566a724c66694c5353612f4e3643506a56414853673d3d"
API_TIMEOUT_SEC = 300
CHANNEL_USERNAME = "@ai_akulaa"

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

def compress_image(image_bytes: bytes) -> str:
    img = Image.open(BytesIO(image_bytes))
    if img.mode in ('RGBA', 'LA', 'P'):
        background = Image.new('RGB', img.size, (255, 255, 255))
        if img.mode == 'P': img = img.convert('RGBA')
        background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
        img = background
    max_dimension = 1024
    if max(img.size) > max_dimension:
        img.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
    output = BytesIO()
    img.save(output, format='JPEG', quality=85, optimize=True)
    return base64.b64encode(output.getvalue()).decode('utf-8')

async def api_call(endpoint, payload):
    async with httpx.AsyncClient(timeout=API_TIMEOUT_SEC) as client:
        resp = await client.post(f"{API_BASE_URL}{endpoint}", json=payload, headers=_api_headers())
        resp.raise_for_status()
        return resp.json()

async def check_subscription(bot: Bot, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=user_id)
        return member.status in ["member", "administrator", "creator"]
    except: return False

def kb_subscribe():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📢 Подписаться на канал", url="https://t.me/ai_akulaa")], [InlineKeyboardButton(text="✅ Я подписался", callback_data="check_sub")]])

router = Router()

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext, bot: Bot):
    if not await check_subscription(bot, message.from_user.id):
        await message.answer("🦈 <b>Akula Bot</b>\n\n⚠️ Для использования бота подпишись на наш канал:", parse_mode="HTML", reply_markup=kb_subscribe())
        return
    await state.clear()
    kb = ReplyKeyboardMarkup(keyboard=[[BTN_CREATE, BTN_EDIT]], resize_keyboard=True)
    await message.answer("🦈 <b>Akula Bot готов!</b>\n\nВыбери действие:", parse_mode="HTML", reply_markup=kb)
    await state.set_state(CreateFlow.main_menu)

@router.callback_query(F.data == "check_sub")
async def check_sub_callback(callback, bot: Bot, state: FSMContext):
    if not await check_subscription(bot, callback.from_user.id):
        await callback.answer("❌ Ты ещё не подписан!", show_alert=True)
        return
    await callback.message.delete()
    kb = ReplyKeyboardMarkup(keyboard=[[BTN_CREATE, BTN_EDIT]], resize_keyboard=True)
    await callback.message.answer("🦈 <b>Akula Bot готов!</b>\n\nВыбери действие:", parse_mode="HTML", reply_markup=kb)
    await state.set_state(CreateFlow.main_menu)

@router.message(F.text == "⬅️ Назад")
async def back_btn(message: Message, state: FSMContext, bot: Bot): 
    await cmd_start(message, state, bot)

# --- СОЗДАНИЕ ---
@router.message(CreateFlow.main_menu, F.text == "✨ Создать")
async def start_create(message: Message, state: FSMContext, bot: Bot):
    if not await check_subscription(bot, message.from_user.id):
        await message.answer("⚠️ Подпишись на канал, чтобы продолжить:", reply_markup=kb_subscribe())
        return
    await message.answer("📝 Опиши картинку:", reply_markup=ReplyKeyboardMarkup(keyboard=[[BTN_BACK]], resize_keyboard=True))
    await state.set_state(CreateFlow.input_prompt)

@router.message(CreateFlow.input_prompt)
async def got_prompt(message: Message, state: FSMContext):
    await state.update_data(prompt=message.text)
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="1"), KeyboardButton(text="2")], [KeyboardButton(text="3"), KeyboardButton(text="4")], [BTN_BACK]], resize_keyboard=True)
    await message.answer("🔢 Сколько вариантов сгенерировать?\n(1-4)", reply_markup=kb)
    await state.set_state(CreateFlow.select_quantity)

@router.message(CreateFlow.select_quantity, F.text.isdigit())
async def got_qty(message: Message, state: FSMContext):
    qty = int(message.text)
    if qty not in [1, 2, 3, 4]:
        await message.answer("Выбери от 1 до 4.")
        return
    await state.update_data(quantity=qty)
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="16:9"), KeyboardButton(text="9:16"), KeyboardButton(text="3:2")],
        [KeyboardButton(text="2:3"), KeyboardButton(text="4:3"), KeyboardButton(text="3:4")],
        [KeyboardButton(text="1:1"), BTN_BACK]
    ], resize_keyboard=True)
    await message.answer("📐 Выбери соотношение сторон:", reply_markup=kb)
    await state.set_state(CreateFlow.select_aspect_ratio)

@router.message(CreateFlow.select_aspect_ratio, F.text.in_(ASPECT_RATIOS))
async def got_aspect(message: Message, state: FSMContext):
    await state.update_data(aspect_ratio=message.text)
    data = await state.get_data()
    kb = ReplyKeyboardMarkup(keyboard=[[BTN_CONFIRM, BTN_BACK]], resize_keyboard=True)
    await message.answer(
        f"🔍 <b>Проверим параметры</b>\n\n"
        f"📝 <b>Промпт:</b> {data['prompt']}\n"
        f"📐 <b>Соотношение сторон:</b> {data['aspect_ratio']}\n"
        f"🔢 <b>Вариантов:</b> {data['quantity']}\n\n"
        f"Запускаем генерацию? ⚡",
        parse_mode="HTML", reply_markup=kb
    )
    await state.set_state(CreateFlow.confirm)

@router.message(CreateFlow.confirm, F.text == "✅ Подтвердить")
async def create_confirmed(message: Message, state: FSMContext, bot: Bot):
    if not await check_subscription(bot, message.from_user.id):
        await message.answer("⚠️ Подпишись на канал, чтобы продолжить:", reply_markup=kb_subscribe())
        await state.clear()
        return
    data = await state.get_data()
    qty = data["quantity"]
    
    # Отправляем сообщение о начале
    await message.answer(f"⚡ <b>Начинаю генерацию {qty} вариант(а/ов)...</b>", parse_mode="HTML", reply_markup=ReplyKeyboardRemove())
    
    try:
        # ВАЖНО: Цикл, который заставляет API работать несколько раз
        for i in range(qty):
            # Информируем пользователя о прогрессе
            status_msg = await message.answer(f"⏳ Создаю вариант {i+1} из {qty}...")
            
            res = await api_call("/api/v1/image/create", {
                "prompt": data["prompt"],
                "aspect_ratio": data["aspect_ratio"],
                "n": 1 # Всегда просим 1, чтобы API не глючило
            })
            
            imgs = res.get("image_b64", [])
            if isinstance(imgs, str): imgs = [imgs]
            
            if imgs:
                b = decode_b64_image(imgs[0])
                if b:
                    await message.answer_photo(BufferedInputFile(b, filename=f"create_{i+1}.png"))
                    await status_msg.delete() # Удаляем текст "Создаю...", когда фото готово
            else:
                await message.answer(f"❌ Не удалось создать вариант {i+1}")
        
        kb = ReplyKeyboardMarkup(keyboard=[[BTN_CREATE, BTN_EDIT]], resize_keyboard=True)
        await message.answer("✅ <b>Все варианты готовы!</b>", parse_mode="HTML", reply_markup=kb)
    except Exception as e:
        kb = ReplyKeyboardMarkup(keyboard=[[BTN_CREATE, BTN_EDIT]], resize_keyboard=True)
        await message.answer(f"❌ Ошибка: {str(e)}", reply_markup=kb)
    
    await state.set_state(CreateFlow.main_menu)

# --- РЕДАКТИРОВАНИЕ ---
@router.message(CreateFlow.main_menu, F.text == "🎨 Редактировать")
async def start_edit(message: Message, state: FSMContext, bot: Bot):
    if not await check_subscription(bot, message.from_user.id):
        await message.answer("⚠️ Подпишись на канал, чтобы продолжить:", reply_markup=kb_subscribe())
        return
    await message.answer("📷 Отправь фото для редактирования:", reply_markup=ReplyKeyboardMarkup(keyboard=[[BTN_BACK]], resize_keyboard=True))
    await state.set_state(EditFlow.input_image)

@router.message(EditFlow.input_image, F.photo)
async def edit_got_photo(message: Message, state: FSMContext, bot: Bot):
    file = await bot.get_file(message.photo[-1].file_id)
    bio = BytesIO()
    await bot.download_file(file.file_path, bio)
    compressed_b64 = compress_image(bio.getvalue())
    await state.update_data(image_b64=compressed_b64)
    await message.answer("📝 Опиши, как изменить изображение:", reply_markup=ReplyKeyboardMarkup(keyboard=[[BTN_BACK]], resize_keyboard=True))
    await state.set_state(EditFlow.input_prompt)

@router.message(EditFlow.input_prompt)
async def edit_got_prompt(message: Message, state: FSMContext):
    await state.update_data(prompt=message.text)
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="1"), KeyboardButton(text="2")], [KeyboardButton(text="3"), KeyboardButton(text="4")], [BTN_BACK]], resize_keyboard=True)
    await message.answer("🔢 Сколько вариантов сгенерировать?\n(1-4)", reply_markup=kb)
    await state.set_state(EditFlow.select_quantity)

@router.message(EditFlow.select_quantity, F.text.isdigit())
async def edit_got_qty(message: Message, state: FSMContext):
    qty = int(message.text)
    if qty not in [1, 2, 3, 4]:
        await message.answer("Выбери от 1 до 4.")
        return
    await state.update_data(quantity=qty)
    data = await state.get_data()
    kb = ReplyKeyboardMarkup(keyboard=[[BTN_CONFIRM, BTN_BACK]], resize_keyboard=True)
    await message.answer(
        f"🔍 <b>Проверим параметры</b>\n\n"
        f"📝 <b>Промпт:</b> {data['prompt']}\n"
        f"🔢 <b>Вариантов:</b> {data['quantity']}\n\n"
        f"Запускаем редактирование? ⚡",
        parse_mode="HTML", reply_markup=kb
    )
    await state.set_state(EditFlow.confirm)

@router.message(EditFlow.confirm, F.text == "✅ Подтвердить")
async def edit_confirmed(message: Message, state: FSMContext, bot: Bot):
    if not await check_subscription(bot, message.from_user.id):
        await message.answer("⚠️ Подпишись на канал, чтобы продолжить:", reply_markup=kb_subscribe())
        await state.clear()
        return
    data = await state.get_data()
    qty = data["quantity"]
    await message.answer(f"⚡ <b>Обрабатываю {qty} вариант(а/ов)...</b>", parse_mode="HTML", reply_markup=ReplyKeyboardRemove())
    
    try:
        for i in range(qty):
            status_msg = await message.answer(f"⏳ Обрабатываю вариант {i+1} из {qty}...")
            
            res = await api_call("/api/v1/image/edit", {
                "reference_image_b64": data["image_b64"],
                "prompt": data["prompt"],
                "aspect_ratio": "1:1",
                "n": 1
            })
            
            imgs = res.get("image_b64", [])
            if isinstance(imgs, str): imgs = [imgs]
            
            if imgs:
                b = decode_b64_image(imgs[0])
                if b:
                    await message.answer_photo(BufferedInputFile(b, filename=f"edit_{i+1}.png"))
                    await status_msg.delete()
            else:
                await message.answer(f"❌ Не удалось изменить вариант {i+1}")
        
        kb = ReplyKeyboardMarkup(keyboard=[[BTN_CREATE, BTN_EDIT]], resize_keyboard=True)
        await message.answer("✅ <b>Все варианты готовы!</b>", parse_mode="HTML", reply_markup=kb)
    except Exception as e:
        kb = ReplyKeyboardMarkup(keyboard=[[BTN_CREATE, BTN_EDIT]], resize_keyboard=True)
        await message.answer(f"❌ Ошибка: {str(e)}", reply_markup=kb)
    
    await state.set_state(CreateFlow.main_menu)

async def main():
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    await dp.start_polling(bot)

if __name__ == "__main__": asyncio.run(main())
