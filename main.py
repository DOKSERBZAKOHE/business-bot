import os
import asyncio
import logging
import sqlite3
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.client.session.aiohttp import AiohttpSession
from apscheduler.schedulers.asyncio import AsyncIOScheduler

logging.basicConfig(level=logging.INFO)

# Инициализация базы данных
conn = sqlite3.connect("bot_data.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    connection_id TEXT,
    folder_url TEXT,
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

# Настройка бота с прокси для PythonAnywhere
session = AiohttpSession(proxy="http://proxy.server:3128")
bot = Bot(token=os.environ.get("BOT_TOKEN"), session=session)
dp = Dispatcher()


# --- Команды настройки ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "Привет! Я бот для автоматической рассылки через Telegram Business.\n\n"
        "Команды:\n"
        "• `/set_text <текст>` — задать текст рассылки\n"
        "• `/set_folder <ссылка>` — задать ссылку на папку с чатами\n"
        "• `/test_broadcast` — запустить рассылку прямо сейчас (тест)"
    )

@dp.message(Command("set_text"))
async def cmd_set_text(message: types.Message):
    text = message.text.replace("/set_text", "").strip()
    if not text:
        await message.answer("Пожалуйста, укажи текст после команды. Пример:\n`/set_text Ваш рекламный текст`")
        return
    
    cursor.execute(
        "INSERT INTO users (user_id, broadcast_text) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET broadcast_text=excluded.broadcast_text",
        (message.from_user.id, text)
    )
    conn.commit()
    await message.answer("✅ Текст рассылки успешно сохранён!")

@dp.message(Command("set_folder"))
async def cmd_set_folder(message: types.Message):
    url = message.text.replace("/set_folder", "").strip()
    if not url:
        await message.answer("Пожалуйста, укажи ссылку после команды. Пример:\n`/set_folder https://t.me/addlist/...`")
        return

    cursor.execute(
        "INSERT INTO users (user_id, folder_url) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET folder_url=excluded.folder_url",
        (message.from_user.id, url)
    )
    conn.commit()
    await message.answer("✅ Ссылка на папку сохранена!")


# --- Логика Telegram Business ---

@dp.business_connection()
async def handle_business_connection(connection: types.BusinessConnection):
    cursor.execute(
        "INSERT INTO users (user_id, connection_id) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET connection_id=excluded.connection_id",
        (connection.user_id, connection.id)
    )
    conn.commit()
    logging.info(f"Бизнес-подключение {connection.id} сохранено для пользователя {connection.user_id}")

@dp.business_message()
async def handle_business_message(message: types.Message):
    cursor.execute(
        "INSERT OR IGNORE INTO target_chats (user_id, chat_id) VALUES (?, ?)",
        (message.from_user.id, message.chat.id)
    )
    conn.commit()


# --- Рассылка ---

async def send_hourly_broadcast():
    logging.info("Запуск функции рассылки...")
    cursor.execute("SELECT user_id, connection_id, broadcast_text FROM users WHERE connection_id IS NOT NULL AND broadcast_text IS NOT NULL")
    users = cursor.fetchall()

    for user_id, connection_id, text in users:
        cursor.execute("SELECT chat_id FROM target_chats WHERE user_id = ?", (user_id,))
        chats = cursor.fetchall()

        for (chat_id,) in chats:
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    business_connection_id=connection_id
                )
                logging.info(f"Сообщение отправлено в чат {chat_id} от пользователя {user_id}")
                await asyncio.sleep(12)  # Безопасная задержка
            except Exception as e:
                logging.error(f"Ошибка отправки в чат {chat_id}: {e}")

# Команда для ручного запуска рассылки в любой момент
@dp.message(Command("test_broadcast"))
async def cmd_test_broadcast(message: types.Message):
    await message.answer("🚀 Запускаю тестовую рассылку...")
    await send_hourly_broadcast()
    await message.answer("✅ Тестовая рассылка завершена!")


# --- Запуск ---

async def main():
    scheduler = AsyncIOScheduler()
    scheduler.add_job(send_hourly_broadcast, 'interval', hours=1)
    scheduler.start()

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())