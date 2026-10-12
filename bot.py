import asyncio
import json
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

# ÃÂÃÂ°ÃÂ³ÃÂÃÂÃÂ¶ÃÂ°ÃÂµÃÂ¼ ÃÂ¿ÃÂµÃÂÃÂµÃÂ¼ÃÂµÃÂ½ÃÂ½ÃÂÃÂµ ÃÂ¾ÃÂºÃÂÃÂÃÂ¶ÃÂµÃÂ½ÃÂ¸ÃÂ
load_dotenv()

# ÃÂÃÂ°ÃÂÃÂÃÂÃÂ¾ÃÂ¹ÃÂºÃÂ° ÃÂ»ÃÂ¾ÃÂ³ÃÂ¸ÃÂÃÂ¾ÃÂ²ÃÂ°ÃÂ½ÃÂ¸ÃÂ
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ÃÂÃÂ¾ÃÂ½ÃÂÃÂ¸ÃÂ³ÃÂÃÂÃÂ°ÃÂÃÂ¸ÃÂ
BOT_TOKEN = os.getenv("BOT_TOKEN")
PAYMENT_PROVIDER_TOKEN = os.getenv("PAYMENT_PROVIDER_TOKEN")
SUBSCRIPTION_PRICE = int(os.getenv("SUBSCRIPTION_PRICE", "100"))
SUBSCRIPTION_DAYS = int(os.getenv("SUBSCRIPTION_DAYS", "30"))

# ÃÂÃÂ°ÃÂÃÂÃÂÃÂ¾ÃÂ¹ÃÂºÃÂ¸ webhook ÃÂ´ÃÂ»ÃÂ Render
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST", "https://tg-bot-dmhf.onrender.com")
WEBHOOK_PATH = os.getenv("WEBHOOK_PATH", "/webhook")
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"
WEBAPP_HOST = os.getenv("WEBAPP_HOST", "0.0.0.0")
WEBAPP_PORT = int(os.getenv("PORT", "10000"))

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN ÃÂ½ÃÂµ ÃÂÃÂÃÂÃÂ°ÃÂ½ÃÂ¾ÃÂ²ÃÂ»ÃÂµÃÂ½ ÃÂ² ÃÂ¿ÃÂµÃÂÃÂµÃÂ¼ÃÂµÃÂ½ÃÂ½ÃÂÃÂ ÃÂ¾ÃÂºÃÂÃÂÃÂ¶ÃÂµÃÂ½ÃÂ¸ÃÂ")

# ÃÂÃÂ½ÃÂ¸ÃÂÃÂ¸ÃÂ°ÃÂ»ÃÂ¸ÃÂ·ÃÂ°ÃÂÃÂ¸ÃÂ ÃÂ±ÃÂ¾ÃÂÃÂ°
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# ÃÂÃÂ°ÃÂ·ÃÂ° ÃÂ´ÃÂ°ÃÂ½ÃÂ½ÃÂÃÂ
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
        return "Ã¢ÂÂ ÃÂ£ ÃÂ²ÃÂ°ÃÂ ÃÂ½ÃÂµÃÂ ÃÂ°ÃÂºÃÂÃÂ¸ÃÂ²ÃÂ½ÃÂ¾ÃÂ¹ ÃÂ¿ÃÂ¾ÃÂ´ÃÂ¿ÃÂ¸ÃÂÃÂºÃÂ¸"
    
    end_date = datetime.fromisoformat(user['subscription_end'])
    if end_date <= datetime.now():
        return "Ã¢ÂÂ ÃÂÃÂ°ÃÂÃÂ° ÃÂ¿ÃÂ¾ÃÂ´ÃÂ¿ÃÂ¸ÃÂÃÂºÃÂ° ÃÂ¸ÃÂÃÂÃÂµÃÂºÃÂ»ÃÂ°"
    
    days_left = (end_date - datetime.now()).days
    return f"Ã¢ÂÂ ÃÂÃÂ¾ÃÂ´ÃÂ¿ÃÂ¸ÃÂÃÂºÃÂ° ÃÂ°ÃÂºÃÂÃÂ¸ÃÂ²ÃÂ½ÃÂ° ÃÂ´ÃÂ¾ {end_date.strftime('%d.%m.%Y')} (ÃÂ¾ÃÂÃÂÃÂ°ÃÂ»ÃÂ¾ÃÂÃÂ {days_left} ÃÂ´ÃÂ½.)"

# ÃÂÃÂ»ÃÂ°ÃÂ²ÃÂ¸ÃÂ°ÃÂÃÂÃÂÃÂ
def main_keyboard(subscribed: bool = False) -> InlineKeyboardMarkup:
    buttons = []
    
    if not subscribed:
        buttons.append([
            InlineKeyboardButton(text="Ã°ÂÂÂ³ ÃÂÃÂÃÂ¿ÃÂ¸ÃÂÃÂ ÃÂ¿ÃÂ¾ÃÂ´ÃÂ¿ÃÂ¸ÃÂÃÂºÃÂ", callback_data="buy_subscription")
        ])
    
    buttons.extend([
        [InlineKeyboardButton(text="Ã°ÂÂÂ ÃÂÃÂ¾ÃÂ ÃÂ¿ÃÂ¾ÃÂ´ÃÂ¿ÃÂ¸ÃÂÃÂºÃÂ°", callback_data="my_subscription")],
        [InlineKeyboardButton(text="Ã¢ÂÂ¹Ã¯Â¸Â ÃÂ ÃÂ±ÃÂ¾ÃÂÃÂµ", callback_data="about")],
        [InlineKeyboardButton(text="Ã°ÂÂÂ¨Ã¢ÂÂÃ°ÂÂÂ» ÃÂÃÂ¾ÃÂ´ÃÂ´ÃÂµÃÂÃÂ¶ÃÂºÃÂ°", callback_data="support")]
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ÃÂÃÂ±ÃÂÃÂ°ÃÂ±ÃÂ¾ÃÂÃÂÃÂ¸ÃÂºÃÂ¸ ÃÂºÃÂ¾ÃÂ¼ÃÂ°ÃÂ½ÃÂ´
@dp.message(CommandStart())
async def cmd_start(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or ""
    first_name = message.from_user.first_name or ""
    
    create_user(user_id, username, first_name)
    
    subscribed = is_subscribed(user_id)
    
    text = (
        f"Ã°ÂÂÂ ÃÂÃÂÃÂ¸ÃÂ²ÃÂµÃÂ, {first_name}!\n\n"
        f"ÃÂ¯ ÃÂ´ÃÂµÃÂ¼ÃÂ¾-ÃÂ±ÃÂ¾ÃÂ ÃÂ ÃÂÃÂ¸ÃÂÃÂÃÂµÃÂ¼ÃÂ¾ÃÂ¹ ÃÂ¿ÃÂ¾ÃÂ´ÃÂ¿ÃÂ¸ÃÂÃÂ¾ÃÂº. "
        f"ÃÂÃÂÃÂ¿ÃÂ¸ÃÂÃÂµ ÃÂ¿ÃÂ¾ÃÂ´ÃÂ¿ÃÂ¸ÃÂÃÂºÃÂ, ÃÂÃÂÃÂ¾ÃÂ±ÃÂ ÃÂ¿ÃÂ¾ÃÂ»ÃÂÃÂÃÂ¸ÃÂÃÂ ÃÂ´ÃÂ¾ÃÂÃÂÃÂÃÂ¿ ÃÂº ÃÂÃÂºÃÂÃÂºÃÂ»ÃÂÃÂ·ÃÂ¸ÃÂ²ÃÂ½ÃÂÃÂ¼ ÃÂÃÂÃÂ½ÃÂºÃÂÃÂ¸ÃÂÃÂ¼.\n\n"
        f"Ã°ÂÂÂ¡ ÃÂ§ÃÂÃÂ¾ ÃÂ´ÃÂ°ÃÂÃÂ ÃÂ¿ÃÂ¾ÃÂ´ÃÂ¿ÃÂ¸ÃÂÃÂºÃÂ°:\n"
        f"Ã¢ÂÂ¢ ÃÂÃÂ¾ÃÂÃÂÃÂÃÂ¿ ÃÂº ÃÂ¿ÃÂÃÂµÃÂ¼ÃÂ¸ÃÂÃÂ¼-ÃÂºÃÂ¾ÃÂ½ÃÂÃÂµÃÂ½ÃÂÃÂ\n"
        f"Ã¢ÂÂ¢ ÃÂÃÂÃÂ¸ÃÂ¾ÃÂÃÂ¸ÃÂÃÂµÃÂÃÂ½ÃÂ°ÃÂ ÃÂ¿ÃÂ¾ÃÂ´ÃÂ´ÃÂµÃÂÃÂ¶ÃÂºÃÂ°\n"
        f"Ã¢ÂÂ¢ ÃÂ­ÃÂºÃÂÃÂºÃÂ»ÃÂÃÂ·ÃÂ¸ÃÂ²ÃÂ½ÃÂÃÂµ ÃÂÃÂÃÂ½ÃÂºÃÂÃÂ¸ÃÂ¸\n\n"
        f"Ã°ÂÂÂ° ÃÂ¡ÃÂÃÂ¾ÃÂ¸ÃÂ¼ÃÂ¾ÃÂÃÂÃÂ: {SUBSCRIPTION_PRICE}Ã¢ÂÂ½/{SUBSCRIPTION_DAYS} ÃÂ´ÃÂ½ÃÂµÃÂ¹"
    )
    
    await message.answer(text, reply_markup=main_keyboard(subscribed))

@dp.message(Command("help"))
async def cmd_help(message: Message):
    text = (
        "Ã°ÂÂÂ ÃÂÃÂ¾ÃÂÃÂÃÂÃÂ¿ÃÂ½ÃÂÃÂµ ÃÂºÃÂ¾ÃÂ¼ÃÂ°ÃÂ½ÃÂ´ÃÂ:\n\n"
        "/start - ÃÂÃÂ»ÃÂ°ÃÂ²ÃÂ½ÃÂ¾ÃÂµ ÃÂ¼ÃÂµÃÂ½ÃÂ\n"
        "/help - ÃÂÃÂ¾ÃÂ¼ÃÂ¾ÃÂÃÂ\n"
        "/status - ÃÂ¡ÃÂÃÂ°ÃÂÃÂÃÂ ÃÂ¿ÃÂ¾ÃÂ´ÃÂ¿ÃÂ¸ÃÂÃÂºÃÂ¸\n"
        "/buy - ÃÂÃÂÃÂ¿ÃÂ¸ÃÂÃÂ ÃÂ¿ÃÂ¾ÃÂ´ÃÂ¿ÃÂ¸ÃÂÃÂºÃÂ\n"
        "/premium - ÃÂÃÂÃÂµÃÂ¼ÃÂ¸ÃÂÃÂ¼-ÃÂºÃÂ¾ÃÂ½ÃÂÃÂµÃÂ½ÃÂ"
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
            "Ã¢ÂÂ ÃÂ£ ÃÂ²ÃÂ°ÃÂ ÃÂ½ÃÂµÃÂ ÃÂ°ÃÂºÃÂÃÂ¸ÃÂ²ÃÂ½ÃÂ¾ÃÂ¹ ÃÂ¿ÃÂ¾ÃÂ´ÃÂ¿ÃÂ¸ÃÂÃÂºÃÂ¸.\n"
            "ÃÂÃÂÃÂ¿ÃÂ¸ÃÂÃÂµ ÃÂ¿ÃÂ¾ÃÂ´ÃÂ¿ÃÂ¸ÃÂÃÂºÃÂ, ÃÂÃÂÃÂ¾ÃÂ±ÃÂ ÃÂ¿ÃÂ¾ÃÂ»ÃÂÃÂÃÂ¸ÃÂÃÂ ÃÂ´ÃÂ¾ÃÂÃÂÃÂÃÂ¿ ÃÂº ÃÂ¿ÃÂÃÂµÃÂ¼ÃÂ¸ÃÂÃÂ¼-ÃÂºÃÂ¾ÃÂ½ÃÂÃÂµÃÂ½ÃÂÃÂ.",
            reply_markup=main_keyboard(False)
        )
        return
    
    text = (
        "Ã°ÂÂÂ ÃÂÃÂÃÂµÃÂ¼ÃÂ¸ÃÂÃÂ¼-ÃÂºÃÂ¾ÃÂ½ÃÂÃÂµÃÂ½ÃÂ:\n\n"
        "ÃÂ¡ÃÂ¿ÃÂ°ÃÂÃÂ¸ÃÂ±ÃÂ¾ ÃÂ·ÃÂ° ÃÂ¿ÃÂ¾ÃÂ´ÃÂ¿ÃÂ¸ÃÂÃÂºÃÂ! ÃÂÃÂ¾ÃÂ ÃÂ²ÃÂ°ÃÂÃÂ¸ ÃÂ¿ÃÂÃÂµÃÂ¸ÃÂ¼ÃÂÃÂÃÂµÃÂÃÂÃÂ²ÃÂ°:\n\n"
        "Ã¢ÂÂ ÃÂÃÂ¾ÃÂÃÂÃÂÃÂ¿ ÃÂº ÃÂÃÂºÃÂÃÂºÃÂ»ÃÂÃÂ·ÃÂ¸ÃÂ²ÃÂ½ÃÂÃÂ¼ ÃÂ¼ÃÂ°ÃÂÃÂµÃÂÃÂ¸ÃÂ°ÃÂ»ÃÂ°ÃÂ¼\n"
        "Ã¢ÂÂ ÃÂÃÂÃÂ¸ÃÂ¾ÃÂÃÂ¸ÃÂÃÂµÃÂÃÂ½ÃÂ°ÃÂ ÃÂ¿ÃÂ¾ÃÂ´ÃÂ´ÃÂµÃÂÃÂ¶ÃÂºÃÂ°\n"
        "Ã¢ÂÂ ÃÂÃÂ¾ÃÂ²ÃÂÃÂµ ÃÂÃÂÃÂ½ÃÂºÃÂÃÂ¸ÃÂ¸ ÃÂ¿ÃÂµÃÂÃÂ²ÃÂÃÂ¼\n\n"
        "ÃÂ¡ÃÂ»ÃÂµÃÂ´ÃÂ¸ÃÂÃÂµ ÃÂ·ÃÂ° ÃÂ¾ÃÂ±ÃÂ½ÃÂ¾ÃÂ²ÃÂ»ÃÂµÃÂ½ÃÂ¸ÃÂÃÂ¼ÃÂ¸!"
    )
    await message.answer(text)

# ÃÂÃÂÃÂ¿ÃÂÃÂ°ÃÂ²ÃÂºÃÂ° ÃÂÃÂÃÂÃÂÃÂ° ÃÂ½ÃÂ° ÃÂ¾ÃÂ¿ÃÂ»ÃÂ°ÃÂÃÂ
async def send_invoice(message: Message):
    user_id = message.from_user.id
    
    if is_subscribed(user_id):
        await message.answer(
            "Ã¢ÂÂ ÃÂ£ ÃÂ²ÃÂ°ÃÂ ÃÂÃÂ¶ÃÂµ ÃÂµÃÂÃÂÃÂ ÃÂ°ÃÂºÃÂÃÂ¸ÃÂ²ÃÂ½ÃÂ°ÃÂ ÃÂ¿ÃÂ¾ÃÂ´ÃÂ¿ÃÂ¸ÃÂÃÂºÃÂ°!\n"
            + get_subscription_info(user_id)
        )
        return
    
    prices = [LabeledPrice(label="ÃÂÃÂ¾ÃÂ´ÃÂ¿ÃÂ¸ÃÂÃÂºÃÂ°", amount=SUBSCRIPTION_PRICE * 100)]
    
    await message.answer_invoice(
        title="ÃÂÃÂ¾ÃÂ´ÃÂ¿ÃÂ¸ÃÂÃÂºÃÂ° ÃÂ½ÃÂ° ÃÂ±ÃÂ¾ÃÂÃÂ°",
        description=f"ÃÂÃÂ¾ÃÂÃÂÃÂÃÂ¿ ÃÂº ÃÂ¿ÃÂÃÂµÃÂ¼ÃÂ¸ÃÂÃÂ¼-ÃÂÃÂÃÂ½ÃÂºÃÂÃÂ¸ÃÂÃÂ¼ ÃÂ½ÃÂ° {SUBSCRIPTION_DAYS} ÃÂ´ÃÂ½ÃÂµÃÂ¹",
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

# ÃÂÃÂÃÂµÃÂ´ÃÂ²ÃÂ°ÃÂÃÂ¸ÃÂÃÂµÃÂ»ÃÂÃÂ½ÃÂ°ÃÂ ÃÂ¿ÃÂÃÂ¾ÃÂ²ÃÂµÃÂÃÂºÃÂ° ÃÂ¿ÃÂ»ÃÂ°ÃÂÃÂµÃÂ¶ÃÂ°
@dp.pre_checkout_query()
async def pre_checkout_query(pre_checkout_query: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

# ÃÂ£ÃÂÃÂ¿ÃÂµÃÂÃÂ½ÃÂÃÂ¹ ÃÂ¿ÃÂ»ÃÂ°ÃÂÃÂÃÂ¶
@dp.message(F.successful_payment)
async def successful_payment(message: Message):
    user_id = message.from_user.id
    payment = message.successful_payment
    
    # ÃÂ¡ÃÂ¾ÃÂÃÂÃÂ°ÃÂ½ÃÂÃÂµÃÂ¼ ÃÂ¿ÃÂ»ÃÂ°ÃÂÃÂÃÂ¶ ÃÂ² ÃÂ±ÃÂ°ÃÂ·ÃÂ
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
    
    # ÃÂÃÂºÃÂÃÂ¸ÃÂ²ÃÂ¸ÃÂÃÂÃÂµÃÂ¼ ÃÂ¿ÃÂ¾ÃÂ´ÃÂ¿ÃÂ¸ÃÂÃÂºÃÂ
    end_date = activate_subscription(user_id)
    
    text = (
        "Ã¢ÂÂ ÃÂÃÂ¿ÃÂ»ÃÂ°ÃÂÃÂ° ÃÂ¿ÃÂÃÂ¾ÃÂÃÂ»ÃÂ° ÃÂÃÂÃÂ¿ÃÂµÃÂÃÂ½ÃÂ¾!\n\n"
        f"Ã°ÂÂÂ ÃÂÃÂ°ÃÂÃÂ° ÃÂ¿ÃÂ¾ÃÂ´ÃÂ¿ÃÂ¸ÃÂÃÂºÃÂ° ÃÂ°ÃÂºÃÂÃÂ¸ÃÂ²ÃÂ¸ÃÂÃÂ¾ÃÂ²ÃÂ°ÃÂ½ÃÂ° ÃÂ´ÃÂ¾ {end_date.strftime('%d.%m.%Y')}\n\n"
        "ÃÂ¢ÃÂµÃÂ¿ÃÂµÃÂÃÂ ÃÂ ÃÂ²ÃÂ°ÃÂ ÃÂµÃÂÃÂÃÂ ÃÂ´ÃÂ¾ÃÂÃÂÃÂÃÂ¿ ÃÂºÃÂ¾ ÃÂ²ÃÂÃÂµÃÂ¼ ÃÂ¿ÃÂÃÂµÃÂ¼ÃÂ¸ÃÂÃÂ¼-ÃÂÃÂÃÂ½ÃÂºÃÂÃÂ¸ÃÂÃÂ¼!"
    )
    
    await message.answer(text, reply_markup=main_keyboard(True))

# ÃÂÃÂ±ÃÂÃÂ°ÃÂ±ÃÂ¾ÃÂÃÂÃÂ¸ÃÂºÃÂ¸ callback-ÃÂ·ÃÂ°ÃÂ¿ÃÂÃÂ¾ÃÂÃÂ¾ÃÂ²
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
        "Ã¢ÂÂ¹Ã¯Â¸Â ÃÂ ÃÂ±ÃÂ¾ÃÂÃÂµ:\n\n"
        "ÃÂ­ÃÂÃÂ¾ ÃÂ´ÃÂµÃÂ¼ÃÂ¾-ÃÂ±ÃÂ¾ÃÂ ÃÂ ÃÂÃÂ¸ÃÂÃÂÃÂµÃÂ¼ÃÂ¾ÃÂ¹ ÃÂ¿ÃÂ¾ÃÂ´ÃÂ¿ÃÂ¸ÃÂÃÂ¾ÃÂº.\n"
        "ÃÂÃÂ½ ÃÂ¿ÃÂ¾ÃÂºÃÂ°ÃÂ·ÃÂÃÂ²ÃÂ°ÃÂµÃÂ, ÃÂºÃÂ°ÃÂº ÃÂ¼ÃÂ¾ÃÂ¶ÃÂ½ÃÂ¾ ÃÂ¼ÃÂ¾ÃÂ½ÃÂµÃÂÃÂ¸ÃÂ·ÃÂ¸ÃÂÃÂ¾ÃÂ²ÃÂ°ÃÂÃÂ Telegram-ÃÂ±ÃÂ¾ÃÂÃÂ°.\n\n"
        "Ã°ÂÂÂ¡ ÃÂÃÂ´ÃÂµÃÂ¸ ÃÂ´ÃÂ»ÃÂ ÃÂ¼ÃÂ¾ÃÂ½ÃÂµÃÂÃÂ¸ÃÂ·ÃÂ°ÃÂÃÂ¸ÃÂ¸:\n"
        "Ã¢ÂÂ¢ ÃÂ­ÃÂºÃÂÃÂºÃÂ»ÃÂÃÂ·ÃÂ¸ÃÂ²ÃÂ½ÃÂÃÂ¹ ÃÂºÃÂ¾ÃÂ½ÃÂÃÂµÃÂ½ÃÂ\n"
        "Ã¢ÂÂ¢ ÃÂÃÂ²ÃÂÃÂ¾ÃÂ¼ÃÂ°ÃÂÃÂ¸ÃÂ·ÃÂ°ÃÂÃÂ¸ÃÂ ÃÂ·ÃÂ°ÃÂ´ÃÂ°ÃÂ\n"
        "Ã¢ÂÂ¢ ÃÂÃÂ¾ÃÂÃÂÃÂÃÂ¿ ÃÂº ÃÂ±ÃÂ°ÃÂ·ÃÂµ ÃÂ´ÃÂ°ÃÂ½ÃÂ½ÃÂÃÂ\n"
        "Ã¢ÂÂ¢ ÃÂÃÂµÃÂÃÂÃÂ¾ÃÂ½ÃÂ°ÃÂ»ÃÂÃÂ½ÃÂÃÂµ ÃÂºÃÂ¾ÃÂ½ÃÂÃÂÃÂ»ÃÂÃÂÃÂ°ÃÂÃÂ¸ÃÂ¸"
    )
    await callback.message.edit_text(text, reply_markup=main_keyboard(is_subscribed(callback.from_user.id)))

@dp.callback_query(F.data == "support")
async def callback_support(callback: CallbackQuery):
    text = (
        "Ã°ÂÂÂ¨Ã¢ÂÂÃ°ÂÂÂ» ÃÂÃÂ¾ÃÂ´ÃÂ´ÃÂµÃÂÃÂ¶ÃÂºÃÂ°:\n\n"
        "ÃÂÃÂÃÂ»ÃÂ¸ ÃÂ ÃÂ²ÃÂ°ÃÂ ÃÂµÃÂÃÂÃÂ ÃÂ²ÃÂ¾ÃÂ¿ÃÂÃÂ¾ÃÂÃÂ, ÃÂ½ÃÂ°ÃÂ¿ÃÂ¸ÃÂÃÂ¸ÃÂÃÂµ ÃÂ½ÃÂ°ÃÂ¼:\n"
        "@username_support\n\n"
        "ÃÂÃÂ ÃÂ¾ÃÂÃÂ²ÃÂµÃÂÃÂ°ÃÂµÃÂ¼ ÃÂ² ÃÂÃÂµÃÂÃÂµÃÂ½ÃÂ¸ÃÂµ 24 ÃÂÃÂ°ÃÂÃÂ¾ÃÂ²."
    )
    await callback.message.edit_text(text, reply_markup=main_keyboard(is_subscribed(callback.from_user.id)))

# Webhook ÃÂ¾ÃÂ±ÃÂÃÂ°ÃÂ±ÃÂ¾ÃÂÃÂÃÂ¸ÃÂº
async def webhook_handler(request):
    try:
        import json
        body = await request.text()
        update = json.loads(body)
        await dp.feed_update(bot, update)
        return web.Response(text="OK")
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        import traceback
        traceback.print_exc()
        return web.Response(text="Error", status=500)

# Health check ÃÂ´ÃÂ»ÃÂ Render
async def health_check(request):
    return web.Response(text="OK")

# ÃÂÃÂ°ÃÂÃÂÃÂÃÂ¾ÃÂ¹ÃÂºÃÂ° ÃÂ²ÃÂµÃÂ±-ÃÂ¿ÃÂÃÂ¸ÃÂ»ÃÂ¾ÃÂ¶ÃÂµÃÂ½ÃÂ¸ÃÂ
async def on_startup(app):
    # ÃÂ£ÃÂÃÂÃÂ°ÃÂ½ÃÂ°ÃÂ²ÃÂ»ÃÂ¸ÃÂ²ÃÂ°ÃÂµÃÂ¼ webhook
    await bot.set_webhook(WEBHOOK_URL)
    logger.info(f"Webhook ÃÂÃÂÃÂÃÂ°ÃÂ½ÃÂ¾ÃÂ²ÃÂ»ÃÂµÃÂ½: {WEBHOOK_URL}")

async def on_shutdown(app):
    # ÃÂ£ÃÂ´ÃÂ°ÃÂ»ÃÂÃÂµÃÂ¼ webhook
    await bot.delete_webhook()
    logger.info("Webhook ÃÂÃÂ´ÃÂ°ÃÂ»ÃÂÃÂ½")

# ÃÂÃÂ°ÃÂ¿ÃÂÃÂÃÂº ÃÂ²ÃÂµÃÂ±-ÃÂ¿ÃÂÃÂ¸ÃÂ»ÃÂ¾ÃÂ¶ÃÂµÃÂ½ÃÂ¸ÃÂ
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
    
    logger.info(f"ÃÂ¡ÃÂµÃÂÃÂ²ÃÂµÃÂ ÃÂ·ÃÂ°ÃÂ¿ÃÂÃÂÃÂµÃÂ½ ÃÂ½ÃÂ° {WEBAPP_HOST}:{WEBAPP_PORT}")
    await site.start()
    
    # ÃÂÃÂµÃÂÃÂ¶ÃÂ¸ÃÂ¼ ÃÂÃÂµÃÂÃÂ²ÃÂµÃÂ ÃÂ·ÃÂ°ÃÂ¿ÃÂÃÂÃÂµÃÂ½ÃÂ½ÃÂÃÂ¼
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
