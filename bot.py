import asyncio
from telethon import TelegramClient, events
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
import sqlite3
from datetime import datetime

# === Конфигурация Telethon ===
API_ID = 
API_HASH = 
OWNER_ID =   # Ваш Telegram ID
PING_INTERVAL = 600  # Интервал пинга в секундах

# === Конфигурация Aiogram ===
BOT_API_TOKEN =   # Токен от BotFather

# === Состояние бота ===
bot_enabled = True

# === Инициализация Telethon и базы данных ===
telethon_client = TelegramClient('bot_session', API_ID, API_HASH)
conn = sqlite3.connect('messages.db', check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    username TEXT,
    message TEXT,
    importance INTEGER,
    details TEXT,
    timestamp DATETIME
)
''')
conn.commit()

# === Инициализация Aiogram ===
aiogram_bot = Bot(token=BOT_API_TOKEN)
dp = Dispatcher(aiogram_bot)


# === Telethon: Логика работы основного бота ===
def get_greeting():
    hour = datetime.now().hour
    if 6 <= hour < 12:
        return "Доброе утро! Я сейчас занят, но скоро отвечу."
    elif 12 <= hour < 18:
        return "Добрый день! Я отвечу вам в течение дня."
    elif 18 <= hour < 23:
        return "Добрый вечер! Я занят, но отвечу, как только освобожусь."
    else:
        return "Я сейчас сплю. Ожидайте ответа утром."


def can_respond(user_id):
    cursor.execute(
        "SELECT timestamp FROM messages WHERE user_id = ? ORDER BY timestamp DESC LIMIT 1",
        (user_id,)
    )
    last_message = cursor.fetchone()
    if last_message:
        last_time = datetime.strptime(last_message[0], '%Y-%m-%d %H:%M:%S')
        return (datetime.now() - last_time).seconds > PING_INTERVAL
    return True


async def notify_owner(client, message, importance):
    sender_username = message.sender.username if message.sender.username else "Unknown"
    await client.send_message(
        OWNER_ID,
        f"Важное сообщение от @{sender_username}:\n"
        f"'{message.text}' (важность: {importance})"
    )

# === Глобальный словарь для управления состояниями пользователей ===
user_states = {}

# === Глобальный список пользователей, которых бот игнорирует ===
ignored_users = []  # Замените на реальные ID пользователей

@telethon_client.on(events.NewMessage(incoming=True))
async def handle_message(event):
    global bot_enabled

    # Проверяем, включен ли бот
    if not bot_enabled:
        return  # Игнорируем все входящие сообщения, если бот выключен

    # Проверяем, что сообщение пришло в личный чат
    if not event.is_private:
        return  # Игнорируем сообщения из групп или каналов

    try:
        # Получаем данные об отправителе
        sender = await event.get_sender()

        # Игнорируем сообщения от ботов
        if sender.bot:
            return

        # Игнорируем сообщения от пользователей из списка ignored_users
        if sender.id in ignored_users:
            print(f"Сообщение от {sender.id} ({sender.username}) проигнорировано.")
            return

        username = sender.username if sender and sender.username else "Unknown"
        user_id = sender.id
        message_text = event.text.strip()

        # Проверяем, есть ли пользователь в словаре состояний
        if user_id in user_states:
            # Получаем текущее состояние пользователя
            state = user_states[user_id]
            if state == 'awaiting_importance':
                # Пользователь должен указать важность сообщения
                try:
                    importance = int(message_text)
                    if 1 <= importance <= 10:
                        # Обновляем запись в базе данных
                        cursor.execute(
                            "UPDATE messages SET importance = ? WHERE user_id = ? ORDER BY id DESC LIMIT 1",
                            (importance, user_id)
                        )
                        conn.commit()

                        # Уведомляем владельца, если важность >= 8
                        if importance >= 8:
                            await notify_owner(telethon_client, event, importance)

                        # Запрашиваем дополнительные детали
                        await event.reply("Спасибо! Можете рассказать подробнее о вашем запросе.")
                        # Обновляем состояние пользователя
                        user_states[user_id] = 'awaiting_details'
                    else:
                        await event.reply("Пожалуйста, укажите важность числом от 1 до 10.")
                except ValueError:
                    await event.reply("Неверный формат. Укажите важность числом от 1 до 10.")
            elif state == 'awaiting_details':
                # Пользователь должен предоставить дополнительные детали
                details = message_text
                # Обновляем запись в базе данных
                cursor.execute(
                    "UPDATE messages SET details = ? WHERE user_id = ? ORDER BY id DESC LIMIT 1",
                    (details, user_id)
                )
                conn.commit()
                await event.reply("Спасибо за предоставленную информацию. Мы свяжемся с вами в ближайшее время.")
                # Удаляем пользователя из словаря состояний
                del user_states[user_id]
        else:
            # Проверяем, нужно ли отвечать
            if not can_respond(user_id):
                return

            # Формируем и отправляем ответ
            greeting = get_greeting()
            await event.reply(f"{greeting}\nУкажите важность вашего сообщения от 1 до 10.")

            # Сохраняем сообщение в базу данных
            cursor.execute(
                "INSERT INTO messages (user_id, username, message, importance, timestamp) VALUES (?, ?, ?, ?, ?)",
                (user_id, username, message_text, None, datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            )
            conn.commit()

            # Обновляем состояние пользователя
            user_states[user_id] = 'awaiting_importance'
    except Exception as e:
        print(f"Произошла ошибка: {e}")



# === Aiogram: Управление ботом ===
@dp.message_handler(commands=['start'])
async def start_command(message: types.Message):
    if message.from_user.id == OWNER_ID:
        await message.reply("Привет! Используй /enable или /disable, чтобы управлять основным ботом.")
    else:
        await message.reply("Извините, этот бот предназначен только для владельца.")


@dp.message_handler(commands=['enable'])
async def enable_bot(message: types.Message):
    global bot_enabled
    if message.from_user.id == OWNER_ID:
        bot_enabled = True
        await message.reply("Основной бот включен!")
    else:
        await message.reply("У вас нет доступа к этой команде.")


@dp.message_handler(commands=['disable'])
async def disable_bot(message: types.Message):
    global bot_enabled
    if message.from_user.id == OWNER_ID:
        bot_enabled = False
        await message.reply("Основной бот выключен!")
    else:
        await message.reply("У вас нет доступа к этой команде.")


# === Запуск обоих ботов ===
def start_aiogram():
    """Отдельный запуск Aiogram."""
    print("Запуск бота управления (Aiogram)...")
    executor.start_polling(dp, skip_updates=True)


async def start_telethon():
    """Запуск Telethon."""
    print("Запуск основного бота (Telethon)...")
    await telethon_client.start()
    await telethon_client.run_until_disconnected()


if __name__ == '__main__':
    loop = asyncio.get_event_loop()

    # Запускаем Telethon и Aiogram параллельно
    try:
        loop.create_task(start_telethon())
        start_aiogram()  # Aiogram запускается в отдельном потоке
    except KeyboardInterrupt:
        print("Боты остановлены")
    finally:
        conn.close()
