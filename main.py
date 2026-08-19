import asyncio
import logging
import os
import sqlite3
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, BusinessConnection
from aiogram.filters import Command
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# Токен берем из переменных окружения (для безопасности)
BOT_TOKEN = os.getenv("8708888855:AAE1cXGOMv-8jEN-P-ti1nGW7dfyM0sBlYc")

bot = Bot(token=8708888855:AAE1cXGOMv-8jEN-P-ti1nGW7dfyM0sBlYc)
dp = Dispatcher()
scheduler = AsyncIOScheduler()

# Инициализация базы данных SQLite
conn = sqlite3.connect("bot_data.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    connection_id TEXT,
    folder_link TEXT,
    broadcast_text TEXT
)
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS target_chats (
    user_id INTEGER,
    chat_id INTEGER,
    PRIMARY KEY (user_id, chat_id)
)
""")
conn.commit()


# 1. Отслеживание подключения бота к Telegram Business
@dp.business_connection()
async def on_business_connection(connection: BusinessConnection):
    user_id = connection.user_id
    if connection.is_enabled:
        cursor.execute(
            "INSERT INTO users (user_id, connection_id) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET connection_id=?",
            (user_id, connection.id, connection.id)
        )
        print(f"✅ Бот подключен к бизнесу пользователя {user_id}")
    else:
        cursor.execute("UPDATE users SET connection_id=NULL WHERE user_id=?", (user_id,))
        print(f"❌ Бот отключен от бизнеса пользователя {user_id}")
    conn.commit()


# 2. Команда /start и инструкция
@dp.message(Command("start"))
async def start_cmd(message: Message):
    text = (
        "👋 **Привет! Я бот для авто-рассылки в Telegram Business.**\n\n"
        "**Как меня настроить:**\n"
        "1. Перейдите в `Настройки` ➔ `Telegram Business` ➔ `Чат-боты` и подключите меня.\n"
        "2. Укажите ссылку на папку для рассылки:\n"
        "`/set_folder https://t.me/addlist/ВАША_ССЫЛКА`\n"
        "3. Укажите текст рассылки:\n"
        "`/set_text Ваш рекламный текст`\n\n"
        "После этого я буду автоматически рассылать ваш текст по бизнес-чатам каждый час!"
    )
    await message.answer(text, parse_mode="Markdown")


# 3. Установка текста рассылки
@dp.message(Command("set_text"))
async def set_text_cmd(message: Message):
    user_id = message.from_user.id
    args = message.text.split(maxsplit=1)
    
    if len(args) < 2:
        await message.answer("❌ Укажите текст после команды!\nПример:\n`/set_text Привет! Действует скидка 10%`", parse_mode="Markdown")
        return

    text_to_save = args[1]
    cursor.execute(
        "INSERT INTO users (user_id, broadcast_text) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET broadcast_text=?",
        (user_id, text_to_save, text_to_save)
    )
    conn.commit()
    await message.answer(f"✅ **Текст рассылки сохранен:**\n\n{text_to_save}", parse_mode="Markdown")


# 4. Установка ссылки на папку
@dp.message(Command("set_folder"))
async def set_folder_cmd(message: Message):
    user_id = message.from_user.id
    args = message.text.split(maxsplit=1)

    if len(args) < 2 or not args[1].startswith("https://t.me/addlist/"):
        await message.answer("❌ Укажите корректную ссылку на папку!\nПример:\n`/set_folder https://t.me/addlist/K_4TSI0ZbcI4OGE8`", parse_mode="Markdown")
        return

    folder_url = args[1]
    cursor.execute(
        "INSERT INTO users (user_id, folder_link) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET folder_link=?",
        (user_id, folder_url, folder_url)
    )
    conn.commit()
    await message.answer(f"✅ **Ссылка на папку сохранена:**\n{folder_url}", parse_mode="Markdown")


# 5. Перехват входящих диалогов из Telegram Business
@dp.business_message()
async def catch_business_messages(message: Message):
    # Запоминаем ID чата клиента для конкретного владельца бизнеса
    business_owner_id = message.from_user.id
    chat_id = message.chat.id
    
    cursor.execute(
        "INSERT OR IGNORE INTO target_chats (user_id, chat_id) VALUES (?, ?)",
        (business_owner_id, chat_id)
    )
    conn.commit()


# 6. Автоматическая рассылка каждый час по всем пользователям
async def send_hourly_broadcast():
    cursor.execute("SELECT user_id, connection_id, broadcast_text FROM users WHERE connection_id IS NOT NULL AND broadcast_text IS NOT NULL")
    active_users = cursor.fetchall()

    for owner_id, connection_id, text in active_users:
        cursor.execute("SELECT chat_id FROM target_chats WHERE user_id=?", (owner_id,))
        chats = cursor.fetchall()

        for (chat_id,) in chats:
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    business_connection_id=connection_id
                )
                await asyncio.sleep(1)  # Пауза 1 секунда между сообщениями
            except Exception as e:
                print(f"Ошибка отправки пользователю {owner_id} в чат {chat_id}: {e}")


async def main():
    logging.basicConfig(level=logging.INFO)

    # Настройка планировщика на запуск каждый час (3600 сек)
    scheduler.add_job(send_hourly_broadcast, "interval", hours=1)
    scheduler.start()

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
