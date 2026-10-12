# Telegram Bot с монетизацией

Простой Telegram-бот с системой подписок и приёмом платежей.

## 🚀 Быстрый старт

### 1. Клонирование репозитория
```bash
git clone https://github.com/zxkittenxd/tg-bot.git
cd tg-bot
```

### 2. Установка зависимостей
```bash
pip install -r requirements.txt
```

### 3. Настройка
Скопируйте `.env.example` в `.env` и заполните значения:
```bash
cp .env.example .env
```

Получите токены:
- **BOT_TOKEN**: [@BotFather](https://t.me/BotFather) -> /newbot
- **PAYMENT_PROVIDER_TOKEN**: [@BotFather](https://t.me/BotFather) -> Payments -> выберите провайдера

### 4. Запуск
```bash
python bot.py
```

## 📋 Команды бота

| Команда | Описание |
|---------|----------|
| /start | Главное меню |
| /help | Помощь |
| /status | Статус подписки |
| /buy | Купить подписку |
| /premium | Премиум-контент |

## 💰 Монетизация

Бот использует Telegram Payments для приёма платежей:
- Подписка: 100₽ / 30 дней
- Платежи обрабатываются через Telegram

## 🛠 Технологии

- [aiogram](https://github.com/aiogram/aiogram) 3.x — асинхронный фреймворк для Telegram Bot API
- SQLite — база данных
- Python 3.10+

## 📄 Лицензия

MIT
