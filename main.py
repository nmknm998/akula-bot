import os, asyncio, base64, re, httpx, logging
from io import BytesIO
from PIL import Image
from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN", "8482353260:AAExJIgniNYVuGp9Tx0pbSAQRmBIblsg3aU")
API_BASE_URL = os.getenv("API_BASE_URL", "https://voiceapi.csv666.ru")
API_KEY = os.getenv("API_KEY", "421191035:56566a724c66694c5353612f4e3643506a56414853673d3d")
API_TIMEOUT_SEC = 300
CHANNEL_USERNAME = "@ai_akulaa"

class MainMenu(StatesGroup):
    idle = State()

class CreateFlow(StatesGroup):
    input_prompt = State()
    select_quantity = State()
    select_aspect_ratio = State()
    confirm = State()

class EditFlow(StatesGroup):
    input_image = State()
    input_prompt = State()
    confirm = State()

ASPECT_RATIOS = ["16:9", "9:16", "3:2", "2:3", "4:3", "3:4", "1:1"]
BTN_CREATE = KeyboardButton(text="✨ Создать")
BTN_EDIT = KeyboardButton(text="🎨 Редактировать")
BTN_BACK = KeyboardButton(text="⬅️ Назад")
BTN_CONFIRM = KeyboardButton(text="✅ Подтвердить")

def _api_headers():
    return {"x-API-Key": API_KEY, "Content-Type": "application/json"}

def decode_b64_image(b64_str):
    if not b64_str or not isinstance(b64_str, str):
        logger.error("decode_b64_image: пустая строка или не строка")
        return None
    clean_str = re.sub(r'^data:image/.+;base64,', '', b64_str.strip())
    missing_padding = len(clean_str) % 4
    if missing_padding:
        clean_str += '=' * (4 - missing_padding)
    try:
        decoded = base64.b64decode(clean_str)
        logger.info(f"decode_b64_image: успешно декодировано {len(decoded)} байт")
        return decoded
    except Exception as e:
        logger.error(f"decode_b64_image: ошибка декодирования - {e}")
        return None

def compress_image(image_bytes: bytes) -> str:
    try:
        img = Image.open(BytesIO(image_bytes))
        logger.info(f"compress_image: исходное изображение {img.size}, режим {img.mode}")
        
        if img.mode in ('RGBA', 'LA', 'P'):
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
            img = background
        
        max_dimension = 1024
        if max(img.size) > max_dimension:
            img.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
            logger.info(f"compress_image: изображение уменьшено до {img.size}")
        
        output = BytesIO()
        img.save(output, format='JPEG', quality=85, optimize=True)
        compressed_size = len(output.getvalue())
        logger.info(f"compress_image: сжато до {compressed_size} байт")
        
        return base64.b64encode(output.getvalue()).decode('utf-8')
    except Exception as e:
        logger.error(f"compress_image: ошибка - {e}")
        raise

async def api_call(endpoint, payload):
    try:
        logger.info(f"api_call: вызов {endpoint}")
        logger.info(f"api_call: payload keys = {payload.keys()}")
        
        # Проверяем размер base64 изображения если есть
        if 'reference_image_b64' in payload:
            img_size = len(payload['reference_image_b64'])
            logger.info(f"api_call: размер reference_image_b64 = {img_size} символов")
        
        async with httpx.AsyncClient(timeout=API_TIMEOUT_SEC) as client:
            resp = await client.post(f"{API_BASE_URL}{endpoint}", json=payload, headers=_api_headers())
            logger.info(f"api_call: статус ответа = {resp.status_code}")
            resp.raise_for_status()
            result = resp.json()
            logger.info(f"api_call: получен ответ с ключами {result.keys()}")
            return result
    except httpx.HTTPStatusError as e:
        logger.error(f"api_call: HTTP ошибка {e.response.status_code}")
        logger.error(f"api_call: тело ответа = {e.response.text[:1000]}")
        raise
    except Exception as e:
        logger.error(f"api_call: общая ошибка - {e}")
        raise

async def check_subscription(bot: Bot, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception as e:
        logger.error(f"check_subscription: ошибка - {e}")
        return False

def kb_subscribe():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Подписаться на канал", url="https://t.me/ai_akulaa")],
        [InlineKeyboardButton(text="✅ Я подписался", callback_data="check_sub")]
    ])

async def show_main_menu(message: Message, state: FSMContext):
    kb = ReplyKeyboardMarkup(keyboard=[[BTN_CREATE, BTN_EDIT]], resize_keyboard=True)
    await message.answer("🦈 <b>Akula Bot готов!</b>\n\nВыбери действие:", parse_mode="HTML", reply_markup=kb)
    await state.set_state(MainMenu.idle)
    logger.info("show_main_menu: переход в MainMenu.idle")

router = Router()

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext, bot: Bot):
    logger.info(f"cmd_start: пользователь {message.from_user.id}")
    if not await check_subscription(bot, message.from_user.id):
        await message.answer(
            "🦈 <b>Akula Bot</b>\n\n⚠️ Для использования бота подпишись на наш канал:",
            parse_mode="HTML",
            reply_markup=kb_subscribe()
        )
        return
    
    await state.clear()
    await show_main_menu(message, state)

@router.callback_query(F.data == "check_sub")
async def check_sub_callback(callback, bot: Bot, state: FSMContext):
    logger.info(f"check_sub_callback: пользователь {callback.from_user.id}")
    if not await check_subscription(bot, callback.from_user.id):
        await callback.answer("❌ Ты ещё не подписан!", show_alert=True)
        return
    
    await callback.message.delete()
    await show_main_menu(callback.message, state)

@router.message(F.text == "⬅️ Назад")
async def back_btn(message: Message, state: FSMContext, bot: Bot):
    logger.info(f"back_btn: пользователь {message.from_user.id}")
    await show_main_menu(message, state)

# ============ СОЗДАНИЕ ============
@router.message(MainMenu.idle, F.text == "✨ Создать")
async def start_create(message: Message, state: FSMContext, bot: Bot):
    logger.info(f"start_create: пользователь {message.from_user.id}")
    if not await check_subscription(bot, message.from_user.id):
        await message.answer("⚠️ Подпишись на канал, чтобы продолжить:", reply_markup=kb_subscribe())
        return
    
    await message.answer("📝 Опиши картинку:", reply_markup=ReplyKeyboardMarkup(keyboard=[[BTN_BACK]], resize_keyboard=True))
    await state.set_state(CreateFlow.input_prompt)

@router.message(CreateFlow.input_prompt)
async def got_prompt(message: Message, state: FSMContext):
    logger.info(f"got_prompt: {message.text[:50]}")
    await state.update_data(prompt=message.text)
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="1"), KeyboardButton(text="2")],
        [KeyboardButton(text="3"), KeyboardButton(text="4")],
        [BTN_BACK]
    ], resize_keyboard=True)
    await message.answer("🔢 Сколько вариантов сгенерировать?\n(1-4)", reply_markup=kb)
    await state.set_state(CreateFlow.select_quantity)

@router.message(CreateFlow.select_quantity)
async def got_qty(message: Message, state: FSMContext):
    logger.info(f"got_qty: {message.text}")
    if not message.text.isdigit():
        await message.answer("❌ Пожалуйста, выбери число от 1 до 4")
        return
    
    qty = int(message.text)
    if qty not in [1, 2, 3, 4]:
        await message.answer("❌ Выбери от 1 до 4")
        return
    
    await state.update_data(quantity=qty)
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="16:9"), KeyboardButton(text="9:16"), KeyboardButton(text="3:2")],
        [KeyboardButton(text="2:3"), KeyboardButton(text="4:3"), KeyboardButton(text="3:4")],
        [KeyboardButton(text="1:1"), BTN_BACK]
    ], resize_keyboard=True)
    await message.answer("📐 Выбери соотношение сторон:", reply_markup=kb)
    await state.set_state(CreateFlow.select_aspect_ratio)

@router.message(CreateFlow.select_aspect_ratio)
async def got_aspect(message: Message, state: FSMContext):
    logger.info(f"got_aspect: {message.text}")
    if message.text not in ASPECT_RATIOS:
        await message.answer("❌ Пожалуйста, выбери соотношение сторон из предложенных вариантов")
        return
    
    await state.update_data(aspect_ratio=message.text)
    data = await state.get_data()
    kb = ReplyKeyboardMarkup(keyboard=[[BTN_CONFIRM, BTN_BACK]], resize_keyboard=True)
    await message.answer(
        f"🔍 <b>Проверим параметры</b>\n\n"
        f"📝 <b>Промпт:</b> {data['prompt']}\n"
        f"📐 <b>Соотношение сторон:</b> {data['aspect_ratio']}\n"
        f"🔢 <b>Вариантов:</b> {data['quantity']}\n\n"
        f"Запускаем генерацию? ⚡",
        parse_mode="HTML",
        reply_markup=kb
    )
    await state.set_state(CreateFlow.confirm)

@router.message(CreateFlow.confirm, F.text == "✅ Подтвердить")
async def create_confirmed(message: Message, state: FSMContext, bot: Bot):
    logger.info(f"create_confirmed: пользователь {message.from_user.id}")
    if not await check_subscription(bot, message.from_user.id):
        await message.answer("⚠️ Подпишись на канал, чтобы продолжить:", reply_markup=kb_subscribe())
        await state.clear()
        return
    
    data = await state.get_data()
    await message.answer("⚡ <b>Генерирую...</b>", parse_mode="HTML", reply_markup=ReplyKeyboardRemove())
    
    try:
        res = await api_call("/api/v1/image/create", {
            "prompt": data["prompt"],
            "aspect_ratio": data["aspect_ratio"],
            "n": data["quantity"]
        })
        
        imgs = res.get("image_b64", [])
        if isinstance(imgs, str):
            imgs = [imgs]
        
        if not imgs:
            await message.answer("❌ API не вернуло изображений")
        else:
            for idx, img in enumerate(imgs, 1):
                b = decode_b64_image(img)
                if b:
                    await message.answer_photo(BufferedInputFile(b, filename=f"create_{idx}.png"))
        
        await message.answer("✅ <b>Готово!</b>", parse_mode="HTML")
        await show_main_menu(message, state)
    except Exception as e:
        logger.error(f"create_confirmed: ошибка - {e}")
        await message.answer(f"❌ Ошибка: {str(e)}")
        await show_main_menu(message, state)

# ============ РЕДАКТИРОВАНИЕ ============
@router.message(MainMenu.idle, F.text == "🎨 Редактировать")
async def start_edit(message: Message, state: FSMContext, bot: Bot):
    logger.info(f"start_edit: пользователь {message.from_user.id}")
    if not await check_subscription(bot, message.from_user.id):
        await message.answer("⚠️ Подпишись на канал, чтобы продолжить:", reply_markup=kb_subscribe())
        return
    
    await message.answer("📷 Отправь фото для редактирования:", reply_markup=ReplyKeyboardMarkup(keyboard=[[BTN_BACK]], resize_keyboard=True))
    await state.set_state(EditFlow.input_image)
    logger.info("start_edit: переход в EditFlow.input_image")

@router.message(EditFlow.input_image, F.photo)
async def edit_got_photo(message: Message, state: FSMContext, bot: Bot):
    logger.info(f"edit_got_photo: получено фото от {message.from_user.id}")
    try:
        file = await bot.get_file(message.photo[-1].file_id)
        logger.info(f"edit_got_photo: file_path = {file.file_path}")
        
        bio = BytesIO()
        await bot.download_file(file.file_path, bio)
        logger.info(f"edit_got_photo: скачано {len(bio.getvalue())} байт")
        
        compressed_b64 = compress_image(bio.getvalue())
        await state.update_data(image_b64=compressed_b64)
        logger.info(f"edit_got_photo: сохранено в state, длина base64 = {len(compressed_b64)}")
        
        await message.answer("📝 Опиши, как изменить изображение:", reply_markup=ReplyKeyboardMarkup(keyboard=[[BTN_BACK]], resize_keyboard=True))
        await state.set_state(EditFlow.input_prompt)
        logger.info("edit_got_photo: переход в EditFlow.input_prompt")
    except Exception as e:
        logger.error(f"edit_got_photo: ошибка - {e}")
        await message.answer(f"❌ Ошибка обработки фото: {str(e)}")

@router.message(EditFlow.input_image)
async def edit_no_photo(message: Message, state: FSMContext):
    logger.warning(f"edit_no_photo: пользователь {message.from_user.id} отправил не фото")
    await message.answer("❌ Пожалуйста, отправь фото (не файл, не ссылку)")

@router.message(EditFlow.input_prompt)
async def edit_got_prompt(message: Message, state: FSMContext):
    logger.info(f"edit_got_prompt: {message.text[:50]}")
    await state.update_data(prompt=message.text)
    data = await state.get_data()
    
    # Проверяем наличие изображения
    if 'image_b64' not in data:
        logger.error("edit_got_prompt: image_b64 отсутствует в state!")
        await message.answer("❌ Ошибка: изображение потеряно. Начни заново.")
        await show_main_menu(message, state)
        return
    
    kb = ReplyKeyboardMarkup(keyboard=[[BTN_CONFIRM, BTN_BACK]], resize_keyboard=True)
    await message.answer(
        f"🔍 <b>Проверим параметры</b>\n\n"
        f"📝 <b>Инструкция:</b> {data['prompt']}\n\n"
        f"Запускаем редактирование? ⚡",
        parse_mode="HTML",
        reply_markup=kb
    )
    await state.set_state(EditFlow.confirm)

@router.message(EditFlow.confirm, F.text == "✅ Подтвердить")
async def edit_confirmed(message: Message, state: FSMContext, bot: Bot):
    logger.info(f"edit_confirmed: пользователь {message.from_user.id}")
    if not await check_subscription(bot, message.from_user.id):
        await message.answer("⚠️ Подпишись на канал, чтобы продолжить:", reply_markup=kb_subscribe())
        await state.clear()
        return
    
    data = await state.get_data()
    
    # Проверяем наличие всех данных
    if 'image_b64' not in data:
        logger.error("edit_confirmed: image_b64 отсутствует!")
        await message.answer("❌ Ошибка: изображение потеряно. Начни заново.")
        await show_main_menu(message, state)
        return
    
    await message.answer("⚡ <b>Обрабатываю фото...</b>\n\n⏳ Это может занять до 1 минуты", parse_mode="HTML", reply_markup=ReplyKeyboardRemove())
    
    try:
        # ✅ ИСПРАВЛЕНО: используем edit_instruction вместо prompt
        payload = {
            "reference_image_b64": data["image_b64"],
            "edit_instruction": data["prompt"]
        }
        
        logger.info(f"edit_confirmed: отправка запроса с edit_instruction='{data['prompt'][:50]}'")
        
        res = await api_call("/api/v1/image/edit", payload)
        
        # API возвращает одно изображение (не массив)
        img_b64 = res.get("image_b64")
        
        if not img_b64:
            await message.answer("❌ API не вернуло изображение")
        else:
            logger.info(f"edit_confirmed: получено изображение")
            b = decode_b64_image(img_b64)
            if b:
                await message.answer_photo(BufferedInputFile(b, filename="edited.png"))
            else:
                logger.error(f"edit_confirmed: не удалось декодировать изображение")
                await message.answer("❌ Ошибка декодирования изображения")
        
        await message.answer("✅ <b>Готово!</b>", parse_mode="HTML")
        await show_main_menu(message, state)
    except httpx.HTTPStatusError as e:
        error_detail = e.response.text if hasattr(e.response, 'text') else str(e)
        logger.error(f"edit_confirmed: HTTP ошибка {e.response.status_code}: {error_detail}")
        await message.answer(f"❌ Ошибка API ({e.response.status_code}):\n\n{error_detail[:500]}")
        await show_main_menu(message, state)
    except Exception as e:
        logger.error(f"edit_confirmed: общая ошибка - {e}", exc_info=True)
        await message.answer(f"❌ Ошибка: {str(e)}")
        await show_main_menu(message, state)

async def main():
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    logger.info("Бот запущен")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
