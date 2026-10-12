import asyncio
import logging
import os
import sqlite3
from datetime import datetime, timedelta
from typing import Optional

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, LabeledPrice, PreCheckoutQuery
from aiogram.filters import CommandStart, Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Конфигурация
BOT_TOKEN = os.getenv("BOT_TOKEN")
PAYMENT_PROVIDER_TOKEN = os.getenv("PAYMENT_PROVIDER_TOKEN")
SUBSCRIPTION_PRICE = int(os.getenv("SUBSCRIPTION_PRICE", "100"))
SUBSCRIPTION_DAYS = int(os.getenv("SUBSCRIPTION_DAYS", "30"))

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не установлен в переменных окружения")

# Инициализация бота
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# База данных
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
        return "❌ У вас нет активной подписки"
    
    end_date = datetime.fromisoformat(user['subscription_end'])
    if end_date <= datetime.now():
        return "❌ Ваша подписка истекла"
    
    days_left = (end_date - datetime.now()).days
    return f"✅ Подписка активна до {end_date.strftime('%d.%m.%Y')} (осталось {days_left} дн.)"

# Клавиатуры
def main_keyboard(subscribed: bool = False) -> InlineKeyboardMarkup:
    buttons = []
    
    if not subscribed:
        buttons.append([
            InlineKeyboardButton(text="💳 Купить подписку", callback_data="buy_subscription")
        ])
    
    buttons.extend([
        [InlineKeyboardButton(text="📊 Моя подписка", callback_data="my_subscription")],
        [InlineKeyboardButton(text="ℹ️ О боте", callback_data="about")],
        [InlineKeyboardButton(text="👨‍💻 Поддержка", callback_data="support")]
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# Обработчики команд
@dp.message(CommandStart())
async def cmd_start(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or ""
    first_name = message.from_user.first_name or ""
    
    create_user(user_id, username, first_name)
    
    subscribed = is_subscribed(user_id)
    
    text = (
        f"👋 Привет, {first_name}!\n\n"
        f"Я демо-бот с системой подписок. "
        f"Купите подписку, чтобы получить доступ к эксклюзивным функциям.\n\n"
        f"💡 Что даёт подписка:\n"
        f"• Доступ к премиум-контенту\n"
        f"• Приоритетная поддержка\n"
        f"• Эксклюзивные функции\n\n"
        f"💰 Стоимость: {SUBSCRIPTION_PRICE}₽/{SUBSCRIPTION_DAYS} днays"
    )
    
    await message.answer(text, reply_markup=main_keyboard(subscribed))

@dp.message(Command("help"))
async def cmd_help(message: Message):
    text = (
        "📋 Доступные команды:\n\n"
        "/start - Главное меню\n"
        "/help - Помощь\n"
        "/status - Статус подписки\n"
        "/buy - Купить подписку\n"
        "/premium - Премиум-контент"
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
            "❌ У вас нет активной подписки.\n"
            "Купите подписку, чтобы получить доступ к премиум-контенту.",
            reply_markup=main_keyboard(False)
        )
        return
    
    text = (
        "🌟 Премиум-контент:\n\n"
        "Спасибо за подписку! Вот ваши преимущества:\n\n"
        "✅ Доступ к эксклюзивным материалам\n"
        "✅ Приоритетная поддержка\n"
        "✅ Новые функции первым\n\n"
        "Следите за обновлениями!"
    )
    await message.answer(text)

# Отправка счёта на оплату
async def send_invoice(message: Message):
    user_id = message.from_user.id
    
    if is_subscribed(user_id):
        await message.answer(
            "✅ У вас уже есть активная подписка!\n"
            + get_subscription_info(user_id)
        )
        return
    
    prices = [LabeledPrice(label="Подписка", amount=SUBSCRIPTION_PRICE * 100)]
    
    await message.answer_invoice(
        title="Подписка на бота",
        description=f"Доступ к премиум-функциям на {SUBSCRIPTION_DAYS} дней",
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

# Предварительная проверка платежа
@dp.pre_checkout_query()
async def pre_checkout_query(pre_checkout_query: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

# Успешный платёж
@dp.message(F.successful_payment)
async def successful_payment(message: Message):
    user_id = message.from_user.id
    payment = message.successful_payment
    
    # Сохраняем платёж в базу
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
    
    # Активируем подписку
    end_date = activate_subscription(user_id)
    
    text = (
        "✅ Оплата прошла успешно!\n\n"
        f"🎉 Ваша подписка активирована до {end_date.strftime('%d.%m.%Y')}\n\n"
        "Теперь у вас есть доступ ко всем премиум-функциям!"
    )
    
    await message.answer(text, reply_markup=main_keyboard(True))

# Обработчики callback-запросов
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
        "ℹ️ О боте:\n\n"
        "Это демо-бот с системой подписок.\n"
        "Он показывает, как можно монетизировать Telegram-бота.\n\n"
        "💡 Идеи для монетизации:\n"
        "• Эксклюзивный контент\n"
        "• Автоматизация задач\n"
        "• Доступ к базе данных\n"
        "• Персональные консультации"
    )
    await callback.message.edit_text(text, reply_markup=main_keyboard(is_subscribed(callback.from_user.id)))

@dp.callback_query(F.data == "support")
async def callback_support(callback: CallbackQuery):
    text = (
        "👨‍💻 Поддержка:\n\n"
        "Если у вас есть вопросы, напишите нам:\n"
        "@username_support\n\n"
        "Мы отвечаем в течение 24 часов."
    )
    await callback.message.edit_text(text, reply_markup=main_keyboard(is_subscribed(callback.from_user.id)))

# Health check для Render (предотвращает засыпание)
@dp.message(F.text == "/health")
async def health_check(message: Message):
    await message.answer("✅ Бот работает!")

# Запуск бота
async def main():
    init_db()
    logger.info("Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
