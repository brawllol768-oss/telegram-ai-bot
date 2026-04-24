import os
import asyncio
import sqlite3
import json
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.types import ParseMode, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils import executor
from telethon import TelegramClient
from telethon.sessions import StringSession
import requests

# ===== КОНФИГУРАЦИЯ =====
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")

if not BOT_TOKEN:
    raise Exception("BOT_TOKEN не задан в переменных окружения!")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

# ===== БАЗА ДАННЫХ =====
def init_db():
    conn = sqlite3.connect("twins.db")
    c = conn.cursor()
    
    c.execute("""CREATE TABLE IF NOT EXISTS accounts (
        id TEXT PRIMARY KEY,
        type TEXT CHECK(type IN ('user', 'bot')),
        token_or_session TEXT,
        is_active INTEGER DEFAULT 1,
        added_by INTEGER,
        name TEXT,
        username TEXT,
        user_id INTEGER,
        added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_used TIMESTAMP
    )""")
    
    c.execute("""CREATE TABLE IF NOT EXISTS send_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id TEXT,
        target TEXT,
        message TEXT,
        status TEXT,
        error TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    
    conn.commit()
    conn.close()

init_db()

# Хранилища
active_clients = {}  # user-аккаунты (Telethon)
user_states = {}

# ===== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====
def get_user_accounts():
    conn = sqlite3.connect("twins.db")
    c = conn.cursor()
    c.execute("SELECT id, token_or_session, name, username FROM accounts WHERE type = 'user' AND is_active = 1")
    rows = c.fetchall()
    conn.close()
    return rows

def save_user_account(phone, session_string, added_by, name="", username=""):
    conn = sqlite3.connect("twins.db")
    c = conn.cursor()
    c.execute("""INSERT OR REPLACE INTO accounts 
                 (id, type, token_or_session, added_by, name, username, last_used)
                 VALUES (?, 'user', ?, ?, ?, ?, ?)""",
              (phone, session_string, added_by, name, username, datetime.now()))
    conn.commit()
    conn.close()

def delete_account(account_id):
    conn = sqlite3.connect("twins.db")
    c = conn.cursor()
    c.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
    conn.commit()
    conn.close()
    if account_id in active_clients:
        asyncio.create_task(active_clients[account_id].disconnect())
        del active_clients[account_id]

# ===== КОМАНДЫ БОТА =====
@dp.message_handler(commands=['start'])
async def start_cmd(message: types.Message):
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    keyboard.add(
        "📱 Мои аккаунты",
        "➕ Добавить аккаунт",
        "📤 Рассылка",
        "📊 Статистика"
    )
    
    await message.reply(
        "🤖 *Twin Manager Bot*\n\n"
        "Управление твинками через одного бота.\n\n"
        "📌 *Команды:*\n"
        "• Добавить аккаунт — авторизация по номеру и коду\n"
        "• Рассылка — отправить сообщение со всех акков\n"
        "• Мои аккаунты — список и статус\n\n"
        "📖 *Чат-команды:*\n"
        "`/send @username текст` — отправить со всех аккаунтов\n"
        "`/join @chat` — вступить в чат всеми акками\n\n"
        f"🆔 Ваш ID: `{message.from_user.id}`\n\n"
        "⚠️ Аккаунты могут быть забанены за спам!",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=keyboard
    )

@dp.message_handler(lambda msg: msg.text == "📱 Мои аккаунты")
async def list_accounts(msg: types.Message):
    accounts = get_user_accounts()
    if not accounts:
        await msg.answer("❌ Нет добавленных аккаунтов.\nНажмите '➕ Добавить аккаунт'")
        return
    
    text = "📱 *Ваши аккаунты:*\n\n"
    for phone, _, name, username in accounts:
        status = "✅" if phone in active_clients else "🔄"
        display = name or username or phone
        text += f"{status} `{display}`\n   📞 `{phone}`\n"
    
    text += f"\n📊 *Всего: {len(accounts)} аккаунтов*"
    text += f"\n🟢 Активных сессий: {len(active_clients)}"
    
    await msg.answer(text, parse_mode=ParseMode.MARKDOWN)

@dp.message_handler(lambda msg: msg.text == "➕ Добавить аккаунт")
async def add_account_start(msg: types.Message):
    await msg.answer(
        "📞 *Добавление аккаунта*\n\n"
        "Введите номер телефона в формате:\n`+71234567890`\n\n"
        "⚠️ Убедитесь, что номер указан с кодом страны.\n"
        "Аккаунт должен быть без 2FA или вы введёте пароль.",
        parse_mode=ParseMode.MARKDOWN
    )
    user_states[msg.from_user.id] = {"step": "waiting_phone"}

@dp.message_handler(lambda msg: msg.from_user.id in user_states and user_states[msg.from_user.id].get("step") == "waiting_phone")
async def process_phone(msg: types.Message):
    phone = msg.text.strip()
    if not phone.startswith("+"):
        await msg.answer("❌ Неверный формат. Номер должен начинаться с +\nПример: +71234567890")
        return
    
    client = TelegramClient(StringSession(), API_ID, API_HASH)
    try:
        await client.connect()
        await client.send_code_request(phone)
        
        user_states[msg.from_user.id] = {
            "step": "waiting_code",
            "phone": phone,
            "client": client
        }
        
        await msg.answer(
            f"📲 Код отправлен на `{phone}`\n\n"
            "Введите код из Telegram:",
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        await msg.answer(f"❌ Ошибка: {str(e)}")
        user_states.pop(msg.from_user.id, None)

@dp.message_handler(lambda msg: msg.from_user.id in user_states and user_states[msg.from_user.id].get("step") == "waiting_code")
async def process_code(msg: types.Message):
    code = msg.text.strip()
    state = user_states[msg.from_user.id]
    phone = state["phone"]
    client = state["client"]
    
    try:
        await client.sign_in(phone, code)
        me = await client.get_me()
        name = me.first_name or ""
        if me.last_name:
            name += f" {me.last_name}"
        
        session_string = client.session.save()
        save_user_account(phone, session_string, msg.from_user.id, name, me.username)
        active_clients[phone] = client
        
        await msg.answer(
            f"✅ *Аккаунт добавлен!*\n\n"
            f"👤 {name}\n"
            f"📞 `{phone}`\n"
            f"🆔 @{me.username or 'нет'}\n\n"
            f"Теперь он доступен для рассылок.",
            parse_mode=ParseMode.MARKDOWN
        )
        user_states.pop(msg.from_user.id, None)
    except Exception as e:
        error_msg = str(e)
        if "password" in error_msg.lower():
            await msg.answer("🔐 Введите пароль двухфакторной аутентификации:")
            user_states[msg.from_user.id]["step"] = "waiting_password"
        elif "phone code invalid" in error_msg.lower():
            await msg.answer("❌ Неверный код. Попробуйте ещё раз.")
        else:
            await msg.answer(f"❌ Ошибка: {error_msg}")
            user_states.pop(msg.from_user.id, None)

@dp.message_handler(lambda msg: msg.from_user.id in user_states and user_states[msg.from_user.id].get("step") == "waiting_password")
async def process_password(msg: types.Message):
    password = msg.text.strip()
    state = user_states[msg.from_user.id]
    phone = state["phone"]
    client = state["client"]
    
    try:
        await client.sign_in(password=password)
        me = await client.get_me()
        name = me.first_name or ""
        if me.last_name:
            name += f" {me.last_name}"
        
        session_string = client.session.save()
        save_user_account(phone, session_string, msg.from_user.id, name, me.username)
        active_clients[phone] = client
        
        await msg.answer(f"✅ Аккаунт {name} добавлен!")
        user_states.pop(msg.from_user.id, None)
    except Exception as e:
        await msg.answer(f"❌ Ошибка: {str(e)}")
        user_states.pop(msg.from_user.id, None)

@dp.message_handler(lambda msg: msg.text == "📤 Рассылка")
async def broadcast_start(msg: types.Message):
    accounts = get_user_accounts()
    if not accounts:
        await msg.answer("❌ Нет аккаунтов для рассылки. Сначала добавьте аккаунты.")
        return
    
    await msg.answer(
        "✏️ *Массовая рассылка*\n\n"
        "Введите текст сообщения для рассылки.\n"
        "Сообщение будет отправлено от каждого аккаунта в 'Избранное' (диалог с собой).\n\n"
        "💡 Чтобы отправить в конкретный чат, используйте команду:\n"
        "`/send @username текст`",
        parse_mode=ParseMode.MARKDOWN
    )
    user_states[msg.from_user.id] = {"step": "waiting_broadcast_text"}

@dp.message_handler(lambda msg: msg.from_user.id in user_states and user_states[msg.from_user.id].get("step") == "waiting_broadcast_text")
async def execute_broadcast(msg: types.Message):
    text = msg.text
    accounts = get_user_accounts()
    
    if not accounts:
        await msg.answer("❌ Аккаунты не найдены.")
        user_states.pop(msg.from_user.id, None)
        return
    
    status_msg = await msg.answer(f"🚀 Начинаю рассылку для {len(accounts)} аккаунтов...")
    
    success = 0
    errors = []
    
    for phone, session_string, name, username in accounts:
        try:
            # Восстанавливаем клиент если нужно
            if phone not in active_clients:
                client = TelegramClient(StringSession(session_string), API_ID, API_HASH)
                await client.connect()
                await client.start()
                active_clients[phone] = client
            
            # Отправляем сообщение в избранное
            await active_clients[phone].send_message("me", f"📢 *Рассылка от {name or phone}* 📢\n\n{text}")
            success += 1
            
        except Exception as e:
            errors.append(f"{name or phone}: {str(e)[:50]}")
        
        await asyncio.sleep(1)  # Защита от флуда
    
    result_text = f"✅ *Результат рассылки*\n\n"
    result_text += f"📤 Успешно: {success}/{len(accounts)}\n"
    
    if errors:
        result_text += f"\n❌ Ошибки ({len(errors)}):\n"
        for err in errors[:5]:
            result_text += f"• {err}\n"
        if len(errors) > 5:
            result_text += f"• ...и ещё {len(errors) - 5}\n"
    
    await status_msg.edit_text(result_text, parse_mode=ParseMode.MARKDOWN)
    user_states.pop(msg.from_user.id, None)

# ===== КОМАНДЫ В ЧАТЕ =====
@dp.message_handler(commands=['send'])
async def cmd_send(msg: types.Message):
    """Отправка сообщения от всех аккаунтов в указанный чат"""
    parts = msg.text.split(maxsplit=2)
    if len(parts) < 3:
        await msg.reply(
            "❌ *Использование:*\n"
            "`/send @username текст сообщения`\n\n"
            "Пример: `/send @durov Привет!`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    target = parts[1]
    text = parts[2]
    accounts = get_user_accounts()
    
    if not accounts:
        await msg.reply("❌ Нет аккаунтов для отправки.")
        return
    
    status_msg = await msg.reply(f"🚀 Отправляю сообщение от {len(accounts)} аккаунтов...")
    
    success = 0
    for phone, session_string, name, username in accounts:
        try:
            if phone not in active_clients:
                client = TelegramClient(StringSession(session_string), API_ID, API_HASH)
                await client.connect()
                await client.start()
                active_clients[phone] = client
            
            await active_clients[phone].send_message(target, text)
            success += 1
            await asyncio.sleep(1)
        except Exception as e:
            print(f"Ошибка {phone}: {e}")
    
    await status_msg.edit_text(f"✅ Отправлено с {success}/{len(accounts)} аккаунтов")

@dp.message_handler(commands=['join'])
async def cmd_join(msg: types.Message):
    """Вступление в чат всеми аккаунтами"""
    parts = msg.text.split()
    if len(parts) < 2:
        await msg.reply("❌ Использование: `/join @chat` или `/join https://t.me/joinchat/xxx`", parse_mode=ParseMode.MARKDOWN)
        return
    
    invite = parts[1]
    accounts = get_user_accounts()
    
    status_msg = await msg.reply(f"🚀 Вступаю в чат {len(accounts)} аккаунтами...")
    
    success = 0
    for phone, session_string, name, username in accounts:
        try:
            if phone not in active_clients:
                client = TelegramClient(StringSession(session_string), API_ID, API_HASH)
                await client.connect()
                await client.start()
                active_clients[phone] = client
            
            await active_clients[phone].join_channel(invite)
            success += 1
        except Exception as e:
            print(f"Ошибка {phone}: {e}")
        await asyncio.sleep(1)
    
    await status_msg.edit_text(f"✅ Вступили: {success}/{len(accounts)}")

@dp.message_handler(commands=['stats'])
async def cmd_stats(msg: types.Message):
    accounts = get_user_accounts()
    await msg.reply(
        f"📊 *Статистика*\n\n"
        f"• Всего аккаунтов: `{len(accounts)}`\n"
        f"• Активных сессий: `{len(active_clients)}`\n"
        f"• Статус: ✅ Работает",
        parse_mode=ParseMode.MARKDOWN
    )

@dp.message_handler(commands=['delete_account'])
async def cmd_delete(msg: types.Message):
    """Удаление аккаунта (только для администратора)"""
    parts = msg.text.split()
    if len(parts) < 2:
        await msg.reply("❌ Использование: `/delete_account +71234567890`", parse_mode=ParseMode.MARKDOWN)
        return
    
    phone = parts[1]
    delete_account(phone)
    await msg.reply(f"✅ Аккаунт {phone} удалён")

@dp.message_handler(commands=['restore_sessions'])
async def cmd_restore(msg: types.Message):
    """Восстановление всех сессий"""
    await msg.reply("🔄 Восстанавливаю сессии...")
    accounts = get_user_accounts()
    restored = 0
    for phone, session_string, name, username in accounts:
        if phone not in active_clients:
            try:
                client = TelegramClient(StringSession(session_string), API_ID, API_HASH)
                await client.connect()
                await client.start()
                active_clients[phone] = client
                restored += 1
            except Exception as e:
                print(f"Ошибка восстановления {phone}: {e}")
    await msg.reply(f"✅ Восстановлено {restored} из {len(accounts)} сессий")

# ===== ЗАПУСК =====
async def on_startup(dp):
    print("🚀 Запуск Twin Manager Bot...")
    print(f"📡 API ID: {API_ID}")
    
    # Восстанавливаем сессии
    accounts = get_user_accounts()
    restored = 0
    for phone, session_string, _, _ in accounts:
        try:
            client = TelegramClient(StringSession(session_string), API_ID, API_HASH)
            await client.connect()
            await client.start()
            active_clients[phone] = client
            restored += 1
        except Exception as e:
            print(f"Ошибка восстановления {phone}: {e}")
    
    print(f"✅ Восстановлено {restored} из {len(accounts)} сессий")
    print("✅ Бот готов к работе!")

if __name__ == "__main__":
    executor.start_polling(dp, on_startup=on_startup, skip_updates=True)
