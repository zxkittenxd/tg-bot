import asyncio
import logging
import os
import sqlite3
from datetime import datetime, timedelta
from typing import Optional
from aiohttp import web

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, LabeledPrice, PreCheckoutQuery
from aiogram.filters import CommandStart, Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv

# ÐÐ°Ð³ÑÑÐ¶Ð°ÐµÐ¼ Ð¿ÐµÑÐµÐ¼ÐµÐ½Ð½ÑÐµ Ð¾ÐºÑÑÐ¶ÐµÐ½Ð¸Ñ
load_dotenv()

# ÐÐ°ÑÑÑÐ¾Ð¹ÐºÐ° Ð»Ð¾Ð³Ð¸ÑÐ¾Ð²Ð°Ð½Ð¸Ñ
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ÐÐ¾Ð½ÑÐ¸Ð³ÑÑÐ°ÑÐ¸Ñ
BOT_TOKEN = os.getenv("BOT_TOKEN")
PAYMENT_PROVIDER_TOKEN = os.getenv("PAYMENT_PROVIDER_TOKEN")
SUBSCRIPTION_PRICE = int(os.getenv("SUBSCRIPTION_PRICE", "100"))
SUBSCRIPTION_DAYS = int(os.getenv("SUBSCRIPTION_DAYS", "30"))

# ÐÐ°ÑÑÑÐ¾Ð¹ÐºÐ¸ webhook Ð´Ð»Ñ Render
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST", "https://tg-bot-dmhf.onrender.com")
WEBHOOK_PATH = os.getenv("WEBHOOK_PATH", "/webhook")
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"
WEBAPP_HOST = os.getenv("WEBAPP_HOST", "0.0.0.0")
WEBAPP_PORT = int(os.getenv("PORT", "10000"))

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN Ð½Ðµ ÑÑÑÐ°Ð½Ð¾Ð²Ð»ÐµÐ½ Ð² Ð¿ÐµÑÐµÐ¼ÐµÐ½Ð½ÑÑ Ð¾ÐºÑÑÐ¶ÐµÐ½Ð¸Ñ")

# ÐÐ½Ð¸ÑÐ¸Ð°Ð»Ð¸Ð·Ð°ÑÐ¸Ñ Ð±Ð¾ÑÐ°
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# ÐÐ°Ð·Ð° Ð´Ð°Ð½Ð½ÑÑ
def init_db():
    conn = sqlite3.connect('bot.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            subscription_end TIMESTAMP,
            is_active BOOLEAN DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS payments (
            payment_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount INTEGER,
            currency TEXT,
            telegram_payment_charge_id TEXT,
            provider_payment_charge_id TEXT,
            status TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')
    
    conn.commit()
    conn.close()

def get_user(user_id: int) -> Optional[dict]:
    conn = sqlite3.connect('bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = cursor.fetchone()
    conn.close()
    if user:
        return {
            'user_id': user[0],
            'username': user[1],
            'first_name': user[2],
            'subscription_end': user[3],
            'is_active': user[4],
            'created_at': user[5]
        }
    return None

def create_user(user_id: int, username: str, first_name: str):
    conn = sqlite3.connect('bot.db')
    cursor = conn.cursor()
    cursor.execute(
        'INSERT OR IGNORE INTO users (user_id, username, first_name) VALUES (?, ?, ?)',
        (user_id, username, first_name)
    )
    conn.commit()
    conn.close()

def activate_subscription(user_id: int, days: int = SUBSCRIPTION_DAYS):
    conn = sqlite3.connect('bot.db')
    cursor = conn.cursor()
    
    user = get_user(user_id)
    if user and user['subscription_end']:
        current_end = datetime.fromisoformat(user['subscription_end'])
        if current_end > datetime.now():
            new_end = current_end + timedelta(days=days)
        else:
            new_end = datetime.now() + timedelta(days=days)
    else:
        new_end = datetime.now() + timedelta(days=days)
    
    cursor.execute(
        'UPDATE users SET subscription_end = ?, is_active = 1 WHERE user_id = ?',
        (new_end.isoformat(), user_id)
    )
    conn.commit()
    conn.close()
    return new_end

def is_subscribed(user_id: int) -> bool:
    user = get_user(user_id)
    if not user or not user['subscription_end']:
        return False
    return datetime.fromisoformat(user['subscription_end']) > datetime.now()

def get_subscription_info(user_id: int) -> str:
    user = get_user(user_id)
    if not user or not user['subscription_end']:
        return "â Ð£ Ð²Ð°Ñ Ð½ÐµÑ Ð°ÐºÑÐ¸Ð²Ð½Ð¾Ð¹ Ð¿Ð¾Ð´Ð¿Ð¸ÑÐºÐ¸"
    
    end_date = datetime.fromisoformat(user['subscription_end'])
    if end_date <= datetime.now():
        return "â ÐÐ°ÑÐ° Ð¿Ð¾Ð´Ð¿Ð¸ÑÐºÐ° Ð¸ÑÑÐµÐºÐ»Ð°"
    
    days_left = (end_date - datetime.now()).days
    return f"â ÐÐ¾Ð´Ð¿Ð¸ÑÐºÐ° Ð°ÐºÑÐ¸Ð²Ð½Ð° Ð´Ð¾ {end_date.strftime('%d.%m.%Y')} (Ð¾ÑÑÐ°Ð»Ð¾ÑÑ {days_left} Ð´Ð½.)"

# ÐÐ»Ð°Ð²Ð¸Ð°ÑÑÑÑ
def main_keyboard(subscribed: bool = False) -> InlineKeyboardMarkup:
    buttons = []
    
    if not subscribed:
        buttons.append([
            InlineKeyboardButton(text="ð³ ÐÑÐ¿Ð¸ÑÑ Ð¿Ð¾Ð´Ð¿Ð¸ÑÐºÑ", callback_data="buy_subscription")
        ])
    
    buttons.extend([
        [InlineKeyboardButton(text="ð ÐÐ¾Ñ Ð¿Ð¾Ð´Ð¿Ð¸ÑÐºÐ°", callback_data="my_subscription")],
        [InlineKeyboardButton(text="â¹ï¸ Ð Ð±Ð¾ÑÐµ", callback_data="about")],
        [InlineKeyboardButton(text="ð¨âð» ÐÐ¾Ð´Ð´ÐµÑÐ¶ÐºÐ°", callback_data="support")]
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ÐÐ±ÑÐ°Ð±Ð¾ÑÑÐ¸ÐºÐ¸ ÐºÐ¾Ð¼Ð°Ð½Ð´
@dp.message(CommandStart())
async def cmd_start(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or ""
    first_name = message.from_user.first_name or ""
    
    create_user(user_id, username, first_name)
    
    subscribed = is_subscribed(user_id)
    
    text = (
        f"ð ÐÑÐ¸Ð²ÐµÑ, {first_name}!\n\n"
        f"Ð¯ Ð´ÐµÐ¼Ð¾-Ð±Ð¾Ñ Ñ ÑÐ¸ÑÑÐµÐ¼Ð¾Ð¹ Ð¿Ð¾Ð´Ð¿Ð¸ÑÐ¾Ðº. "
        f"ÐÑÐ¿Ð¸ÑÐµ Ð¿Ð¾Ð´Ð¿Ð¸ÑÐºÑ, ÑÑÐ¾Ð±Ñ Ð¿Ð¾Ð»ÑÑÐ¸ÑÑ Ð´Ð¾ÑÑÑÐ¿ Ðº ÑÐºÑÐºÐ»ÑÐ·Ð¸Ð²Ð½ÑÐ¼ ÑÑÐ½ÐºÑÐ¸ÑÐ¼.\n\n"
        f"ð¡ Ð§ÑÐ¾ Ð´Ð°ÑÑ Ð¿Ð¾Ð´Ð¿Ð¸ÑÐºÐ°:\n"
        f"â¢ ÐÐ¾ÑÑÑÐ¿ Ðº Ð¿ÑÐµÐ¼Ð¸ÑÐ¼-ÐºÐ¾Ð½ÑÐµÐ½ÑÑ\n"
        f"â¢ ÐÑÐ¸Ð¾ÑÐ¸ÑÐµÑÐ½Ð°Ñ Ð¿Ð¾Ð´Ð´ÐµÑÐ¶ÐºÐ°\n"
        f"â¢ Ð­ÐºÑÐºÐ»ÑÐ·Ð¸Ð²Ð½ÑÐµ ÑÑÐ½ÐºÑÐ¸Ð¸\n\n"
        f"ð° Ð¡ÑÐ¾Ð¸Ð¼Ð¾ÑÑÑ: {SUBSCRIPTION_PRICE}â½/{SUBSCRIPTION_DAYS} Ð´Ð½ÐµÐ¹"
    )
    
    await message.answer(text, reply_markup=main_keyboard(subscribed))

@dp.message(Command("help"))
async def cmd_help(message: Message):
    text = (
        "ð ÐÐ¾ÑÑÑÐ¿Ð½ÑÐµ ÐºÐ¾Ð¼Ð°Ð½Ð´Ñ:\n\n"
        "/start - ÐÐ»Ð°Ð²Ð½Ð¾Ðµ Ð¼ÐµÐ½Ñ\n"
        "/help - ÐÐ¾Ð¼Ð¾ÑÑ\n"
        "/status - Ð¡ÑÐ°ÑÑÑ Ð¿Ð¾Ð´Ð¿Ð¸ÑÐºÐ¸\n"
        "/buy - ÐÑÐ¿Ð¸ÑÑ Ð¿Ð¾Ð´Ð¿Ð¸ÑÐºÑ\n"
        "/premium - ÐÑÐµÐ¼Ð¸ÑÐ¼-ÐºÐ¾Ð½ÑÐµÐ½Ñ"
    )
    await message.answer(text)

@dp.message(Command("status"))
async def cmd_status(message: Message):
    user_id = message.from_user.id
    text = get_subscription_info(user_id)
    await message.answer(text)

@dp.message(Command("buy"))
async def cmd_buy(message: Message):
    await send_invoice(message)

@dp.message(Command("premium"))
async def cmd_premium(message: Message):
    user_id = message.from_user.id
    
    if not is_subscribed(user_id):
        await message.answer(
            "â Ð£ Ð²Ð°Ñ Ð½ÐµÑ Ð°ÐºÑÐ¸Ð²Ð½Ð¾Ð¹ Ð¿Ð¾Ð´Ð¿Ð¸ÑÐºÐ¸.\n"
            "ÐÑÐ¿Ð¸ÑÐµ Ð¿Ð¾Ð´Ð¿Ð¸ÑÐºÑ, ÑÑÐ¾Ð±Ñ Ð¿Ð¾Ð»ÑÑÐ¸ÑÑ Ð´Ð¾ÑÑÑÐ¿ Ðº Ð¿ÑÐµÐ¼Ð¸ÑÐ¼-ÐºÐ¾Ð½ÑÐµÐ½ÑÑ.",
            reply_markup=main_keyboard(False)
        )
        return
    
    text = (
        "ð ÐÑÐµÐ¼Ð¸ÑÐ¼-ÐºÐ¾Ð½ÑÐµÐ½Ñ:\n\n"
        "Ð¡Ð¿Ð°ÑÐ¸Ð±Ð¾ Ð·Ð° Ð¿Ð¾Ð´Ð¿Ð¸ÑÐºÑ! ÐÐ¾Ñ Ð²Ð°ÑÐ¸ Ð¿ÑÐµÐ¸Ð¼ÑÑÐµÑÑÐ²Ð°:\n\n"
        "â ÐÐ¾ÑÑÑÐ¿ Ðº ÑÐºÑÐºÐ»ÑÐ·Ð¸Ð²Ð½ÑÐ¼ Ð¼Ð°ÑÐµÑÐ¸Ð°Ð»Ð°Ð¼\n"
        "â ÐÑÐ¸Ð¾ÑÐ¸ÑÐµÑÐ½Ð°Ñ Ð¿Ð¾Ð´Ð´ÐµÑÐ¶ÐºÐ°\n"
        "â ÐÐ¾Ð²ÑÐµ ÑÑÐ½ÐºÑÐ¸Ð¸ Ð¿ÐµÑÐ²ÑÐ¼\n\n"
        "Ð¡Ð»ÐµÐ´Ð¸ÑÐµ Ð·Ð° Ð¾Ð±Ð½Ð¾Ð²Ð»ÐµÐ½Ð¸ÑÐ¼Ð¸!"
    )
    await message.answer(text)

# ÐÑÐ¿ÑÐ°Ð²ÐºÐ° ÑÑÑÑÐ° Ð½Ð° Ð¾Ð¿Ð»Ð°ÑÑ
async def send_invoice(message: Message):
    user_id = message.from_user.id
    
    if is_subscribed(user_id):
        await message.answer(
            "â Ð£ Ð²Ð°Ñ ÑÐ¶Ðµ ÐµÑÑÑ Ð°ÐºÑÐ¸Ð²Ð½Ð°Ñ Ð¿Ð¾Ð´Ð¿Ð¸ÑÐºÐ°!\n"
            + get_subscription_info(user_id)
        )
        return
    
    prices = [LabeledPrice(label="ÐÐ¾Ð´Ð¿Ð¸ÑÐºÐ°", amount=SUBSCRIPTION_PRICE * 100)]
    
    await message.answer_invoice(
        title="ÐÐ¾Ð´Ð¿Ð¸ÑÐºÐ° Ð½Ð° Ð±Ð¾ÑÐ°",
        description=f"ÐÐ¾ÑÑÑÐ¿ Ðº Ð¿ÑÐµÐ¼Ð¸ÑÐ¼-ÑÑÐ½ÐºÑÐ¸ÑÐ¼ Ð½Ð° {SUBSCRIPTION_DAYS} Ð´Ð½ÐµÐ¹",
        payload=f"subscription_{user_id}",
        currency="RUB",
        prices=prices,
        start_parameter="subscription",
        provider_token=PAYMENT_PROVIDER_TOKEN,
        need_name=False,
        need_phone_number=False,
        need_email=False,
        need_shipping_address=False,
        is_flexible=False
    )

# ÐÑÐµÐ´Ð²Ð°ÑÐ¸ÑÐµÐ»ÑÐ½Ð°Ñ Ð¿ÑÐ¾Ð²ÐµÑÐºÐ° Ð¿Ð»Ð°ÑÐµÐ¶Ð°
@dp.pre_checkout_query()
async def pre_checkout_query(pre_checkout_query: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

# Ð£ÑÐ¿ÐµÑÐ½ÑÐ¹ Ð¿Ð»Ð°ÑÑÐ¶
@dp.message(F.successful_payment)
async def successful_payment(message: Message):
    user_id = message.from_user.id
    payment = message.successful_payment
    
    # Ð¡Ð¾ÑÑÐ°Ð½ÑÐµÐ¼ Ð¿Ð»Ð°ÑÑÐ¶ Ð² Ð±Ð°Ð·Ñ
    conn = sqlite3.connect('bot.db')
    cursor = conn.cursor()
    cursor.execute(
        '''INSERT INTO payments 
           (user_id, amount, currency, telegram_payment_charge_id, provider_payment_charge_id, status)
           VALUES (?, ?, ?, ?, ?, ?)''',
        (user_id, payment.total_amount, payment.currency,
         payment.telegram_payment_charge_id, payment.provider_payment_charge_id, 'completed')
    )
    conn.commit()
    conn.close()
    
    # ÐÐºÑÐ¸Ð²Ð¸ÑÑÐµÐ¼ Ð¿Ð¾Ð´Ð¿Ð¸ÑÐºÑ
    end_date = activate_subscription(user_id)
    
    text = (
        "â ÐÐ¿Ð»Ð°ÑÐ° Ð¿ÑÐ¾ÑÐ»Ð° ÑÑÐ¿ÐµÑÐ½Ð¾!\n\n"
        f"ð ÐÐ°ÑÐ° Ð¿Ð¾Ð´Ð¿Ð¸ÑÐºÐ° Ð°ÐºÑÐ¸Ð²Ð¸ÑÐ¾Ð²Ð°Ð½Ð° Ð´Ð¾ {end_date.strftime('%d.%m.%Y')}\n\n"
        "Ð¢ÐµÐ¿ÐµÑÑ Ñ Ð²Ð°Ñ ÐµÑÑÑ Ð´Ð¾ÑÑÑÐ¿ ÐºÐ¾ Ð²ÑÐµÐ¼ Ð¿ÑÐµÐ¼Ð¸ÑÐ¼-ÑÑÐ½ÐºÑÐ¸ÑÐ¼!"
    )
    
    await message.answer(text, reply_markup=main_keyboard(True))

# ÐÐ±ÑÐ°Ð±Ð¾ÑÑÐ¸ÐºÐ¸ callback-Ð·Ð°Ð¿ÑÐ¾ÑÐ¾Ð²
@dp.callback_query(F.data == "buy_subscription")
async def callback_buy(callback: CallbackQuery):
    await callback.message.delete()
    await send_invoice(callback.message)

@dp.callback_query(F.data == "my_subscription")
async def callback_my_subscription(callback: CallbackQuery):
    user_id = callback.from_user.id
    text = get_subscription_info(user_id)
    await callback.message.edit_text(text, reply_markup=main_keyboard(is_subscribed(user_id)))

@dp.callback_query(F.data == "about")
async def callback_about(callback: CallbackQuery):
    text = (
        "â¹ï¸ Ð Ð±Ð¾ÑÐµ:\n\n"
        "Ð­ÑÐ¾ Ð´ÐµÐ¼Ð¾-Ð±Ð¾Ñ Ñ ÑÐ¸ÑÑÐµÐ¼Ð¾Ð¹ Ð¿Ð¾Ð´Ð¿Ð¸ÑÐ¾Ðº.\n"
        "ÐÐ½ Ð¿Ð¾ÐºÐ°Ð·ÑÐ²Ð°ÐµÑ, ÐºÐ°Ðº Ð¼Ð¾Ð¶Ð½Ð¾ Ð¼Ð¾Ð½ÐµÑÐ¸Ð·Ð¸ÑÐ¾Ð²Ð°ÑÑ Telegram-Ð±Ð¾ÑÐ°.\n\n"
        "ð¡ ÐÐ´ÐµÐ¸ Ð´Ð»Ñ Ð¼Ð¾Ð½ÐµÑÐ¸Ð·Ð°ÑÐ¸Ð¸:\n"
        "â¢ Ð­ÐºÑÐºÐ»ÑÐ·Ð¸Ð²Ð½ÑÐ¹ ÐºÐ¾Ð½ÑÐµÐ½Ñ\n"
        "â¢ ÐÐ²ÑÐ¾Ð¼Ð°ÑÐ¸Ð·Ð°ÑÐ¸Ñ Ð·Ð°Ð´Ð°Ñ\n"
        "â¢ ÐÐ¾ÑÑÑÐ¿ Ðº Ð±Ð°Ð·Ðµ Ð´Ð°Ð½Ð½ÑÑ\n"
        "â¢ ÐÐµÑÑÐ¾Ð½Ð°Ð»ÑÐ½ÑÐµ ÐºÐ¾Ð½ÑÑÐ»ÑÑÐ°ÑÐ¸Ð¸"
    )
    await callback.message.edit_text(text, reply_markup=main_keyboard(is_subscribed(callback.from_user.id)))

@dp.callback_query(F.data == "support")
async def callback_support(callback: CallbackQuery):
    text = (
        "ð¨âð» ÐÐ¾Ð´Ð´ÐµÑÐ¶ÐºÐ°:\n\n"
        "ÐÑÐ»Ð¸ Ñ Ð²Ð°Ñ ÐµÑÑÑ Ð²Ð¾Ð¿ÑÐ¾ÑÑ, Ð½Ð°Ð¿Ð¸ÑÐ¸ÑÐµ Ð½Ð°Ð¼:\n"
        "@username_support\n\n"
        "ÐÑ Ð¾ÑÐ²ÐµÑÐ°ÐµÐ¼ Ð² ÑÐµÑÐµÐ½Ð¸Ðµ 24 ÑÐ°ÑÐ¾Ð²."
    )
    await callback.message.edit_text(text, reply_markup=main_keyboard(is_subscribed(callback.from_user.id)))

# Webhook Ð¾Ð±ÑÐ°Ð±Ð¾ÑÑÐ¸Ðº
async def webhook_handler(request):
    try:
        update = await request.json()
        await dp.feed_update(bot, update)
        return web.Response(text="OK")
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        return web.Response(text="Error", status=500)

# Health check Ð´Ð»Ñ Render
async def health_check(request):
    return web.Response(text="OK")

# ÐÐ°ÑÑÑÐ¾Ð¹ÐºÐ° Ð²ÐµÐ±-Ð¿ÑÐ¸Ð»Ð¾Ð¶ÐµÐ½Ð¸Ñ
async def on_startup(app):
    # Ð£ÑÑÐ°Ð½Ð°Ð²Ð»Ð¸Ð²Ð°ÐµÐ¼ webhook
    await bot.set_webhook(WEBHOOK_URL)
    logger.info(f"Webhook ÑÑÑÐ°Ð½Ð¾Ð²Ð»ÐµÐ½: {WEBHOOK_URL}")

async def on_shutdown(app):
    # Ð£Ð´Ð°Ð»ÑÐµÐ¼ webhook
    await bot.delete_webhook()
    logger.info("Webhook ÑÐ´Ð°Ð»ÑÐ½")

# ÐÐ°Ð¿ÑÑÐº Ð²ÐµÐ±-Ð¿ÑÐ¸Ð»Ð¾Ð¶ÐµÐ½Ð¸Ñ
async def main():
    init_db()
    
    app = web.Application()
    app.router.add_post(WEBHOOK_PATH, webhook_handler)
    app.router.add_get("/health", health_check)
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, WEBAPP_HOST, WEBAPP_PORT)
    
    logger.info(f"Ð¡ÐµÑÐ²ÐµÑ Ð·Ð°Ð¿ÑÑÐµÐ½ Ð½Ð° {WEBAPP_HOST}:{WEBAPP_PORT}")
    await site.start()
    
    # ÐÐµÑÐ¶Ð¸Ð¼ ÑÐµÑÐ²ÐµÑ Ð·Ð°Ð¿ÑÑÐµÐ½Ð½ÑÐ¼
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
