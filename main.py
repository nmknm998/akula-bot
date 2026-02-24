import os, asyncio, base64, re, httpx, logging
from io import BytesIO
from PIL import Image
from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN", "YOR TOKEN BOT")
API_BASE_URL = os.getenv("API_BASE_URL", "https://voiceapi.csv666.ru")
API_KEY = os.getenv("API_KEY", "YOUR KOD")
API_TIMEOUT_SEC = 300
CHANNEL_USERNAME = "@ai_akulaa"

class MainMenu(StatesGroup):
    idle = State()

class CreateFlow(StatesGroup):
    input_prompt = State()
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
        if img.mode in ('RGBA', 'LA', 'P'):
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
            img = background
        max_dimension = 1024
        if max(img.size) > max_dimension:
            img.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
        output = BytesIO()
        img.save(output, format='JPEG', quality=85, optimize=True)
        return base64.b64encode(output.getvalue()).decode('utf-8')
    except Exception as e:
        logger.error(f"compress_image: ошибка - {e}")
        raise

async def api_call(endpoint, payload, retries=3):
    for attempt in range(retries):
        try:
            logger.info(f"api_call: попытка {attempt + 1}/{retries} -> {endpoint}")
            async with httpx.AsyncClient(timeout=API_TIMEOUT_SEC) as client:
                resp = await client.post(f"{API_BASE_URL}{endpoint}", json=payload, headers=_api_headers())
                logger.info(f"api_call: статус = {resp.status_code}")

                # Если сервер перегружен — ждём и пробуем снова
                if resp.status_code == 503:
                    if attempt < retries - 1:
                        logger.warning(f"api_call: 503 Сервер перегружен, ждём 5 сек...")
                        await asyncio.sleep(5)
                        continue
                    else:
                        resp.raise_for_status()

                resp.raise_for_status()
                result = resp.json()
                logger.info(f"api_call: успех, ключи ответа = {result.keys()}")
                return result

        except httpx.HTTPStatusError as e:
            logger.error(f"api_call: HTTP ошибка {e.response.status_code}: {e.response.text[:500]}")
            if attempt < retries - 1 and e.response.status_code in [503, 502, 500]:
                logger.warning(f"api_call: повтор через 5 сек...")
                await asyncio.sleep(5)
                continue
            raise
        except Exception as e:
            logger.error(f"api_call: общая ошибка - {e}")
            if attempt < retries - 1:
                await asyncio.sleep(5)
                continue
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

def kb_after_generation(aspect_ratio: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Перегенерировать", callback_data=f"regenerate:{aspect_ratio}")],
        [InlineKeyboardButton(text="✨ Новая генерация", callback_data="new_generation")],
        [InlineKeyboardButton(text="🎨 Редактировать результат", callback_data="edit_result")],
        [InlineKeyboardButton(text="🏠 В меню", callback_data="to_menu")]
    ])

def kb_after_edit():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Повторить редактирование", callback_data="re_edit")],
        [InlineKeyboardButton(text="✨ Новая генерация", callback_data="new_generation")],
        [InlineKeyboardButton(text="🎨 Редактировать ещё раз", callback_data="edit_again")],
        [InlineKeyboardButton(text="🏠 В меню", callback_data="to_menu")]
    ])

async def show_main_menu(message: Message, state: FSMContext):
    kb = ReplyKeyboardMarkup(keyboard=[[BTN_CREATE, BTN_EDIT]], resize_keyboard=True)
    await message.answer("🦈 <b>Akula Bot готов!</b>\n\nВыбери действие:", parse_mode="HTML", reply_markup=kb)
    await state.set_state(MainMenu.idle)

router = Router()

# ============ СТАРТ ============
@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext, bot: Bot):
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
    if not await check_subscription(bot, callback.from_user.id):
        await callback.answer("❌ Ты ещё не подписан!", show_alert=True)
        return
    await callback.message.delete()
    await show_main_menu(callback.message, state)

@router.message(F.text == "⬅️ Назад")
async def back_btn(message: Message, state: FSMContext):
    await show_main_menu(message, state)

# ============ КНОПКИ ПОСЛЕ ГЕНЕРАЦИИ ============
@router.callback_query(F.data.startswith("regenerate:"))
async def regenerate_callback(callback, state: FSMContext):
    data = await state.get_data()
    aspect_ratio = callback.data.split(":")[1]
    await callback.message.delete()
    wait_msg = await callback.message.answer("⚡ <b>Перегенерирую...</b>\n⏳ Пожалуйста, подожди...", parse_mode="HTML")
    try:
        res = await api_call("/api/v1/image/create", {
            "prompt": data["prompt"],
            "aspect_ratio": aspect_ratio
        })
        imgs = res.get("image_b64", [])
        if isinstance(imgs, str):
            imgs = [imgs]
        await wait_msg.delete()
        if imgs:
            b = decode_b64_image(imgs[0])
            if b:
                await callback.message.answer_photo(BufferedInputFile(b, filename="create.png"))
        await callback.message.answer(
            f"⭐ <b>Изображение успешно создано</b>\n\n"
            f"• <b>Промпт:</b> {data['prompt']}\n"
            f"• <b>Соотношение сторон:</b> {aspect_ratio}\n\n"
            f"💡 <b>Что дальше?</b>\nВыберите действие кнопками ниже.",
            parse_mode="HTML",
            reply_markup=kb_after_generation(aspect_ratio)
        )
    except Exception as e:
        await wait_msg.delete()
        await callback.message.answer(
            "❌ <b>Сервер перегружен.</b>\nПопробуй ещё раз через минуту.",
            parse_mode="HTML",
            reply_markup=kb_after_generation(aspect_ratio)
        )

@router.callback_query(F.data == "new_generation")
async def new_generation_callback(callback, state: FSMContext):
    await callback.message.delete()
    await state.clear()
    await callback.message.answer("📝 Опиши картинку:", reply_markup=ReplyKeyboardMarkup(keyboard=[[BTN_BACK]], resize_keyboard=True))
    await state.set_state(CreateFlow.input_prompt)

@router.callback_query(F.data == "edit_result")
async def edit_result_callback(callback, state: FSMContext):
    await callback.message.delete()
    await callback.message.answer("📷 Отправь фото для редактирования:", reply_markup=ReplyKeyboardMarkup(keyboard=[[BTN_BACK]], resize_keyboard=True))
    await state.set_state(EditFlow.input_image)

@router.callback_query(F.data == "edit_again")
async def edit_again_callback(callback, state: FSMContext):
    await callback.message.delete()
    await callback.message.answer("📷 Отправь фото для редактирования:", reply_markup=ReplyKeyboardMarkup(keyboard=[[BTN_BACK]], resize_keyboard=True))
    await state.set_state(EditFlow.input_image)

@router.callback_query(F.data == "re_edit")
async def re_edit_callback(callback, state: FSMContext):
    data = await state.get_data()
    if 'image_b64' not in data or 'prompt' not in data:
        await callback.answer("❌ Данные потеряны. Начни заново.", show_alert=True)
        return
    await callback.message.delete()
    wait_msg = await callback.message.answer("⚡ <b>Обрабатываю фото...</b>\n⏳ Это может занять до 1 минуты", parse_mode="HTML")
    try:
        res = await api_call("/api/v1/image/edit", {
            "reference_image_b64": data["image_b64"],
            "edit_instruction": data["prompt"]
        })
        img_b64 = res.get("image_b64")
        await wait_msg.delete()
        if img_b64:
            b = decode_b64_image(img_b64)
            if b:
                await callback.message.answer_photo(BufferedInputFile(b, filename="edited.png"))
        await callback.message.answer(
            f"⭐ <b>Изображение успешно отредактировано</b>\n\n"
            f"• <b>Инструкция:</b> {data['prompt']}\n\n"
            f"💡 <b>Что дальше?</b>\nВыберите действие кнопками ниже.",
            parse_mode="HTML",
            reply_markup=kb_after_edit()
        )
    except Exception as e:
        await wait_msg.delete()
        await callback.message.answer(
            "❌ <b>Сервер перегружен.</b>\nПопробуй ещё раз через минуту.",
            parse_mode="HTML",
            reply_markup=kb_after_edit()
        )

@router.callback_query(F.data == "to_menu")
async def to_menu_callback(callback, state: FSMContext):
    await callback.message.delete()
    await show_main_menu(callback.message, state)

# ============ СОЗДАНИЕ ============
@router.message(MainMenu.idle, F.text == "✨ Создать")
async def start_create(message: Message, state: FSMContext, bot: Bot):
    if not await check_subscription(bot, message.from_user.id):
        await message.answer("⚠️ Подпишись на канал, чтобы продолжить:", reply_markup=kb_subscribe())
        return
    await message.answer("📝 Опиши картинку:", reply_markup=ReplyKeyboardMarkup(keyboard=[[BTN_BACK]], resize_keyboard=True))
    await state.set_state(CreateFlow.input_prompt)

@router.message(CreateFlow.input_prompt)
async def got_prompt(message: Message, state: FSMContext):
    await state.update_data(prompt=message.text)
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="16:9"), KeyboardButton(text="9:16"), KeyboardButton(text="3:2")],
        [KeyboardButton(text="2:3"), KeyboardButton(text="4:3"), KeyboardButton(text="3:4")],
        [KeyboardButton(text="1:1"), BTN_BACK]
    ], resize_keyboard=True)
    await message.answer("📐 Выбери соотношение сторон:", reply_markup=kb)
    await state.set_state(CreateFlow.select_aspect_ratio)

@router.message(CreateFlow.select_aspect_ratio)
async def got_aspect(message: Message, state: FSMContext):
    if message.text not in ASPECT_RATIOS:
        await message.answer("❌ Выбери соотношение сторон из предложенных вариантов")
        return
    await state.update_data(aspect_ratio=message.text)
    data = await state.get_data()
    kb = ReplyKeyboardMarkup(keyboard=[[BTN_CONFIRM, BTN_BACK]], resize_keyboard=True)
    await message.answer(
        f"🔍 <b>Проверим параметры</b>\n\n"
        f"📝 <b>Промпт:</b> {data['prompt']}\n"
        f"📐 <b>Соотношение сторон:</b> {data['aspect_ratio']}\n\n"
        f"Запускаем генерацию? ⚡",
        parse_mode="HTML",
        reply_markup=kb
    )
    await state.set_state(CreateFlow.confirm)

@router.message(CreateFlow.confirm, F.text == "✅ Подтвердить")
async def create_confirmed(message: Message, state: FSMContext, bot: Bot):
    if not await check_subscription(bot, message.from_user.id):
        await message.answer("⚠️ Подпишись на канал, чтобы продолжить:", reply_markup=kb_subscribe())
        await state.clear()
        return
    data = await state.get_data()
    wait_msg = await message.answer("⚡ <b>Генерирую...</b>\n⏳ Пожалуйста, подожди...", parse_mode="HTML", reply_markup=ReplyKeyboardRemove())
    try:
        res = await api_call("/api/v1/image/create", {
            "prompt": data["prompt"],
            "aspect_ratio": data["aspect_ratio"]
        })
        imgs = res.get("image_b64", [])
        if isinstance(imgs, str):
            imgs = [imgs]
        await wait_msg.delete()
        if not imgs:
            await message.answer("❌ API не вернуло изображений")
            await show_main_menu(message, state)
            return
        b = decode_b64_image(imgs[0])
        if b:
            await message.answer_photo(BufferedInputFile(b, filename="create.png"))
        await message.answer(
            f"⭐ <b>Изображение успешно создано</b>\n\n"
            f"• <b>Промпт:</b> {data['prompt']}\n"
            f"• <b>Соотношение сторон:</b> {data['aspect_ratio']}\n\n"
            f"💡 <b>Что дальше?</b>\nВыберите действие кнопками ниже.",
            parse_mode="HTML",
            reply_markup=kb_after_generation(data['aspect_ratio'])
        )
    except Exception as e:
        logger.error(f"create_confirmed: ошибка - {e}")
        await wait_msg.delete()
        await message.answer(
            "❌ <b>Сервер перегружен.</b>\nПопробуй ещё раз через минуту.",
            parse_mode="HTML"
        )
        await show_main_menu(message, state)

# ============ РЕДАКТИРОВАНИЕ ============
@router.message(MainMenu.idle, F.text == "🎨 Редактировать")
async def start_edit(message: Message, state: FSMContext, bot: Bot):
    if not await check_subscription(bot, message.from_user.id):
        await message.answer("⚠️ Подпишись на канал, чтобы продолжить:", reply_markup=kb_subscribe())
        return
    await message.answer("📷 Отправь фото для редактирования:", reply_markup=ReplyKeyboardMarkup(keyboard=[[BTN_BACK]], resize_keyboard=True))
    await state.set_state(EditFlow.input_image)

@router.message(EditFlow.input_image, F.photo)
async def edit_got_photo(message: Message, state: FSMContext, bot: Bot):
    try:
        file = await bot.get_file(message.photo[-1].file_id)
        bio = BytesIO()
        await bot.download_file(file.file_path, bio)
        compressed_b64 = compress_image(bio.getvalue())
        await state.update_data(image_b64=compressed_b64)
        await message.answer("📝 Опиши, как изменить изображение:", reply_markup=ReplyKeyboardMarkup(keyboard=[[BTN_BACK]], resize_keyboard=True))
        await state.set_state(EditFlow.input_prompt)
    except Exception as e:
        logger.error(f"edit_got_photo: ошибка - {e}")
        await message.answer(f"❌ Ошибка обработки фото: {str(e)}")

@router.message(EditFlow.input_image)
async def edit_no_photo(message: Message, state: FSMContext):
    await message.answer("❌ Пожалуйста, отправь фото (не файл, не ссылку)")

@router.message(EditFlow.input_prompt)
async def edit_got_prompt(message: Message, state: FSMContext):
    await state.update_data(prompt=message.text)
    data = await state.get_data()
    if 'image_b64' not in data:
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
    if not await check_subscription(bot, message.from_user.id):
        await message.answer("⚠️ Подпишись на канал, чтобы продолжить:", reply_markup=kb_subscribe())
        await state.clear()
        return
    data = await state.get_data()
    if 'image_b64' not in data:
        await message.answer("❌ Ошибка: изображение потеряно. Начни заново.")
        await show_main_menu(message, state)
        return
    wait_msg = await message.answer("⚡ <b>Обрабатываю фото...</b>\n⏳ Это может занять до 1 минуты", parse_mode="HTML", reply_markup=ReplyKeyboardRemove())
    try:
        res = await api_call("/api/v1/image/edit", {
            "reference_image_b64": data["image_b64"],
            "edit_instruction": data["prompt"]
        })
        img_b64 = res.get("image_b64")
        await wait_msg.delete()
        if not img_b64:
            await message.answer("❌ API не вернуло изображение")
            await show_main_menu(message, state)
            return
        b = decode_b64_image(img_b64)
        if b:
            await message.answer_photo(BufferedInputFile(b, filename="edited.png"))
        await message.answer(
            f"⭐ <b>Изображение успешно отредактировано</b>\n\n"
            f"• <b>Инструкция:</b> {data['prompt']}\n\n"
            f"💡 <b>Что дальше?</b>\nВыберите действие кнопками ниже.",
            parse_mode="HTML",
            reply_markup=kb_after_edit()
        )
    except Exception as e:
        logger.error(f"edit_confirmed: ошибка - {e}", exc_info=True)
        await wait_msg.delete()
        await message.answer(
            "❌ <b>Сервер перегружен.</b>\nПопробуй ещё раз через минуту.",
            parse_mode="HTML"
        )
        await show_main_menu(message, state)

async def main():
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    logger.info("Бот запущен")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

